import os
import datetime
import requests
import numpy as np
from tqdm import tqdm
from skyfield.api import load, EarthSatellite, Topos

from config import settings

class TLEService:
    """Manages downloading, caching, and in-memory loading of TLE data."""
    
    def __init__(self):
        self._satellites: list[EarthSatellite] | None = None
        self._cache_file = os.path.join(settings.cache_dir, settings.tle_cache_file)
        self._last_loaded: datetime.datetime | None = None

    def _ensure_cache_dir_exists(self):
        if not os.path.exists(settings.cache_dir):
            os.makedirs(settings.cache_dir)

    def _is_cache_valid(self) -> bool:
        if not os.path.exists(self._cache_file):
            return False
        
        file_mod_time = datetime.datetime.fromtimestamp(
            os.path.getmtime(self._cache_file), tz=datetime.timezone.utc
        )
        expiration_time = datetime.timedelta(hours=settings.cache_expiration_hours)
        
        return (datetime.datetime.now(datetime.timezone.utc) - file_mod_time) < expiration_time

    def _download_tle_data(self):
        print("Downloading fresh TLE data...")
        try:
            response = requests.get(settings.tle_url)
            response.raise_for_status()
            
            self._ensure_cache_dir_exists()
            with open(self._cache_file, "w") as f:
                f.write(response.text)
            print(f"Successfully downloaded and cached TLE data to {self._cache_file}")

        except requests.exceptions.RequestException as e:
            print(f"Error downloading TLE data: {e}")
            if not os.path.exists(self._cache_file):
                raise RuntimeError("No TLE data available and download failed.") from e

    def get_satellites(self) -> list[EarthSatellite]:
        """Returns the list of satellites, loading from cache or downloading if needed."""
        now = datetime.datetime.now(datetime.timezone.utc)
        
        if self._satellites and self._last_loaded:
            if (now - self._last_loaded) < datetime.timedelta(hours=settings.cache_expiration_hours):
                return self._satellites

        try:
            if not self._is_cache_valid():
                self._download_tle_data()

            self._satellites = load.tle_file(self._cache_file)
            self._last_loaded = now
            print(f"Loaded {len(self._satellites)} satellites.")
            return self._satellites
        except Exception as e:
            print(f"Error loading TLE file: {e}")
            return self._satellites or []

