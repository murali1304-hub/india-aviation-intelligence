"""ATS route parser: 'VABB BBB Q1 DPN VIDP' -> ordered points + legs + distances.

Pure Python (no DB imports). The router passes in a `repo` object with:
    repo.airport(icao)      -> dict | None         {icao,name,lat,lon}
    repo.waypoints(ident)   -> list[dict]          {ident,name,kind,lat,lon}
    repo.airway(name)       -> list[dict]          ordered [{ident,lat,lon}, ...]
"""
import math
import re

RE_AIRWAY = re.compile(r"^[A-Z]{1,2}\d{1,3}$")          # Q1, L301, W20, A791, UL425 ...
RE_LEVEL = re.compile(r"^[NKM]\d{3,4}[FAMS]\d{3,4}$")   # N0450F350
SKIP = {"DCT", "SID", "STAR", "IFR", "VFR"}


def haversine_nm(a, b) -> float:
    r = 3440.065
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp, dl = p2 - p1, math.radians(b["lon"] - a["lon"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def bearing(a, b) -> int:
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dl = math.radians(b["lon"] - a["lon"])
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return round((math.degrees(math.atan2(y, x)) + 360) % 360) or 360


def _point(ident, lat, lon, kind, name=None):
    return {"ident": ident, "name": name, "kind": kind, "lat": lat, "lon": lon}


def resolve_route(text: str, repo) -> dict:
    warnings: list[str] = []
    tokens = [t for t in re.split(r"[\s,]+", text.upper().strip()) if t]
    pts: list[dict] = []          # resolved points, each may carry "via" (airway used to reach it)
    pending: str | None = None    # airway waiting for its exit fix

    def nearest(cands, ref):
        if not ref:
            return cands[0]
        return min(cands, key=lambda c: haversine_nm(ref, c))

    for tok in tokens:
        if tok in SKIP or RE_LEVEL.match(tok):
            continue

        # 1) airport (4 letters)
        ap = repo.airport(tok) if len(tok) == 4 and tok.isalpha() else None
        if ap:
            p = _point(ap["icao"], ap["lat"], ap["lon"], "AIRPORT", ap["name"])
            _add(pts, p, pending, repo, warnings)
            pending = None
            continue

        # 2) airway
        if RE_AIRWAY.match(tok) and not repo.waypoints(tok):
            if not pts:
                warnings.append(f"Airway {tok} ignored: no entry point before it.")
            else:
                if pending:
                    warnings.append(f"Airway {pending} has no exit point before {tok}.")
                pending = tok
            continue

        # 3) waypoint / navaid / fix
        cands = repo.waypoints(tok)
        if not cands:
            warnings.append(f"'{tok}' not found in the database – skipped.")
            continue
        c = nearest(cands, pts[-1] if pts else None)
        p = _point(c["ident"], c["lat"], c["lon"], c["kind"], c.get("name"))
        _add(pts, p, pending, repo, warnings)
        pending = None

    if pending:
        warnings.append(f"Airway {pending} has no exit point – ignored.")

    # legs
    legs, total = [], 0.0
    for a, b in zip(pts, pts[1:]):
        d = haversine_nm(a, b)
        total += d
        legs.append({"from": a["ident"], "to": b["ident"], "via": b.get("via"),
                     "dist_nm": round(d, 1), "course": bearing(a, b),
                     "mode": b.get("mode", "direct")})
    airports = [p["ident"] for p in pts if p["kind"] == "AIRPORT"]
    return {"points": pts, "legs": legs, "total_nm": round(total, 1),
            "airports": airports, "warnings": warnings}


def _add(pts, p, pending, repo, warnings):
    """Append p; if an airway is pending, expand its intermediate fixes first."""
    if pending and pts:
        entry = pts[-1]
        seq = repo.airway(pending)
        if not seq:
            warnings.append(f"Airway {pending} is not in the database – drawn as a direct line "
                            f"{entry['ident']} → {p['ident']}. Import airway data to expand it.")
            p["via"], p["mode"] = pending, "direct-missing"
        else:
            idx = {s["ident"]: i for i, s in enumerate(seq)}
            if entry["ident"] not in idx or p["ident"] not in idx:
                miss = entry["ident"] if entry["ident"] not in idx else p["ident"]
                warnings.append(f"{miss} is not on airway {pending} – drawn as a direct line.")
                p["via"], p["mode"] = pending, "direct-missing"
            else:
                i, j = idx[entry["ident"]], idx[p["ident"]]
                chunk = seq[i:j + 1] if i <= j else seq[j:i + 1][::-1]
                for s in chunk[1:-1]:
                    pts.append({**_point(s["ident"], s["lat"], s["lon"], "FIX"), "via": pending, "mode": "airway"})
                p["via"], p["mode"] = pending, "airway"
    pts.append(p)
