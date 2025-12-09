# System Patterns & Architecture

## 1. Horizon Masking Strategy (CRITICAL)
**Do NOT use direct ray-tracing for every time step.**
We utilize a "Horizon Mask" approach for performance:
1.  **Pre-computation:** For a given user location, compute the max terrain elevation for every degree of azimuth (0-360).
2.  **Runtime Check:** For every second of a satellite pass, compare `Satellite_Elevation` vs `Mask_Elevation[Satellite_Azimuth]`.
3.  **Link Condition:** Link is valid if:
    `Sat_El > Mask_El[Sat_Az]` AND `Sat_El > Min_Hardware_El`

## 2. Coordinate Systems
- **Backend:** All internal calculations in WGS84 (Lat/Lon/Alt).
- **Orbit Propagation:** Use TEME or GCRF frames internally, converted to Topocentric (Az/El) for the user.

## 3. Data Flow
Frontend (User Lat/Lon) -> Backend (FastAPI) -> Terrain Processor (Rasterio) -> Orbit Propagator (Skyfield) -> JSON Response -> Frontend (CesiumJS).