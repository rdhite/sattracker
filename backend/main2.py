#%%
from datetime import datetime, timezone, timedelta

import numpy as np
from sgp4.api import jday, SatrecArray, Satrec
from tqdm import tqdm

# Try importing gstime from possible locations
try:
    from sgp4.api import gstime
except ImportError:
    from sgp4.propagation import gstime

# Skyfield imports for verification
from skyfield.api import Topos, load, EarthSatellite
from skyfield.sgp4lib import EarthSatellite as SGEarthSatellite

from vectorized_sat_service import TLEService

def get_jday_datetime(dt):
    """
    Converts a Python datetime object to Julian Date (JD) and Fraction (FR).
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_utc = dt.astimezone(timezone.utc)
    
    year, month, day = dt_utc.year, dt_utc.month, dt_utc.day
    hour, minute = dt_utc.hour, dt_utc.minute
    second = dt_utc.second + dt_utc.microsecond / 1e6
    
    jd, fr = jday(year, month, day, hour, minute, second)
    return jd, fr

def teme_to_ecef(r_teme, jd, fr):
    """
    Converts TEME position vectors to ECEF.
    """
    gmst = gstime(jd + fr)

    cos_theta = np.cos(gmst)
    sin_theta = np.sin(gmst)

    if r_teme.ndim == 3 and r_teme.shape[1] == 1:
        r_teme = r_teme.squeeze(1)

    x = r_teme[:, 0]
    y = r_teme[:, 1]
    z = r_teme[:, 2]

    x_ecef = x * cos_theta + y * sin_theta
    y_ecef = -x * sin_theta + y * cos_theta
    z_ecef = z

    return np.stack([x_ecef, y_ecef, z_ecef], axis=1)

def ecef_to_aer(r_ecef, lat_deg, lon_deg, alt_m):
    """
    Converts ECEF positions to Azimuth, Elevation, Range.
    """
    lat_rad = np.radians(lat_deg)
    lon_rad = np.radians(lon_deg)
    
    # Earth constants (WGS84)
    a = 6378.137  # km
    f = 1.0 / 298.257223563
    e2 = 2*f - f*f
    
    N = a / np.sqrt(1 - e2 * np.sin(lat_rad)**2)
    alt_km = alt_m / 1000.0
    
    x_obs = (N + alt_km) * np.cos(lat_rad) * np.cos(lon_rad)
    y_obs = (N + alt_km) * np.cos(lat_rad) * np.sin(lon_rad)
    z_obs = (N * (1 - e2) + alt_km) * np.sin(lat_rad)
    
    r_obs = np.array([x_obs, y_obs, z_obs])
    
    rho_ecef = r_ecef - r_obs 
    
    sin_lat = np.sin(lat_rad)
    cos_lat = np.cos(lat_rad)
    sin_lon = np.sin(lon_rad)
    cos_lon = np.cos(lon_rad)
    
    dx = rho_ecef[:, 0]
    dy = rho_ecef[:, 1]
    dz = rho_ecef[:, 2]

    e_enu = -sin_lon * dx + cos_lon * dy
    n_enu = -sin_lat * cos_lon * dx - sin_lat * sin_lon * dy + cos_lat * dz
    u_enu = cos_lat * cos_lon * dx + cos_lat * sin_lon * dy + sin_lat * dz
    
    rng = np.sqrt(e_enu**2 + n_enu**2 + u_enu**2)
    az = np.degrees(np.arctan2(e_enu, n_enu))
    az = (az + 360) % 360
    el = np.degrees(np.arcsin(u_enu / rng))
    
    return az, el, rng

# --- Main Logic ---

tlesvc = TLEService('starlink')
sats = tlesvc.get_satellites()

# Simulation Parameters
now = datetime.now(timezone.utc)
lat, lon, alt = 40.7128, -74.0060, 0 # NYC
jd, fr = get_jday_datetime(now)

print(f"Time: {now}")

# 1. Custom Vectorized Calculation
jd_arr = np.array([jd])
fr_arr = np.array([fr])

e, r_teme, v_teme = sats.sgp4(jd_arr, fr_arr)
r_ecef = teme_to_ecef(r_teme, jd, fr)
az_vec, el_vec, rng_vec = ecef_to_aer(r_ecef, lat, lon, alt)

# 2. Skyfield Calculation (Reference)
print("Comparing with Skyfield...")
ts = load.timescale()
t = ts.from_datetime(now)
observer = Topos(latitude_degrees=lat, longitude_degrees=lon, elevation_m=alt)

# We need to reconstruct EarthSatellite objects from the Satrec objects
# TLEService loads into a SatrecArray. We can access the underlying list if accessible, 
# or we can just reload the TLEs to be safe and match indices. 
# However, SatrecArray is just a wrapper around C++ vector. 
# Let's read the cache file manually to ensure we line up Skyfield objects 1-to-1.

import os
from config import settings
cache_file = os.path.join(settings.cache_dir, settings.tle_cache_file_tmpl.format(group='starlink'))

with open(cache_file, 'r') as f:
    lines = list(filter(lambda x: x, map(lambda x: x.strip(), f.readlines())))

# Skyfield needs Line 1 and Line 2
# lines structure: Name, Line1, Line2
skyfield_sats = []
for i in range(0, len(lines), 3):
    name = lines[i]
    l1 = lines[i+1]
    l2 = lines[i+2]
    sat = EarthSatellite(l1, l2, name, ts)
    skyfield_sats.append(sat)

# Select a subset to compare to save time, or do all?
# Let's do a subset of random indices
num_samples = 100
indices = np.random.choice(len(skyfield_sats), num_samples, replace=False)

diffs = []

print(f"Checking {num_samples} random satellites...")

for idx in tqdm(indices, desc='straight maths', unit='sat'):
    # Skyfield
    sat = skyfield_sats[idx]
    difference = sat - observer
    topocentric = difference.at(t)
    sf_alt, sf_az, sf_dist = topocentric.altaz()
    
    sf_az_deg = sf_az.degrees
    sf_el_deg = sf_alt.degrees
    sf_rng_km = sf_dist.km
    
    # Vectorized
    v_az = az_vec[idx]
    v_el = el_vec[idx]
    v_rng = rng_vec[idx]
    
    # Calculate differences
    d_az = abs(sf_az_deg - v_az)
    # Handle azimuth wraparound 360-0
    if d_az > 180:
        d_az = 360 - d_az
        
    d_el = abs(sf_el_deg - v_el)
    d_rng = abs(sf_rng_km - v_rng)
    
    diffs.append((d_az, d_el, d_rng))

diffs = np.array(diffs)
mean_diff = np.mean(diffs, axis=0)
max_diff = np.max(diffs, axis=0)

print("\n--- Differences (Skyfield vs Vectorized) ---")
print(f"Mean Diff: Az={mean_diff[0]:.6f} deg, El={mean_diff[1]:.6f} deg, Range={mean_diff[2]:.6f} km")
print(f"Max Diff:  Az={max_diff[0]:.6f} deg, El={max_diff[1]:.6f} deg, Range={max_diff[2]:.6f} km")

# Assertions for sanity check
# We allow some small deviation due to different constants or float precision
assert max_diff[0] < 0.1, f"Azimuth difference too high: {max_diff[0]}"
assert max_diff[1] < 0.05, f"Elevation difference too high: {max_diff[1]}"
assert max_diff[2] < 0.5, f"Range difference too high: {max_diff[2]}"

print("\nValidation Successful: Vectorized calculations match Skyfield closely.")

# %%
