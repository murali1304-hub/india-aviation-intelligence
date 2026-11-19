from sqlalchemy import Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Airport(Base):
    __tablename__ = "airports"

    id: Mapped[int] = mapped_column(primary_key=True)
    icao: Mapped[str] = mapped_column(String(4), unique=True, index=True)
    iata: Mapped[str | None] = mapped_column(String(3), index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(150))
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(10), nullable=True)
    type: Mapped[str] = mapped_column(String(10))  # large / medium / small
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    elevation_ft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scheduled: Mapped[bool] = mapped_column(Boolean, default=False)


class Waypoint(Base):
    """Navaids (VOR/DME/NDB) and fixes / reporting points."""

    __tablename__ = "waypoints"

    id: Mapped[int] = mapped_column(primary_key=True)
    ident: Mapped[str] = mapped_column(String(10), index=True)
    name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)  # VOR, VOR-DME, NDB, DME, FIX, ...
    freq_khz: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)


class AirwayPoint(Base):
    """One significant point of an ATS route (airway), in order along the route."""

    __tablename__ = "airway_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    airway: Mapped[str] = mapped_column(String(10), index=True)  # Q1, L301, W20 ...
    seq: Mapped[int] = mapped_column(Integer)
    ident: Mapped[str] = mapped_column(String(10), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
