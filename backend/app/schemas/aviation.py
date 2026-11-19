from pydantic import BaseModel, ConfigDict


class AirportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    icao: str
    iata: str | None
    name: str
    city: str | None
    state: str | None
    type: str
    lat: float
    lon: float
    elevation_ft: int | None
    scheduled: bool


class WaypointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ident: str
    name: str | None
    kind: str
    freq_khz: int | None
    lat: float
    lon: float
