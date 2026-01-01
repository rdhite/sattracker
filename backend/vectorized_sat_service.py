import os
import datetime

import numpy as np
import requests
from sgp4.api import jday, Satrec, SatrecArray
from sgp4.propagation import gstime

from config import settings

class TLEService:
    """Manages downloading, caching, and in-memory loading of TLE data."""
    
    def __init__(self, celestrack_group="stations"):
        self._satellites: list[Satrec] = None
        self._cache_file = os.path.join(settings.cache_dir, settings.tle_cache_file_tmpl.format(group=celestrack_group))
        self._last_loaded: datetime.datetime | None = None
        self._group = celestrack_group

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
            response = requests.get(settings.tle_url_tmpl.format(group=self._group))
            response.raise_for_status()

            self._ensure_cache_dir_exists()
            with open(self._cache_file, "w") as f:
                f.write(response.text)
            print(f"Successfully downloaded and cached TLE data to {self._cache_file}")

        except requests.exceptions.RequestException as e:
            print(f"Error downloading TLE data: {e}")
            if not os.path.exists(self._cache_file):
                raise RuntimeError("No TLE data available and download failed.") from e

    def get_satellites(self) -> SatrecArray:
        """Returns the list of satellites, loading from cache or downloading if needed."""
        now = datetime.datetime.now(datetime.timezone.utc)
        
        if self._satellites and self._last_loaded:
            if (now - self._last_loaded) < datetime.timedelta(hours=settings.cache_expiration_hours):
                return self._satellites

        try:
            if not self._is_cache_valid():
                self._download_tle_data()

            with open(self._cache_file, 'r') as f:
                lines = list(filter(lambda x: x, map(lambda x: x.strip(), f.readlines())))
                names = lines[::3]
                tles = zip(lines[1::3], lines[2::3])

            self._satellites = SatrecArray([Satrec.twoline2rv(one, two) for (one, two) in tles])
            self._last_loaded = now
            print(f"Loaded {len(self._satellites)} satellites.")
            return self._satellites
        except Exception as e:
            print(f"Error loading TLE file: {e}")
            return self._satellites or []

class SatelliteService:
    def __init__(self, tle_service: TLEService):
        self.tle_service = tle_service

    def get_active_links(self, lat: float, lon: float, alt_m: float = 0, min_altitude_deg = 10, horizon_profile: np.ndarray | None = None) -> list[dict]:
        sats = self.tle_service.get_satellites()
        now = datetime.datetime.now(datetime.timezone.utc)
        jd, fr = jday(now.year, now.month, now.day, now.hour, now.munite, now.second + now.microsecond / 1e6)

        e, r_teme, _ = sats.sgp4(jd, fr)
        if np.where(e != 0).any():
            print("Some expection(s) while sgp4ing the satellites")
            return []

        r_ecef = teme_to_ecef(r_teme, jd, fr)
        az_vec, el_vec, rng_vec = ecef_to_aer(r_ecef, lat, lon, alt_m)
        

    def calculate_passes(self, lat: float, lon: float, alt_m: float = 0, horizon_profile: np.ndarray | None = None) -> list[dict]:
        pass


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