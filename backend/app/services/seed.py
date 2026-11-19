"""Seed airports + navaids from app/data/*.json, and import fixes from CSV.

CLI:
    python -m app.services.seed                       # seed airports/navaids
    python -m app.services.seed fixes.csv             # import waypoints/fixes CSV
    python -m app.services.seed --airways airways.csv # import ATS routes (airways)
Fixes CSV columns:   ident,name,kind,lat,lon   (kind e.g. FIX, RP, VOR, NDB)
Airways CSV columns: airway,seq,ident,lat,lon  (seq = order along the route)
"""
import csv
import json
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine
from app.models import aviation, user  # noqa: F401  (register tables)
from app.models.aviation import Airport, AirwayPoint, Waypoint

DATA = Path(__file__).resolve().parent.parent / "data"


def seed_if_empty(db: Session) -> None:
    if db.query(Airport).count() == 0:
        db.add_all(Airport(**a) for a in json.loads((DATA / "airports_in.json").read_text("utf-8")))
    if db.query(Waypoint).count() == 0:
        db.add_all(Waypoint(**w) for w in json.loads((DATA / "navaids_in.json").read_text("utf-8")))
    db.commit()


def import_fixes_csv(db: Session, path: str) -> int:
    n = 0
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ident = r["ident"].strip().upper()
            exists = db.query(Waypoint).filter_by(ident=ident, kind=r["kind"].strip().upper()).first()
            if exists:
                continue
            db.add(Waypoint(ident=ident, name=r.get("name") or None, kind=r["kind"].strip().upper(),
                            lat=float(r["lat"]), lon=float(r["lon"])))
            n += 1
    db.commit()
    return n


def import_airways_csv(db: Session, path: str) -> int:
    """Replaces every airway named in the file, so re-importing is safe."""
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(AirwayPoint(airway=r["airway"].strip().upper(), seq=int(r["seq"]),
                                    ident=r["ident"].strip().upper(),
                                    lat=float(r["lat"]), lon=float(r["lon"])))
    for name in {x.airway for x in rows}:
        db.query(AirwayPoint).filter_by(airway=name).delete()
    db.add_all(rows)
    db.commit()
    return len(rows)


if __name__ == "__main__":
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        if len(sys.argv) > 2 and sys.argv[1] == "--airways":
            print("Imported", import_airways_csv(s, sys.argv[2]), "airway points")
        elif len(sys.argv) > 1:
            print("Imported", import_fixes_csv(s, sys.argv[1]), "waypoints")
        else:
            seed_if_empty(s)
            print("Seeded.")
