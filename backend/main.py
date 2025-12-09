from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import List
import datetime

# Local imports
from satellite_service import calculate_passes
from dem_service import find_dem_tile_path, calculate_horizon

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
        dem_path = find_dem_tile_path(lat=request.lat, lon=request.lon)
        
        if dem_path:
            print(f"Found DEM tile: {dem_path}. Calculating horizon profile.")
            horizon_profile = calculate_horizon(
                dem_path=dem_path,
                lat=request.lat,
                lon=request.lon,
                alt_m=request.alt_m
            )
        else:
            print("No local DEM tile found for the given coordinates. Proceeding without terrain analysis.")

    passes_raw = calculate_passes(
        lat=request.lat,
        lon=request.lon,
        alt_m=request.alt_m,
        horizon_profile=horizon_profile
    )

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