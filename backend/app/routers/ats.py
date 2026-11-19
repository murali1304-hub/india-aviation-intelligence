from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.aviation import Airport, Waypoint
from app.schemas.aviation import AirportOut, WaypointOut
from app.services.security import get_current_user

router = APIRouter(prefix="/ats", tags=["ATS Map"], dependencies=[Depends(get_current_user)])


@router.get("/airports", response_model=list[AirportOut])
def list_airports(
    q: str | None = Query(None, description="Search ICAO / IATA / name / city"),
    type: str | None = Query(None, pattern="^(large|medium|small)$"),
    scheduled: bool | None = None,
    limit: int = Query(500, le=1000),
    db: Session = Depends(get_db),
):
    qs = db.query(Airport)
    if q:
        like = f"%{q}%"
        qs = qs.filter(or_(Airport.icao.ilike(like), Airport.iata.ilike(like),
                           Airport.name.ilike(like), Airport.city.ilike(like)))
    if type:
        qs = qs.filter(Airport.type == type)
    if scheduled is not None:
        qs = qs.filter(Airport.scheduled == scheduled)
    return qs.order_by(Airport.icao).limit(limit).all()


@router.get("/airports/{icao}", response_model=AirportOut)
def get_airport(icao: str, db: Session = Depends(get_db)):
    a = db.query(Airport).filter(Airport.icao == icao.upper()).first()
    if not a:
        raise HTTPException(404, "Airport not found")
    return a


@router.get("/waypoints", response_model=list[WaypointOut])
def list_waypoints(
    q: str | None = None,
    kind: str | None = Query(None, description="VOR, VOR-DME, DME, NDB, TACAN, FIX, RP ..."),
    limit: int = Query(1000, le=3000),
    db: Session = Depends(get_db),
):
    qs = db.query(Waypoint)
    if q:
        like = f"%{q}%"
        qs = qs.filter(or_(Waypoint.ident.ilike(like), Waypoint.name.ilike(like)))
    if kind:
        qs = qs.filter(Waypoint.kind == kind.upper())
    return qs.order_by(Waypoint.ident).limit(limit).all()


@router.get("/geojson")
def geojson(db: Session = Depends(get_db)):
    """Airports + waypoints as one GeoJSON FeatureCollection (for the map)."""
    feats = []
    for a in db.query(Airport).all():
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [a.lon, a.lat]},
            "properties": {"layer": "airport", "id": a.icao, "iata": a.iata, "name": a.name,
                           "city": a.city, "class": a.type, "elev": a.elevation_ft,
                           "scheduled": a.scheduled},
        })
    for w in db.query(Waypoint).all():
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [w.lon, w.lat]},
            "properties": {"layer": "waypoint", "id": w.ident, "name": w.name,
                           "class": w.kind, "freq": w.freq_khz},
        })
    return {"type": "FeatureCollection", "features": feats}
