from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import List
import datetime
from skyfield.api import load, Topos

# Local imports
from satellite_service import TLEService, SatelliteService
from simple_dem_service import HorizonService
import numpy as np # Needed for np.all in main.py

app = FastAPI()

# Global services
tle_service = TLEService()
satellite_service = SatelliteService(tle_service)
horizon_service = HorizonService()


class CurrentLink(BaseModel):
    name: str
    remaining_time_seconds: float
    azimuth_deg: float
    elevation_deg: float


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
    aos_azimuth_deg: float
    aos_elevation_deg: float
    tca_time: datetime.datetime
    tca_azimuth_deg: float
    tca_elevation_deg: float
    los_time: datetime.datetime
    los_azimuth_deg: float
    los_elevation_deg: float
    max_elevation_deg: float
    max_elevation_azimuth_deg: float
    time_to_aos: float


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
        horizon_profile = horizon_service.get_horizon(
            lat=request.lat,
            lon=request.lon,
            alt_m=request.alt_m
        )
        if np.all(horizon_profile == 0):
            horizon_profile = None
            print("No suitable DEM file found. Proceeding without terrain analysis.")

    passes_raw = satellite_service.calculate_passes(
        lat=request.lat,
        lon=request.lon,
        alt_m=request.alt_m,
        horizon_profile=horizon_profile
    )

    print(f"found {len(passes_raw)} passes")

    # Convert skyfield Time objects to python datetimes for Pydantic model
    now = datetime.datetime.now(datetime.timezone.utc)
    response_passes = [
        SatellitePass(
            name=p["name"],
            aos_time=p["aos_time"].utc_datetime(),
            aos_azimuth_deg=p["aos_azimuth_deg"],
            aos_elevation_deg=p["aos_elevation_deg"],
            tca_time=p["tca_time"].utc_datetime(),
            tca_azimuth_deg=p["tca_azimuth_deg"],
            tca_elevation_deg=p["tca_elevation_deg"],
            los_time=p["los_time"].utc_datetime(),
            los_azimuth_deg=p["los_azimuth_deg"],
            los_elevation_deg=p["los_elevation_deg"],
            max_elevation_deg=p["max_elevation_deg"],
            max_elevation_azimuth_deg=p["max_elevation_azimuth_deg"],
            time_to_aos=(p["aos_time"].utc_datetime() - now).total_seconds(),
        )
        for p in passes_raw
    ]

    return response_passes


@app.post("/current-links", response_model=List[CurrentLink])
def current_links(request: PredictionRequest) -> List[CurrentLink]:
    """
    Determines if the operator is currently within any satellite linkages
    and provides details about those links.
    """
    horizon_profile = None
    if request.enable_terrain_analysis:
        horizon_profile = horizon_service.get_horizon(
            lat=request.lat,
            lon=request.lon,
            alt_m=request.alt_m
        )

    links_raw = satellite_service.get_active_links(
        lat=request.lat,
        lon=request.lon,
        alt_m=request.alt_m,
        horizon_profile=horizon_profile
    )

    return [
        CurrentLink(
            name=l["name"],
            remaining_time_seconds=l["remaining_time_seconds"],
            azimuth_deg=l["azimuth_deg"],
            elevation_deg=l["elevation_deg"],
        )
        for l in links_raw
    ]