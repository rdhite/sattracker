import os
import datetime
import requests
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


def calculate_passes(lat: float, lon: float, alt_m: float = 0) -> list[dict]:
    """
    Calculates all satellite passes over a given ground station for the next 24 hours.

    Args:
        lat: Latitude of the ground station.
        lon: Longitude of the ground station.
        alt_m: Altitude of the ground station in meters.

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

    for sat in satellites:
        try:
            times, events = sat.find_events(ground_station, t0, t1, altitude_degrees=10.0)
            
            # Each pass is a sequence of 3 events: rise, culminate, set
            if len(events) > 2:
                # Group events by pass
                for i in range(0, len(events) - 2, 3):
                    if events[i] == 0 and events[i+1] == 1 and events[i+2] == 2: # Rise, Culmination, Set
                        aos_time = times[i]
                        tca_time = times[i+1]
                        los_time = times[i+2]

                        # Calculate max elevation at TCA
                        difference = sat - ground_station
                        topocentric = difference.at(tca_time)
                        alt, az, distance = topocentric.altaz()

                        all_passes.append({
                            "name": sat.name,
                            "aos_time": aos_time,
                            "tca_time": tca_time,
                            "los_time": los_time,
                            "max_elevation_deg": alt.degrees
                        })

        except Exception as e:
            # Some satellites might not have valid TLE data or other issues
            # print(f"Could not calculate pass for {sat.name}: {e}")
            pass

    # Sort passes by acquisition time
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

