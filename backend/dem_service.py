import math
import os

import numpy as np
import rasterio
from config import settings


def get_tile_filename(lat: float, lon: float) -> str:
    """
    Generates the standard Copernicus DEM filename for a given lat/lon.
    It correctly determines the lower-left corner for the tile.

    Args:
        lat: Latitude.
        lon: Longitude.

    Returns:
        The standardized DEM filename (e.g., 'Copernicus_DSM_10_N34_00_W119_00.tif').
    """
    # Determine direction based on the original coordinate
    lat_dir = 'N' if lat >= 0 else 'S'
    lon_dir = 'E' if lon >= 0 else 'W'

    # Floor the coordinate to get the integer for the lower-left corner
    lat_floor = math.floor(lat)
    lon_floor = math.floor(lon)

    # Absolute value is used for the filename itself
    lat_val = abs(lat_floor)
    lon_val = abs(lon_floor)

    # Based on observed Copernicus DEM naming conventions
    # Example: lat=34.05, lon=-118.24 -> floor(lat)=34, floor(lon)=-119 -> N34, W119
    filename = f"Copernicus_DSM_10_{lat_dir}{lat_val:02d}_00_{lon_dir}{lon_val:03d}_00.tif"
    
    return filename


def find_dem_tile_path(lat: float, lon: float) -> str | None:
    """
    Finds the full path to a DEM tile file for a given lat/lon if it exists locally.

    Args:
        lat: Latitude.
        lon: Longitude.

    Returns:
        The full path to the DEM file, or None if it does not exist.
    """
    filename = get_tile_filename(lat, lon)
    full_path = os.path.join(settings.dem_data_dir, filename)

    if os.path.exists(full_path):
        return full_path
    
    return None


def calculate_horizon(dem_path: str, lat: float, lon: float, alt_m: float = 0, search_radius_km: float = 50.0) -> np.ndarray:
    """
    Calculates a 360-degree horizon profile from a DEM for a given observer location.

    Args:
        dem_path: Path to the DEM file (GeoTIFF).
        lat: Observer's latitude.
        lon: Observer's longitude.
        alt_m: Observer's altitude in meters above the ground.
        search_radius_km: How far out to search for terrain obstructions.

    Returns:
        A NumPy array of shape (360, 2) where each row is [azimuth, elevation].
        Returns an empty array if the calculation cannot be performed.
    """
    try:
        with rasterio.open(dem_path) as dem_dataset:
            # --- 1. Get Observer Position and Elevation ---
            # Convert observer's geo coordinates to the DEM's pixel coordinates
            # Note: rasterio's `index` method returns (row, col)
            obs_row, obs_col = dem_dataset.index(lon, lat)

            # Read the DEM data into a numpy array
            dem_data = dem_dataset.read(1)

            # Get observer's ground elevation from the DEM and add personal altitude
            obs_elev_ground = dem_data[obs_row, obs_col]
            obs_elev_total = obs_elev_ground + alt_m

            # --- 2. Prepare for Vectorized Calculation ---
            # Get pixel size from the dataset's geotransform
            pixel_size_x = dem_dataset.transform[0]
            # Assuming square pixels, which is typical
            pixel_size_m = abs(pixel_size_x * 111320 * np.cos(np.radians(lat))) # Approx meters/degree

            max_dist_m = search_radius_km * 1000
            num_steps = int(max_dist_m / pixel_size_m)
            
            # Create arrays for azimuths and distances
            azimuths_rad = np.radians(np.arange(360))
            distances_m = np.linspace(pixel_size_m, max_dist_m, num=num_steps)

            # Earth radius for curvature correction
            R_EARTH_M = 6371 * 1000

            # --- 3. Perform Horizon Calculation ---
            horizon_profile = np.zeros(360)

            # Loop through each degree of azimuth
            for az_deg in range(360):
                az_rad = np.radians(az_deg)

                # Generate a "ray" of points outwards from the observer
                # Calculate the x and y offsets from the observer's pixel
                dx = np.sin(az_rad) * distances_m
                dy = np.cos(az_rad) * distances_m

                # Convert these meter offsets to pixel offsets
                ray_cols = (obs_col + dx / pixel_size_m).astype(int)
                ray_rows = (obs_row - dy / pixel_size_m).astype(int) # North is up, so subtract

                # Filter out points that fall outside the DEM boundaries
                valid_indices = (ray_rows >= 0) & (ray_rows < dem_data.shape[0]) & \
                                (ray_cols >= 0) & (ray_cols < dem_data.shape[1])
                
                ray_rows = ray_rows[valid_indices]
                ray_cols = ray_cols[valid_indices]
                valid_distances_m = distances_m[valid_indices]

                if len(valid_distances_m) == 0:
                    continue

                # Sample the terrain elevation at each point along the ray
                terrain_elevations = dem_data[ray_rows, ray_cols]
                
                # Correct for Earth's curvature
                # This calculates how much the terrain "drops" away due to curvature
                curvature_correction = (valid_distances_m**2) / (2 * R_EARTH_M)
                
                # Calculate the elevation difference, accounting for observer height and curvature
                elevation_diff = terrain_elevations - obs_elev_total - curvature_correction

                # Calculate the vertical angle to each point on the terrain
                # We use np.degrees and np.arctan2 for a stable calculation
                angles = np.degrees(np.arctan2(elevation_diff, valid_distances_m))
                
                # The horizon for this azimuth is the maximum angle found
                horizon_profile[az_deg] = np.max(angles)

            # Combine azimuths and elevations into the final shape
            return np.column_stack((np.arange(360), horizon_profile))

    except Exception as e:
        print(f"Error calculating horizon: {e}")
        return np.array([])


