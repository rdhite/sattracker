# Current Task: Phase 3 - Terrain Obstruction Analysis

1.  **DEM Data Service (`dem_service.py`):** (COMPLETED)
    *   Add `dem_data_dir` to `config.py` to specify where DEM files are stored. (COMPLETED)
    *   Create a function `get_tile_filename(lat, lon)` that generates the standard filename for a DEM tile based on its coordinates. (COMPLETED)
    *   Create a function `find_dem_tile_path(lat, lon)` that uses the above to find the full, verifiable path to a local DEM file, returning `None` if it doesn't exist. (COMPLETED)

2.  **Horizon Calculation:** (COMPLETED)
    *   In `dem_service.py`, create a function `calculate_horizon(dem_path, lat, lon)`. (COMPLETED)
    *   It will use `rasterio` to open the DEM file. (COMPLETED)
    *   It will use a vectorized `numpy` approach (no loops) to perform ray-tracing for a 360-degree view from the observer's location. (COMPLETED)
    *   The function will return a horizon profile (e.g., a list of `(azimuth, elevation)` tuples). (COMPLETED)

3.  **Filter Passes by Horizon:** (COMPLETED)
    *   In `satellite_service.py`, update `calculate_passes` to accept an optional `horizon_profile`. (COMPLETED)
    *   If a profile is provided, check the satellite's elevation against the terrain horizon at multiple points during each pass. (COMPLETED)
    *   Recalculate the true, unobstructed AOS and LOS times for each pass. (COMPLETED)

4.  **API Integration (`main.py`):** (COMPLETED)
    *   Add an optional `enable_terrain_analysis: bool = False` flag to the `PredictionRequest` model in `main.py`. (COMPLETED)
    *   If the flag is true, the `/predict` endpoint will call the DEM service, calculate the horizon, and pass it to the satellite service. (COMPLETED)
    *   Gracefully handle cases where no DEM data is available for a location by proceeding without terrain analysis. (COMPLETED)

5.  **Unit Tests:** (COMPLETED)
    *   Create a simple, programmatic GeoTIFF file with a predictable shape (e.g., a cone) as a test asset. (COMPLETED)
    *   Write a unit test for `calculate_horizon` that asserts the output matches the expected profile for the test asset. (COMPLETED)

**Next Steps:**
*   Perform full integration testing of the API with the downloaded DEM data to verify the terrain obstruction analysis.