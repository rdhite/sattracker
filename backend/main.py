from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
import datetime


class HealthResponse(BaseModel):
    status: str


class PredictionRequest(BaseModel):
    lat: float
    lon: float


class TimeWindow(BaseModel):
    start_time: datetime.datetime
    end_time: datetime.datetime


app = FastAPI()


@app.get("/health", response_model=HealthResponse)
def read_health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/predict", response_model=List[TimeWindow])
def predict(request: PredictionRequest) -> List[TimeWindow]:
    """
    Predicts time windows for a valid link.
    For now, returns a mock time window.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    start_window = now + datetime.timedelta(hours=1)
    end_window = now + datetime.timedelta(hours=2)

    return [TimeWindow(start_time=start_window, end_time=end_window)]