import pytest
import numpy as np
import rasterio
from rasterio.transform import from_origin
from dem_service import get_tile_filename, find_dem_tile_path, calculate_horizon
from unittest.mock import patch

@pytest.fixture(scope="module")
def mock_dem_file(tmpdir_factory):
    """
    Creates a temporary GeoTIFF file with a simple E-W ridge for testing.
    The DEM is 1000x1000 pixels, with each pixel being ~10m.
    A 200m high ridge is placed horizontally in the middle.
    """
    path_obj = tmpdir_factory.mktemp("data").join("test_ridge.tif")
    path_str = str(path_obj)
    width, height = 1000, 1000
    
    # Create a simple ridge terrain
    data = np.zeros((height, width), dtype=np.float32)
    data[490:510, :] = 200  # 200m high ridge across the middle

    # Define metadata for the GeoTIFF
    # Place it over lat/lon 0,0 for simplicity
    transform = from_origin(0, 0, 10.0 / (111320), 10.0 / 111320) # Approx 10m pixels
    
    with rasterio.open(
        path_str,
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
        
    return path_str


def test_get_tile_filename_logic():
    """
    Tests the core logic of the DEM tile filename generation.
    """
    # Test case 1: Los Angeles (should be in tile N34, W119)
    lat1, lon1 = 34.0522, -118.2437
    fname1 = get_tile_filename(lat1, lon1)
    assert fname1 == "Copernicus_DSM_10_N34_00_W119_00.tif"

    # Test case 2: Sydney, Australia (should be in tile S34, E151)
    lat2, lon2 = -33.8688, 151.2093
    fname2 = get_tile_filename(lat2, lon2)
    assert fname2 == "Copernicus_DSM_10_S34_00_E151_00.tif"

    # Test case 3: Near equator/prime meridian (positive)
    lat3, lon3 = 0.5, 0.5
    fname3 = get_tile_filename(lat3, lon3)
    assert fname3 == "Copernicus_DSM_10_N00_00_E000_00.tif"
    
    # Test case 4: Near equator/prime meridian (negative)
    lat4, lon4 = -0.5, -0.5
    fname4 = get_tile_filename(lat4, lon4)
    assert fname4 == "Copernicus_DSM_10_S01_00_W001_00.tif"

@patch('dem_service.os.path.exists')
def test_find_dem_tile_path_exists(mock_exists):
    """
    Tests that find_dem_tile_path returns a full path if the file exists.
    """
    # Arrange
    mock_exists.return_value = True
    
    # Act
    path = find_dem_tile_path(34.0522, -118.2437)
    
    # Assert
    assert path is not None
    assert "dem_data" in path
    assert "Copernicus_DSM_10_N34_00_W119_00.tif" in path

@patch('dem_service.os.path.exists')
def test_find_dem_tile_path_not_exists(mock_exists):
    """
    Tests that find_dem_tile_path returns None if the file does not exist.
    """
    # Arrange
    mock_exists.return_value = False
    
    # Act
    path = find_dem_tile_path(34.0522, -118.2437)
    
    # Assert
    assert path is None

def test_calculate_horizon_with_ridge(mock_dem_file):
    """
    Tests the horizon calculation with a predictable ridge.
    Observer is at the bottom-center, looking north towards the ridge.
    """
    # Observer position near the bottom of the 1000-pixel-high tile
    # The mock DEM's top edge is at lat=0. A pixel is ~9e-5 degrees.
    # Row 950 is at lat = -(950 * 9e-5) approx -0.085
    obs_lat, obs_lon = -0.085, 0.005 # Approx bottom-center

    horizon = calculate_horizon(mock_dem_file, obs_lat, obs_lon, search_radius_km=10.0)

    # Expected angle to the ridge
    # Observer is at ~row 950. Ridge is at row ~500. Distance is ~450 pixels.
    # Pixel size is ~10m. Distance is ~4500m. Ridge height is 200m.
    expected_angle = np.degrees(np.arctan2(200, 4500)) # ~2.5 degrees
    
    # Assertions
    assert horizon.shape == (360, 2)
    
    # Azimuths pointing North (e.g., 340-359 and 0-20 deg) should see the ridge
    # Azimuths pointing South (e.g., 160-200 deg) should see a flat horizon (angle ~0)
    
    # Check a northerly direction
    north_horizon_elevation = horizon[0, 1]
    assert north_horizon_elevation == pytest.approx(expected_angle, abs=0.5)

    # Check an easterly direction (should be flat as it's parallel to the ridge)
    east_horizon_elevation = horizon[90, 1]
    assert east_horizon_elevation == pytest.approx(0, abs=0.2)

    # Check a southerly direction (looking away from the ridge)
    south_horizon_elevation = horizon[180, 1]
    assert south_horizon_elevation == pytest.approx(0, abs=0.2)
