from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import List
import datetime
from skyfield.api import load, Topos

# Local imports
from satellite_service import calculate_passes, get_satellites
from simple_dem_service import calculate_horizon_from_directory
import numpy as np # Needed for np.all in main.py

app = FastAPI()


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
        print("Terrain analysis enabled. Searching for DEM tile.")
        horizon_profile = calculate_horizon_from_directory(
            lat=request.lat,
            lon=request.lon,
            alt_m=request.alt_m
        )
        if np.all(horizon_profile == 0):
            print("No suitable DEM file found. Proceeding without terrain analysis.")
        else:
            print("Horizon profile calculated.")

    passes_raw = calculate_passes(
        lat=request.lat,
        lon=request.lon,
        alt_m=request.alt_m,
        horizon_profile=horizon_profile
    )

    ts = load.timescale()
    now = ts.now()

    active_links = []
    
    # To get the satellite objects, we need to call this again.
    # This is inefficient and could be refactored.
    
    satellites = get_satellites()
    satellites_by_name = {sat.name: sat for sat in satellites}
    ground_station = Topos(latitude_degrees=request.lat, longitude_degrees=request.lon, elevation_m=request.alt_m)

    for p in passes_raw:
        if p["aos_time"].utc_datetime() <= now.utc_datetime() <= p["los_time"].utc_datetime():
            # This pass is currently active.
            current_sat = satellites_by_name.get(p["name"])

            if current_sat:
                difference = current_sat - ground_station
                topocentric = difference.at(now)
                alt, az, _ = topocentric.altaz()
                
                remaining_time = (p["los_time"].utc_datetime() - now.utc_datetime()).total_seconds()

                active_links.append(
                    CurrentLink(
                        name=p["name"],
                        remaining_time_seconds=remaining_time,
                        azimuth_deg=az.degrees,
                        elevation_deg=alt.degrees,
                    )
                )

    return active_links