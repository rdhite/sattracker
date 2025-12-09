import os
import datetime
import requests
import numpy as np
from tqdm import tqdm
from skyfield.api import load, EarthSatellite, Topos

from config import settings

# Construct cache file path from settings
CACHE_FILE = os.path.join(settings.cache_dir, settings.tle_cache_file)


def _ensure_cache_dir_exists():
    """Ensures the cache directory exists."""
    if not os.path.exists(settings.cache_dir):
        os.makedirs(settings.cache_dir)


def _is_cache_valid() -> bool:
    """Checks if the cached TLE file is still valid."""
    if not os.path.exists(CACHE_FILE):
        return False
    
    file_mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(CACHE_FILE), tz=datetime.timezone.utc)
    expiration_time = datetime.timedelta(hours=settings.cache_expiration_hours)
    
    return (datetime.datetime.now(datetime.timezone.utc) - file_mod_time) < expiration_time


def _download_tle_data():
    """Downloads TLE data from the source and saves it to the cache."""
    try:
        response = requests.get(settings.tle_url)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        _ensure_cache_dir_exists()
        with open(CACHE_FILE, "w") as f:
            f.write(response.text)
        print("Successfully downloaded and cached TLE data.")

    except requests.exceptions.RequestException as e:
        print(f"Error downloading TLE data: {e}")
        # In a real app, you'd want more robust error handling
        # Maybe fallback to an older cache if available, or raise an exception
        pass


def get_satellites() -> list[EarthSatellite]:
    """
    Gets a list of EarthSatellite objects from cached or freshly downloaded TLE data.
    """
    if not _is_cache_valid():
        print("Cache is invalid or missing, downloading fresh TLE data.")
        _download_tle_data()
    else:
        print("Using valid cached TLE data.")

    if not os.path.exists(CACHE_FILE):
        print("Could not load satellites: TLE file is missing and download failed.")
        return []
        
    ts = load.timescale()
    try:
        satellites = load.tle_file(CACHE_FILE)
        print(f"Loaded {len(satellites)} satellites.")
        return satellites
    except Exception as e:
        print(f"Error loading TLE file: {e}")
        # This could happen if the file is corrupted. We might want to re-download.
        return []


def calculate_passes(lat: float, lon: float, alt_m: float = 0, horizon_profile: np.ndarray | None = None) -> list[dict]:
    """
    Calculates all satellite passes over a given ground station for the next 24 hours.
    Optionally filters passes against a terrain horizon profile.

    Args:
        lat: Latitude of the ground station.
        lon: Longitude of the ground station.
        alt_m: Altitude of the ground station in meters.
        horizon_profile: A NumPy array of shape (360, 2) representing the horizon.

    Returns:
        A list of dictionaries, where each dictionary represents a single satellite pass.
    """
    satellites = get_satellites()
    if not satellites:
        return []

    ts = load.timescale()
    ground_station = Topos(latitude_degrees=lat, longitude_degrees=lon, elevation_m=alt_m)

    t0 = ts.now()
    t1 = ts.from_datetime(t0.utc_datetime() + datetime.timedelta(hours=24))

    all_passes = []

    for sat in tqdm(satellites):
        try:
            times, events = sat.find_events(ground_station, t0, t1, altitude_degrees=10.0)
            
            if len(events) > 2:
                for i in range(0, len(events) - 2, 3):
                    if events[i] == 0 and events[i+1] == 1 and events[i+2] == 2:
                        aos_time, tca_time, los_time = times[i], times[i+1], times[i+2]

                        # If no horizon profile, use the original pass data
                        if horizon_profile is None:
                            difference = sat - ground_station
                            topocentric = difference.at(tca_time)
                            alt, az, distance = topocentric.altaz()
                            max_el = alt.degrees
                        
                        # If horizon profile is provided, filter the pass
                        else:
                            # 1. Sample the pass at a regular interval
                            sample_times = ts.linspace(aos_time, los_time, 100)
                            difference = sat - ground_station
                            topocentric = difference.at(sample_times)
                            alt, az, distance = topocentric.altaz()
                            
                            # 2. Get terrain horizon for each sample point's azimuth
                            terrain_elevations = horizon_profile[az.degrees.astype(int), 1]
                            
                            # 3. Determine visibility at each sample point
                            is_visible = alt.degrees > terrain_elevations
                            
                            # 4. Find the longest continuous visible segment
                            if not np.any(is_visible):
                                continue # Pass is fully obstructed, skip it

                            # Find indices where visibility changes
                            vis_changes = np.diff(is_visible.astype(int))
                            rise_indices = np.where(vis_changes == 1)[0] + 1
                            set_indices = np.where(vis_changes == -1)[0] + 1

                            # Create pairs of rise/set events
                            if is_visible[0]:
                                rise_indices = np.insert(rise_indices, 0, 0)
                            if is_visible[-1]:
                                set_indices = np.append(set_indices, len(is_visible) - 1)

                            if not len(rise_indices) or not len(set_indices):
                                continue

                            # Find the longest segment
                            longest_duration = 0
                            best_segment = None
                            for r_idx, s_idx in zip(rise_indices, set_indices):
                                duration = sample_times[s_idx] - sample_times[r_idx]
                                if duration > longest_duration:
                                    longest_duration = duration
                                    best_segment = (r_idx, s_idx)
                            
                            if best_segment is None:
                                continue

                            # 5. Update pass with the new, shorter AOS/LOS times
                            aos_time = sample_times[best_segment[0]]
                            los_time = sample_times[best_segment[1]]
                            
                            # Find new TCA and max elevation for the visible segment
                            visible_times = ts.linspace(aos_time, los_time, 50)
                            visible_topo = (sat - ground_station).at(visible_times)
                            visible_alt, _, _ = visible_topo.altaz()
                            max_el = np.max(visible_alt.degrees)
                            tca_time = visible_times[np.argmax(visible_alt.degrees)]

                        all_passes.append({
                            "name": sat.name,
                            "aos_time": aos_time,
                            "tca_time": tca_time,
                            "los_time": los_time,
                            "max_elevation_deg": max_el,
                        })
        except Exception:
            pass

    all_passes.sort(key=lambda x: x['aos_time'])
    return all_passes

if __name__ == '__main__':
    # For simple testing of the service
    sats = get_satellites()
    if sats:
        print(f"Example satellite: {sats[0].name}")

        # Test pass calculation
        ground_station_lat = 34.0522  # Los Angeles
        ground_station_lon = -118.2437
        
        print(f"\nCalculating passes for {ground_station_lat}, {ground_station_lon}...")
        passes = calculate_passes(ground_station_lat, ground_station_lon)

        if passes:
            print(f"Found {len(passes)} passes in the next 24 hours.")
            # Print details of the first 5 passes
            for p in passes[:5]:
                print(
                    f"  - Satellite: {p['name']}, "
                    f"AOS: {p['aos_time'].utc_strftime('%Y-%m-%d %H:%M:%S')}, "
                    f"TCA: {p['tca_time'].utc_strftime('%Y-%m-%d %H:%M:%S')}, "
                    f"LOS: {p['los_time'].utc_strftime('%Y-%m-%d %H:%M:%S')}, "
                    f"Max El: {p['max_elevation_deg']:.2f}°"
                )
        else:
            print("No passes found in the next 24 hours.")

