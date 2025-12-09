import os
import rasterio
import numpy as np
from rasterio.transform import Affine
from skyfield.toposlib import wgs84
from typing import Tuple

from config import settings

def _calculate_horizon_single_dem(dem_path: str, lat: float, lon: float, alt_m: float = 0, search_radius_km: float = 10.0) -> np.ndarray:
    """
    Calculates the terrain horizon profile from a single DEM file for a given observer location.

    Args:
        dem_path: Path to the Digital Elevation Model (DEM) GeoTIFF file.
        lat: Latitude of the observer (degrees).
        lon: Longitude of the observer (degrees).
        alt_m: Altitude of the observer above the WGS84 ellipsoid (meters).
        search_radius_km: Maximum radius in kilometers to search for terrain obstructions.

    Returns:
        A NumPy array of shape (360, 2) where each row is [azimuth_degrees, elevation_degrees].
        Azimuths are from 0 to 359 degrees. Elevation is the angle from the horizontal to the
        highest obstruction at that azimuth. Returns all zeros if no DEM data or obstructions.
    """
    print("starting horizon calc")
    with rasterio.open(dem_path) as dem_dataset:
        # Convert observer lat/lon to DEM pixel coordinates
        try:
            obs_row, obs_col = dem_dataset.index(lon, lat)
        except Exception:
            # Observer is outside DEM bounds, return flat horizon
            return np.zeros((360, 2))

        # Ensure observer is within valid pixel coordinates
        if not (0 <= obs_row < dem_dataset.height and 0 <= obs_col < dem_dataset.width):
            return np.zeros((360, 2))

        # Get observer's actual terrain height from DEM
        # Read a small window around the observer for safety
        window = rasterio.windows.Window(
            max(0, obs_col - 1),
            max(0, obs_row - 1),
            min(dem_dataset.width, 3),
            min(dem_dataset.height, 3)
        )
        dem_data_window = dem_dataset.read(1, window=window)
        terrain_height_at_obs = dem_data_window[obs_row - window.row_off, obs_col - window.col_off]

        # Observer's total height above mean sea level
        # If dem_data is invalid (e.g., -9999), assume alt_m is absolute
        if terrain_height_at_obs < -1000: # Common nodata value for DEMs
            observer_height_m = alt_m # Assume alt_m is above sea level if no DEM
        else:
            observer_height_m = terrain_height_at_obs + alt_m

        # Get pixel size in degrees
        transform = dem_dataset.transform
        pixel_size_x_deg = transform.a
        pixel_size_y_deg = transform.e # This is negative for north-up rasters

        mean_radius = 6371000.0 # Earth's mean radius in meters for curvature correction

        # Meters per degree of latitude is roughly constant
        meters_per_degree_lat = 111320.0 
        
        pixel_size_y_m = abs(pixel_size_y_deg * meters_per_degree_lat)
        pixel_size_x_m = abs(pixel_size_x_deg * meters_per_degree_lat * np.cos(np.radians(lat)))
        
        horizon_profile = np.zeros((360, 2)) # [azimuth, elevation_angle]

        # Generate rays for 360 degrees
        azimuths_rad = np.radians(np.arange(360))
        
        # Distances to sample along each ray
        num_samples = 100 # Number of points to sample along each ray
        max_dist_m = search_radius_km * 1000
        distances_m = np.linspace(0, max_dist_m, num_samples)

        # Vectorized ray tracing
        # dx, dy in meters from observer
        dx_m = np.sin(azimuths_rad[:, np.newaxis]) * distances_m[np.newaxis, :]
        dy_m = np.cos(azimuths_rad[:, np.newaxis]) * distances_m[np.newaxis, :]

        # Convert dx, dy in meters to pixel offsets from observer
        # Note: rasterio rows increase downwards (South), cols increase right (East)
        # Positive dx_m is East, Positive dy_m is North
        ray_rows_float = obs_row - (dy_m / pixel_size_y_m)
        ray_cols_float = obs_col + (dx_m / pixel_size_x_m)

        # Convert to integer pixel coordinates and clip to DEM bounds
        ray_rows = np.clip(ray_rows_float.astype(int), 0, dem_dataset.height - 1)
        ray_cols = np.clip(ray_cols_float.astype(int), 0, dem_dataset.width - 1)
        
        # Sample terrain heights along each ray
        terrain_heights = dem_dataset.read(1)[ray_rows, ray_cols]

        # Calculate vector from observer to each terrain point
        # Distances from observer to the point on the terrain surface (horizontal distance)
        horizontal_distances = np.sqrt(dx_m**2 + dy_m**2)
        
        # Calculate curvature adjustment
        # h_curvature = d^2 / (2 * R), where R is Earth's mean radius
        h_curvature = horizontal_distances**2 / (2 * mean_radius)

        # Adjust terrain heights for Earth curvature
        # Subtract h_curvature from terrain_heights because terrain appears lower due to curvature
        adjusted_terrain_heights = terrain_heights - h_curvature
        
        # Replace nodata values with a very low number to not obstruct
        nodata_mask = adjusted_terrain_heights < -1000 # Assuming -9999 or similar is nodata
        adjusted_terrain_heights[nodata_mask] = -10000 # Effectively below observer

        # Elevation difference to terrain points, with curvature correction
        elevation_diffs = adjusted_terrain_heights - observer_height_m

        # Calculate elevation angles for all points along all rays
        # Add a small epsilon to avoid division by zero for horizontal_distances[0]=0
        elevation_angles_rad = np.arctan2(elevation_diffs, horizontal_distances + 1e-6)
        elevation_angles_deg = np.degrees(elevation_angles_rad)

        # Find the maximum elevation angle along each ray (azimuth)
        max_elevation_per_azimuth = np.max(elevation_angles_deg, axis=1)

        horizon_profile[:, 0] = np.arange(360) # Azimuth
        horizon_profile[:, 1] = max_elevation_per_azimuth # Max elevation angle

        print("finished horizon calc")
        return horizon_profile

