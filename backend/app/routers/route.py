from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.aviation import Airport, AirwayPoint, Waypoint
from app.services.route import resolve_route
from app.services.security import get_current_user

router = APIRouter(prefix="/route", tags=["ATS Route"], dependencies=[Depends(get_current_user)])


class DbRepo:
    def __init__(self, db: Session):
        self.db = db

    def airport(self, icao):
        a = self.db.query(Airport).filter(Airport.icao == icao).first()
        return {"icao": a.icao, "name": a.name, "lat": a.lat, "lon": a.lon} if a else None

    def waypoints(self, ident):
        rows = self.db.query(Waypoint).filter(Waypoint.ident == ident).all()
        return [{"ident": w.ident, "name": w.name, "kind": w.kind, "lat": w.lat, "lon": w.lon} for w in rows]

    def airway(self, name):
        rows = self.db.query(AirwayPoint).filter(AirwayPoint.airway == name).order_by(AirwayPoint.seq).all()
        return [{"ident": r.ident, "lat": r.lat, "lon": r.lon} for r in rows]


@router.get("")
def plot_route(route: str = Query(..., min_length=3, description="e.g. 'VABB BBB Q1 DPN VIDP'"),
               db: Session = Depends(get_db)):
    result = resolve_route(route, DbRepo(db))
    if len(result["points"]) < 2:
        raise HTTPException(422, "Need at least two valid points. " + " ".join(result["warnings"]))
    return result


@router.get("/airways")
def list_airways(db: Session = Depends(get_db)):
    """Which airways are loaded in the database."""
    rows = db.query(AirwayPoint.airway).distinct().order_by(AirwayPoint.airway).all()
    return [r[0] for r in rows]
