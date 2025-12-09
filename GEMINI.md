# Project: SATCOM Tracker

## Project Overview
This project is a SATCOM tracker with terrain obstruction analysis capabilities. The backend is a Python FastAPI application that predicts satellite passes over a given ground station. It integrates with `skyfield` for orbit propagation and `rasterio` for Digital Elevation Model (DEM) data processing to calculate terrain horizons. The frontend is currently a placeholder, but it is intended to provide a user interface for these capabilities.

## Technologies Used
*   **Backend:** Python 3.13+, FastAPI, uvicorn, Pydantic, NumPy, Skyfield, Rasterio, Requests, pytest.
*   **Frontend:** (Not yet implemented, but indicated by `frontend/` directory).
*   **Project Management:** `uv` (for Python environment and dependency management).

## Building and Running

### Backend
1.  **Navigate to the backend directory:**
    ```bash
    cd backend
    ```
2.  **Install dependencies:** This project uses `uv` for dependency management.
    ```bash
    uv pip install -e .
    ```
3.  **Run the FastAPI application:**
    ```bash
    uv run uvicorn main:app --host 0.0.0.0 --port 8000
    ```
    The API will be available at `http://localhost:8000`.

## Testing

### Backend
1.  **Navigate to the backend directory:**
    ```bash
    cd backend
    ```
2.  **Run tests with `pytest`:**
    ```bash
    uv run pytest
    ```

## Development Conventions
*   **Python Version:** Requires Python 3.13 or newer.
*   **Dependency Management:** `uv` is used for managing Python dependencies.
*   **Backend Framework:** FastAPI for API development.
*   **Configuration:** Pydantic-settings for managing application configurations via environment variables (`.env` file).
*   **Terrain Data:** Copernicus DEM data (either 10m or 30m resolution, specifically `Copernicus_DSM_10_NXX_00_WXXX_00.tif` filename format) is expected in the `backend/dem_data` directory for terrain obstruction analysis.
*   **Testing:** `pytest` is used for unit and integration testing.
