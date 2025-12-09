import pytest
from unittest.mock import patch
from skyfield.api import EarthSatellite, load

# Since we are running tests from the 'backend' directory,
# we should be able to import the modules directly.
# If not, we may need to adjust the python path.
from satellite_service import calculate_passes

# A real TLE for a known satellite (ISS)
TLE_LINE_1 = '1 25544U 98067A   25343.58287413  .00004913  00000+0  90184-4 0  9993'
TLE_LINE_2 = '2 25544  51.6402 242.0227 0006753  32.5512  91.1399 15.49494792423528'

@pytest.fixture
def mock_iss_satellite():
    """Provides a mock ISS satellite for testing."""
    ts = load.timescale()
    iss = EarthSatellite(TLE_LINE_1, TLE_LINE_2, 'ISS (ZARYA)', ts)
    return [iss]

@patch('satellite_service.get_satellites')
def test_calculate_passes_finds_iss_pass(mock_get_satellites, mock_iss_satellite):
    """
    Test that calculate_passes finds at least one pass for the ISS over Houston.
    This is a basic integration test of the calculation logic.
    """
    # Arrange: Mock get_satellites to return our test satellite
    mock_get_satellites.return_value = mock_iss_satellite
    
    # Act: Calculate passes for a known location (Houston, TX)
    # Using a location known to have frequent ISS passes.
    lat = 29.7604
    lon = -95.3698
    passes = calculate_passes(lat, lon)
    
    # Assert: Check that at least one pass was found.
    # The exact number can vary, so we just check for a non-empty list.
    assert isinstance(passes, list)
    assert len(passes) > 0, "Should find at least one pass for the ISS over Houston in a 24-hour window."
    
    # Check the structure and content of the first pass
    first_pass = passes[0]
    assert first_pass['name'] == 'ISS (ZARYA)'
    assert 'aos_time' in first_pass
    assert 'tca_time' in first_pass
    assert 'los_time' in first_pass
    assert 'max_elevation_deg' in first_pass
    assert first_pass['max_elevation_deg'] > 0
    
    # Check that the times are in chronological order
    assert first_pass['aos_time'] < first_pass['tca_time'] < first_pass['los_time']
