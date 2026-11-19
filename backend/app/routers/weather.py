import re

from fastapi import APIRouter, Depends, HTTPException

from app.services.metar import get_weather
from app.services.security import get_current_user

router = APIRouter(prefix="/weather", tags=["Weather"], dependencies=[Depends(get_current_user)])


@router.get("/{icao}")
def aerodrome_weather(icao: str):
    """Decoded METAR + TAF for an aerodrome (source: NOAA Aviation Weather Center)."""
    icao = icao.upper()
    if not re.fullmatch(r"[A-Z]{4}", icao):
        raise HTTPException(422, "ICAO code must be 4 letters")
    return get_weather(icao)
