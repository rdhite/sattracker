# Technology Stack

## Backend (Python 3.13+)
- **Tooling:** uv for Python project, environment, and dependency management
- **Framework:** FastAPI
- **Orbit Propagation:** Skyfield (Do not use sgp4 directly unless optimized)
- **Terrain Data:** Rasterio (for reading GeoTIFF DEMs)
- **Math:** Numpy (for vectorized mask calculation)
- **Data Source:** Copernicus DEM (via AWS Open Data or local files)

## Frontend (React + TypeScript)
- **Build Tool:** Vite
- **Map Engine:** Resium (React wrapper for CesiumJS)
- **State Management:** Zustand or React Context
- **Satellite Viz:** satellite.js (for client-side interpolation/animation if needed)

## Constraint
- No heavy GIS servers (like GeoServer). We process raw DEM raster files directly in Python.