def calculate_horizon_from_directory(lat: float, lon: float, alt_m: float = 0, search_radius_km: float = 10.0) -> np.ndarray:
    """
    Calculates the terrain horizon profile by searching for a suitable DEM file
    in the configured dem_data directory.

    Args:
        lat: Latitude of the observer (degrees).
        lon: Longitude of the observer (degrees).
        alt_m: Altitude of the observer above the WGS84 ellipsoid (meters).
        search_radius_km: Maximum radius in kilometers to search for terrain obstructions.

    Returns:
        A NumPy array of shape (360, 2) representing the terrain horizon profile.
        Returns all zeros if no suitable DEM file is found covering the observer's location.
    """
    dem_data_dir = os.path.join(os.getcwd(), settings.dem_data_dir)

    if not os.path.isdir(dem_data_dir):
        print(f"DEM data directory not found: {dem_data_dir}")
        return np.zeros((360, 2))

    for filename in os.listdir(dem_data_dir):
        if filename.endswith(".tif"):
            dem_path = os.path.join(dem_data_dir, filename)
            try:
                with rasterio.open(dem_path) as dem_dataset:
                    # Check if observer's lat/lon is within DEM bounds
                    if dem_dataset.crs.is_geographic:
                        # For geographic CRS, bounds are lat/lon
                        if (dem_dataset.bounds.left <= lon <= dem_dataset.bounds.right and
                            dem_dataset.bounds.bottom <= lat <= dem_dataset.bounds.top):
                            
                            print(f"Found suitable DEM: {filename}")
                            return _calculate_horizon_single_dem(dem_path, lat, lon, alt_m, search_radius_km)
                    else:
                        # For projected CRS, need to transform
                        # Simpler to just assume geographic for now as Copernicus DEMs are geographic
                        pass # Handle error or log warning

            except rasterio.errors.RasterioIOError:
                print(f"Could not open or read DEM file: {filename}")
            except Exception as e:
                print(f"Error processing DEM file {filename}: {e}")

    print("No suitable DEM file found covering the observer's location. Returning flat horizon.")
    return np.zeros((360, 2))