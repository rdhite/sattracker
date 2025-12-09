from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import List
import datetime

# Local imports
from satellite_service import calculate_passes
from simple_dem_service import calculate_horizon_from_directory
import numpy as np # Needed for np.all in main.py

app = FastAPI()


class HealthResponse(BaseModel):
    status: str


class PredictionRequest(BaseModel):
    lat: float = Field(..., example=34.0522, description="Latitude of the ground station")
    lon: float = Field(..., example=-118.2437, description="Longitude of the ground station")
    alt_m: float = Field(0.0, example=233.0, description="Altitude of the ground station in meters")
    enable_terrain_analysis: bool = Field(False, description="Enable terrain obstruction analysis.")


class SatellitePass(BaseModel):
    name: str
    aos_time: datetime.datetime
    tca_time: datetime.datetime
    los_time: datetime.datetime
    max_elevation_deg: float


@app.get("/health", response_model=HealthResponse)
def read_health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/predict", response_model=List[SatellitePass])
def predict(request: PredictionRequest) -> List[SatellitePass]:
    """
    Predicts satellite passes for a given ground station.
    Optionally performs terrain analysis if a local DEM file is available.
    """
    horizon_profile = None
    if request.enable_terrain_analysis:
        print("Terrain analysis enabled. Searching for DEM tile.")
        # The simple_dem_service now handles finding the appropriate DEM from the directory
        horizon_profile = calculate_horizon_from_directory(
            lat=request.lat,
            lon=request.lon,
            alt_m=request.alt_m
        )
        if np.all(horizon_profile == 0): # Check if the returned horizon is flat
            print("No suitable DEM file found covering the observer's location. Proceeding without terrain analysis.")
        else:
            print("Horizon profile calculated from available DEM data.")

    passes_raw = calculate_passes(
        lat=request.lat,
        lon=request.lon,
        alt_m=request.alt_m,
        horizon_profile=horizon_profile
    )

    print(f"found {len(passes_raw)} passes")

    # Convert skyfield Time objects to python datetimes for Pydantic model
    response_passes = [
        SatellitePass(
            name=p["name"],
            aos_time=p["aos_time"].utc_datetime(),
            tca_time=p["tca_time"].utc_datetime(),
            los_time=p["los_time"].utc_datetime(),
            max_elevation_deg=p["max_elevation_deg"],
        )
        for p in passes_raw
    ]

    return response_passes