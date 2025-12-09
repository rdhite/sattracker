import pytest
import numpy as np
import rasterio
from rasterio.transform import from_origin
import os
import shutil

# Import the new simple_dem_service
from simple_dem_service import calculate_horizon_from_directory, _calculate_horizon_single_dem
from config import settings

@pytest.fixture(scope="module")
def mock_dem_file_in_dem_data():
    """
    Creates a temporary GeoTIFF file with a simple E-W ridge in the dem_data directory
    for testing simple_dem_service.
    """
    # Ensure dem_data directory exists
    dem_data_path = os.path.join(os.getcwd(), settings.dem_data_dir)
    os.makedirs(dem_data_path, exist_ok=True)

    test_file_name = "test_ridge_for_simple_dem.tif"
    dem_path = os.path.join(dem_data_path, test_file_name)

    width, height = 1000, 1000
    
    # Create a simple ridge terrain
    data = np.zeros((height, width), dtype=np.float32)
    data[490:510, :] = 200  # 200m high ridge across the middle

    # Define metadata for the GeoTIFF
    # Place it over lat/lon 0,0 for simplicity
    transform = from_origin(0, 0, 10.0 / (111320), 10.0 / 111320) # Approx 10m pixels
    
    with rasterio.open(
        dem_path,
        'w',
        driver='GTiff',
        height=height,
        width=width,
        count=1,
        dtype=data.dtype,
        crs='EPSG:4326',
        transform=transform,
    ) as dst:
        dst.write(data, 1)
        
    yield dem_path # Provide the path to the test
    
    # Teardown: Remove the test file and the directory if empty
    os.remove(dem_path)
    if not os.listdir(dem_data_path): # Check if directory is empty after removing the file
        shutil.rmtree(dem_data_path)


def test_calculate_horizon_from_directory_with_ridge(mock_dem_file_in_dem_data):
    """
    Tests the calculate_horizon_from_directory with a predictable ridge.
    """
    # Observer position near the bottom of the 1000-pixel-high tile
    # The mock DEM's top edge is at lat=0. A pixel is ~9e-5 degrees.
    # Row 950 is at lat = -(950 * 9e-5) approx -0.085
    obs_lat, obs_lon = -0.085, 0.005 # Approx bottom-center

    # Ensure the dem_path is used by the simple_dem_service (it just needs to exist)
    # The fixture ensures it's in the correct directory.

    horizon = calculate_horizon_from_directory(obs_lat, obs_lon, search_radius_km=10.0)

    # Expected angle to the ridge
    # Observer is at ~row 950. Ridge is at row ~500. Distance is ~450 pixels.
    # Pixel size is ~10m. Distance is ~4500m. Ridge height is 200m.
    expected_angle = np.degrees(np.arctan2(200, 4500)) # ~2.5 degrees
    
    # Assertions
    assert horizon.shape == (360, 2)
    
    # Check a northerly direction (should see the ridge)
    north_horizon_elevation = horizon[0, 1]
    assert north_horizon_elevation == pytest.approx(expected_angle, abs=0.5)

    # Check an easterly direction (should be flat as it's parallel to the ridge)
    east_horizon_elevation = horizon[90, 1]
    assert east_horizon_elevation == pytest.approx(0, abs=0.2)

    # Check a southerly direction (looking away from the ridge)
    south_horizon_elevation = horizon[180, 1]
    assert south_horizon_elevation == pytest.approx(0, abs=0.2)


def test_calculate_horizon_from_directory_no_dem_found():
    """
    Tests calculate_horizon_from_directory when no suitable DEM is found in the directory.
    It should return a flat horizon (all zeros).
    """
    # Use coordinates far away from where mock_dem_file_in_dem_data creates a DEM
    obs_lat, obs_lon = 50.0, 50.0 

    horizon = calculate_horizon_from_directory(obs_lat, obs_lon, search_radius_km=10.0)

    # Expect a flat horizon
    assert horizon.shape == (360, 2)
    assert np.all(horizon == 0)