class SatelliteService:
    def __init__(self, tle_service: TLEService):
        self.tle_service = tle_service

    def get_active_links(self, lat: float, lon: float, alt_m: float = 0, horizon_profile: np.ndarray | None = None) -> list[dict]:
        """
        Directly checks which satellites are currently visible.
        This fixes the bug where in-progress passes were missed.
        """
        satellites = self.tle_service.get_satellites()
        ts = load.timescale()
        now = ts.now()
        ground_station = Topos(latitude_degrees=lat, longitude_degrees=lon, elevation_m=alt_m)
        
        active_links = []
        
        # Vectorized calculation of current positions for all satellites
        # Note: Skyfield can handle multiple satellites if we use a specific approach, 
        # but for now let's focus on correctness for active links.
        for sat in tqdm(satellites, desc="Calculating passes"):
            difference = sat - ground_station
            topocentric = difference.at(now)
            alt, az, _ = topocentric.altaz()
            
            if alt.degrees > 10.0:
                is_visible = True
                if horizon_profile is not None:
                    az_idx = int(az.degrees) % 360
                    mask_el = horizon_profile[az_idx, 1]
                    is_visible = alt.degrees > mask_el
                
                if is_visible:
                    #TODO: Handle terrain mask for LOS as well

                    # To get remaining time, we still need to find the LOS event
                    # But we only do this for VISIBLE satellites, which is much faster.
                    t1 = ts.from_datetime(now.utc_datetime() + datetime.timedelta(hours=2))
                    times, events = sat.find_events(ground_station, now, t1, altitude_degrees=10.0)
                    
                    remaining_time = 0
                    for t, event in zip(times, events):
                        if event == 2: # LOS
                            remaining_time = (t.utc_datetime() - now.utc_datetime()).total_seconds()
                            break
                    
                    active_links.append({
                        "name": sat.name,
                        "remaining_time_seconds": remaining_time,
                        "azimuth_deg": az.degrees,
                        "elevation_deg": alt.degrees,
                    })
        
        return active_links

    def calculate_passes(self, lat: float, lon: float, alt_m: float = 0, horizon_profile: np.ndarray | None = None) -> list[dict]:
        """
        Calculates all satellite passes over a given ground station for the next 24 hours.
        """
        satellites = self.tle_service.get_satellites()
        if not satellites:
            return []

        ts = load.timescale()
        ground_station = Topos(latitude_degrees=lat, longitude_degrees=lon, elevation_m=alt_m)

        t0 = ts.now()
        t1 = ts.from_datetime(t0.utc_datetime() + datetime.timedelta(hours=24))

        all_passes = []

        for sat in tqdm(satellites, desc="Calculating passes"):
            try:
                times, events = sat.find_events(ground_station, t0, t1, altitude_degrees=10.0)
                
                if len(events) == 0:
                    continue

                # Handle potential in-progress pass at the very start
                # If first event is TCA or LOS, we have an in-progress pass
                start_idx = 0
                if events[0] in [1, 2]:
                    # We can't easily find the AOS in the past with find_events,
                    # but for /predict, we can just use t0 as a pseudo-AOS 
                    # or search slightly backwards. Searching backwards is better.
                    t_minus_1h = ts.from_datetime(t0.utc_datetime() - datetime.timedelta(hours=1))
                    past_times, past_events = sat.find_events(ground_station, t_minus_1h, t0, altitude_degrees=10.0)
                    
                    # Look for the AOS in the past results
                    aos_time = None
                    tca_time = None
                    los_time = None
                    for pt, pe in reversed(list(zip(past_times, past_events))):
                        if pe == 0:
                            aos_time = pt
                            break # we don't need to keep going back in time
                        elif pe == 1:
                            tca_time = pt
                    
                    if aos_time:
                        # Find TCA and LOS in current results
                        for i, evt in enumerate(events):
                            if evt == 1:
                                tca_time = times[i]
                            elif evt == 2:
                                los_time = times[i]
                                start_idx = i + 1
                                break
                        
                        if aos_time and tca_time and los_time:
                            pass_data = self._process_pass(sat, ground_station, aos_time, tca_time, los_time, horizon_profile)
                            if pass_data:
                                all_passes.append(pass_data)

                # Process the rest of the events in triples
                i = start_idx
                while i < len(events) - 2:
                    if events[i] == 0 and events[i+1] == 1 and events[i+2] == 2:
                        aos_t, tca_t, los_t = times[i], times[i+1], times[i+2]
                        pass_data = self._process_pass(sat, ground_station, aos_t, tca_t, los_t, horizon_profile)
                        if pass_data:
                            all_passes.append(pass_data)
                        i += 3
                    else:
                        i += 1
            except Exception as e:
                print(f"Error processing pass for satellite {sat.name}: {e}")

        all_passes.sort(key=lambda x: x['aos_time'])
        return all_passes

    def _process_pass(self, sat, ground_station, aos_time, tca_time, los_time, horizon_profile):
        """Processes a single pass, optionally filtering by terrain."""
        if horizon_profile is None:
            difference = sat - ground_station

            topocentric_tca = difference.at(tca_time)
            tca_alt, tca_az, _ = topocentric_tca.altaz()
            
            topocentric_aos = difference.at(aos_time)
            aos_alt, aos_az, _ = topocentric_aos.altaz()
            
            topocentric_los = difference.at(los_time)
            los_alt, los_az, _ = topocentric_los.altaz()
            
            return {
                "name": sat.name,
                "aos_time": aos_time,
                "aos_azimuth_deg": aos_az.degrees,
                "aos_elevation_deg": aos_alt.degrees,
                "tca_time": tca_time,
                "tca_azimuth_deg": tca_az.degrees,
                "tca_elevation_deg": tca_alt.degrees,
                "los_time": los_time,
                "los_azimuth_deg": los_az.degrees,
                "los_elevation_deg": los_alt.degrees,
                "max_elevation_deg": tca_alt.degrees,
                "max_elevation_azimuth_deg": tca_az.degrees,
            }
        else:
            return self._filter_pass_with_horizon(sat, ground_station, aos_time, los_time, horizon_profile)

    def _filter_pass_with_horizon(self, sat, ground_station, aos_time, los_time, horizon_profile):
        """Filters a pass against a terrain horizon profile and finds the visible segment."""
        ts = load.timescale()
        # Vectorized sampling of the pass
        sample_times = ts.linspace(aos_time, los_time, 100)
        difference = sat - ground_station
        topocentric_samples = difference.at(sample_times)
        alt_samples, az_samples, _ = topocentric_samples.altaz()
        
        terrain_elevations = horizon_profile[az_samples.degrees.astype(int) % 360, 1]
        is_visible = alt_samples.degrees > terrain_elevations
        
        if not np.any(is_visible):
            return None

        # Find the longest continuous visible segment
        vis_changes = np.diff(is_visible.astype(int))
        rise_indices = np.where(vis_changes == 1)[0] + 1
        set_indices = np.where(vis_changes == -1)[0] + 1

        if is_visible[0]:
            rise_indices = np.insert(rise_indices, 0, 0)
        if is_visible[-1]:
            set_indices = np.append(set_indices, len(is_visible) - 1)

        longest_duration = 0
        best_segment = None
        for r_idx, s_idx in zip(rise_indices, set_indices):
            duration = sample_times[s_idx] - sample_times[r_idx]
            if duration > longest_duration:
                longest_duration = duration
                best_segment = (r_idx, s_idx)
        
        if best_segment is None:
            return None

        new_aos_time = sample_times[best_segment[0]]
        new_los_time = sample_times[best_segment[1]]
        
        # Recalculate AOS/LOS details for the visible segment
        topo_aos = difference.at(new_aos_time)
        aos_alt, aos_az, _ = topo_aos.altaz()

        topo_los = difference.at(new_los_time)
        los_alt, los_az, _ = topo_los.altaz()

        # Find max elevation within the visible segment
        visible_times = ts.linspace(new_aos_time, new_los_time, 50)
        visible_topo = difference.at(visible_times)
        visible_alt, visible_az, _ = visible_topo.altaz()
        max_el_idx = np.argmax(visible_alt.degrees)
        
        return {
            "name": sat.name,
            "aos_time": new_aos_time,
            "aos_azimuth_deg": aos_az.degrees,
            "aos_elevation_deg": aos_alt.degrees,
            "tca_time": visible_times[max_el_idx],
            "tca_azimuth_deg": visible_az.degrees[max_el_idx],
            "tca_elevation_deg": visible_alt.degrees[max_el_idx],
            "los_time": new_los_time,
            "los_azimuth_deg": los_az.degrees,
            "los_elevation_deg": los_alt.degrees,
            "max_elevation_deg": visible_alt.degrees[max_el_idx],
            "max_elevation_azimuth_deg": visible_az.degrees[max_el_idx],
        }

if __name__ == '__main__':
    # Simple test execution
    tle_service = TLEService()
    sat_service = SatelliteService(tle_service)
    sats = tle_service.get_satellites()
    if sats:
        print(f"Example satellite: {sats[0].name}")
        passes = sat_service.calculate_passes(34.0522, -118.2437)
        print(f"Found {len(passes)} passes.")
