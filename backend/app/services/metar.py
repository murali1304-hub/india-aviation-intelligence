"""METAR / TAF fetch + decoder (no third-party dependencies).

Source: NOAA Aviation Weather Center public API (no API key needed).
"""
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

AWC = "https://aviationweather.gov/api/data"
_cache: dict[str, tuple[float, object]] = {}
CACHE_SECONDS = 60

# ----------------------------------------------------------------- fetching


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "india-aviation-app/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode("utf-8", "replace").strip()


def fetch_raw(kind: str, icao: str) -> list[str]:
    """kind = 'metar' | 'taf'. Returns raw lines (newest first)."""
    key = f"{kind}:{icao}"
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]  # type: ignore[return-value]
    q = urllib.parse.urlencode({"ids": icao, "format": "raw", **({"hours": 3} if kind == "metar" else {})})
    text = _get(f"{AWC}/{kind}?{q}")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    _cache[key] = (time.time(), lines)
    return lines


# ----------------------------------------------------------------- decoding

DESCRIPTORS = {"MI": "shallow", "BC": "patches of", "PR": "partial", "DR": "low drifting",
               "BL": "blowing", "SH": "showers of", "TS": "thunderstorm", "FZ": "freezing"}
PHENOMENA = {"DZ": "drizzle", "RA": "rain", "SN": "snow", "SG": "snow grains", "IC": "ice crystals",
             "PL": "ice pellets", "GR": "hail", "GS": "small hail", "UP": "unknown precipitation",
             "BR": "mist", "FG": "fog", "FU": "smoke", "VA": "volcanic ash", "DU": "widespread dust",
             "SA": "sand", "HZ": "haze", "PY": "spray", "PO": "dust/sand whirls", "SQ": "squalls",
             "FC": "funnel cloud / tornado", "SS": "sandstorm", "DS": "duststorm"}
COVER = {"FEW": "Few", "SCT": "Scattered", "BKN": "Broken", "OVC": "Overcast"}
TREND = {"NOSIG": "No significant change expected", "BECMG": "Becoming", "TEMPO": "Temporarily",
         "NSW": "No significant weather", "CAVOK": "Ceiling and visibility OK"}

RE_WX = re.compile(r"^(RE)?(\+|-|VC)?(MI|BC|PR|DR|BL|SH|TS|FZ)?((?:DZ|RA|SN|SG|IC|PL|GR|GS|UP|BR|FG|FU|VA|DU|SA|HZ|PY|PO|SQ|FC|SS|DS)*)$")
RE_WIND = re.compile(r"^(VRB|\d{3})(\d{2,3})(?:G(\d{2,3}))?(KT|MPS)$")
RE_CLOUD = re.compile(r"^(FEW|SCT|BKN|OVC)(\d{3}|///)(CB|TCU)?$")
RE_TEMP = re.compile(r"^(M?\d{1,2})/(M?\d{1,2})?$")


def _signed(v: str) -> int:
    return -int(v[1:]) if v.startswith("M") else int(v)


def _wind(m) -> dict:
    d, spd, gst, unit = m.groups()
    f = 1.0 if unit == "KT" else 1.94384
    spd_kt, gst_kt = round(int(spd) * f), (round(int(gst) * f) if gst else None)
    if spd_kt == 0:
        text = "Calm"
    else:
        dirn = "Variable" if d == "VRB" else f"{d}°"
        text = f"{dirn} at {spd_kt} kt ({round(spd_kt * 1.852)} km/h)"
        if gst_kt:
            text += f", gusting {gst_kt} kt"
    return {"text": text, "dir": None if d == "VRB" else int(d), "speed_kt": spd_kt, "gust_kt": gst_kt}


def decode_groups(tokens: list[str]) -> dict:
    """Decode the groups shared by METAR/TAF: wind, visibility, weather, cloud."""
    out = {"wind": None, "visibility": None, "vis_m": None, "cavok": False,
           "weather": [], "clouds": [], "ceiling_ft": None, "other": []}
    i = 0
    while i < len(tokens):
        t = tokens[i]
        m = RE_WIND.match(t)
        if m:
            out["wind"] = _wind(m)
        elif re.match(r"^\d{3}V\d{3}$", t):
            if out["wind"]:
                out["wind"]["text"] += f", varying {t[:3]}°–{t[4:]}°"
        elif t == "CAVOK":
            out["cavok"] = True
            out["visibility"], out["vis_m"] = "10 km or more", 9999
            out["clouds"].append("No cloud below 5,000 ft, no significant weather")
        elif re.match(r"^\d{4}(NDV|N|NE|E|SE|S|SW|W|NW)?$", t) and out["vis_m"] is None:
            v = int(t[:4])
            out["vis_m"] = v
            out["visibility"] = "10 km or more" if v >= 9999 else (f"{v / 1000:g} km" if v >= 1000 else f"{v} m")
        elif t in ("NSC", "NCD", "SKC", "CLR"):
            out["clouds"].append({"NSC": "No significant cloud", "NCD": "No cloud detected",
                                  "SKC": "Sky clear", "CLR": "Clear"}[t])
        elif re.match(r"^VV(\d{3}|///)$", t):
            h = None if t[2:] == "///" else int(t[2:]) * 100
            out["clouds"].append(f"Vertical visibility {h:,} ft (sky obscured)" if h else "Sky obscured")
            if h is not None:
                out["ceiling_ft"] = min(h, out["ceiling_ft"] or h)
        elif RE_CLOUD.match(t):
            cov, h, ty = RE_CLOUD.match(t).groups()
            hft = None if h == "///" else int(h) * 100
            s = f"{COVER[cov]} at {hft:,} ft" if hft is not None else f"{COVER[cov]}"
            if ty:
                s += " – " + ("cumulonimbus" if ty == "CB" else "towering cumulus")
            out["clouds"].append(s)
            if cov in ("BKN", "OVC") and hft is not None:
                out["ceiling_ft"] = min(hft, out["ceiling_ft"] or hft)
        elif t in ("NSW",):
            out["weather"].append("No significant weather")
        elif t and RE_WX.match(t) and (RE_WX.match(t).group(3) or RE_WX.match(t).group(4)):
            re_, inten, desc, ph = RE_WX.match(t).groups()
            words = []
            if inten == "-":
                words.append("light")
            elif inten == "+":
                words.append("heavy")
            elif inten == "VC":
                words.append("in the vicinity:")
            if desc:
                words.append(DESCRIPTORS[desc])
            phs = [PHENOMENA[ph[k:k + 2]] for k in range(0, len(ph), 2)]
            if desc == "TS" and phs:
                words[-1] = "thunderstorm with"
            words += phs
            s = " ".join(words).replace(": ", ": ")
            if re_:
                s = "Recent: " + s
            out["weather"].append(s[0].upper() + s[1:])
        else:
            out["other"].append(t)
        i += 1
    return out


def flight_category(vis_m, ceiling_ft, cavok=False) -> str | None:
    if cavok:
        return "VFR"
    if vis_m is None and ceiling_ft is None:
        return None
    v = vis_m if vis_m is not None else 99999
    c = ceiling_ft if ceiling_ft is not None else 99999
    if v < 1600 or c < 500:
        return "LIFR"
    if v < 4800 or c < 1000:
        return "IFR"
    if v <= 8000 or c <= 3000:
        return "MVFR"
    return "VFR"


def _obs_time(ddhhmm: str) -> datetime:
    now = datetime.now(timezone.utc)
    dd, hh, mm = int(ddhhmm[:2]), int(ddhhmm[2:4]), int(ddhhmm[4:6])
    y, mo = now.year, now.month
    if dd > now.day + 1:  # belongs to previous month
        mo, y = (12, y - 1) if mo == 1 else (mo - 1, y)
    try:
        return datetime(y, mo, dd, hh, mm, tzinfo=timezone.utc)
    except ValueError:
        return now


def decode_metar(raw: str) -> dict:
    raw = raw.strip().rstrip("=")
    toks = raw.split()
    res = {"raw": raw, "type": "METAR", "icao": None, "time_utc": None, "age_min": None,
           "auto": False, "corrected": False, "temp_c": None, "dewpoint_c": None,
           "qnh_hpa": None, "altimeter_inhg": None, "rvr": [], "windshear": [], "trend": [], "remarks": None}
    if toks and toks[0] in ("METAR", "SPECI"):
        res["type"] = toks.pop(0)
    if toks and re.match(r"^[A-Z]{4}$", toks[0]):
        res["icao"] = toks.pop(0)
    if toks and re.match(r"^\d{6}Z$", toks[0]):
        t = _obs_time(toks.pop(0))
        res["time_utc"] = t.strftime("%d %b %Y %H:%M UTC")
        res["age_min"] = max(0, int((datetime.now(timezone.utc) - t).total_seconds() // 60))
    body, rmk = toks, None
    if "RMK" in toks:
        k = toks.index("RMK")
        body, rmk = toks[:k], " ".join(toks[k + 1:])
    # split off trend section
    trend_i = next((k for k, t in enumerate(body) if t in ("NOSIG", "BECMG", "TEMPO")), None)
    trend = body[trend_i:] if trend_i is not None else []
    body = body[:trend_i] if trend_i is not None else body
    rest = []
    for t in body:
        if t == "AUTO":
            res["auto"] = True
        elif t == "COR":
            res["corrected"] = True
        elif re.match(r"^R\d{2}[LCR]?/", t):
            res["rvr"].append(_decode_rvr(t))
        elif t.startswith("WS"):
            res["windshear"].append(t)
        elif RE_TEMP.match(t):
            a, b = RE_TEMP.match(t).groups()
            res["temp_c"] = _signed(a)
            res["dewpoint_c"] = _signed(b) if b else None
        elif re.match(r"^Q\d{4}$", t):
            res["qnh_hpa"] = int(t[1:])
        elif re.match(r"^A\d{4}$", t):
            res["altimeter_inhg"] = int(t[1:]) / 100
            res["qnh_hpa"] = round(int(t[1:]) / 100 * 33.8639)
        else:
            rest.append(t)
    res.update(decode_groups(rest))
    res["trend"] = _decode_trend(trend)
    res["remarks"] = rmk
    res["flight_category"] = flight_category(res["vis_m"], res["ceiling_ft"], res["cavok"])
    if res["temp_c"] is not None and res["dewpoint_c"] is not None:
        res["spread_c"] = res["temp_c"] - res["dewpoint_c"]
    return res


def _decode_rvr(t: str) -> str:
    m = re.match(r"^R(\d{2}[LCR]?)/([PM]?)(\d{4})(?:V([PM]?)(\d{4}))?([UDN])?$", t)
    if not m:
        return t
    rwy, p, v, p2, v2, tr = m.groups()
    s = f"RWY {rwy}: {'above ' if p == 'P' else 'below ' if p == 'M' else ''}{int(v)} m"
    if v2:
        s += f" varying to {int(v2)} m"
    s += {"U": " (improving)", "D": " (worsening)", "N": " (no change)"}.get(tr, "")
    return s


def _decode_trend(tokens: list[str]) -> list[str]:
    if not tokens:
        return []
    out, cur = [], []

    def flush():
        if not cur:
            return
        head = TREND.get(cur[0], cur[0])
        if cur[0] == "NOSIG":
            out.append(head)
            return
        d = decode_groups([t for t in cur[1:] if not re.match(r"^(FM|TL|AT)\d{4}$", t)])
        bits = [d["wind"]["text"]] if d["wind"] else []
        if d["visibility"]:
            bits.append("visibility " + d["visibility"])
        bits += d["weather"] + d["clouds"] + d["other"]
        out.append(f"{head}: " + "; ".join(bits) if bits else head)

    for t in tokens:
        if t in ("NOSIG", "BECMG", "TEMPO"):
            flush()
            cur = [t]
        else:
            cur.append(t)
    flush()
    return out


# --------------------------------------------------------------------- TAF


def _dh(s: str) -> str:
    """'1912' -> '19th 12:00Z'"""
    return f"{s[:2]}th {s[2:4]}:00Z" if len(s) == 4 else s


def decode_taf(raw: str) -> dict:
    raw = " ".join(raw.replace("\n", " ").split()).rstrip("=")
    toks = raw.split()
    head = {"raw": raw, "icao": None, "issued": None, "valid": None, "amended": False, "periods": []}
    if toks and toks[0] == "TAF":
        toks.pop(0)
    if toks and toks[0] in ("AMD", "COR"):
        head["amended"] = toks.pop(0) == "AMD"
    if toks and re.match(r"^[A-Z]{4}$", toks[0]):
        head["icao"] = toks.pop(0)
    if toks and re.match(r"^\d{6}Z$", toks[0]):
        t = toks.pop(0)
        head["issued"] = f"{t[:2]}th {t[2:4]}:{t[4:6]}Z"
    if toks and re.match(r"^\d{4}/\d{4}$", toks[0]):
        a, b = toks.pop(0).split("/")
        head["valid"] = f"{_dh(a)} → {_dh(b)}"
    groups: list[tuple[str, list[str]]] = [("Initial forecast", [])]
    for t in toks:
        if re.match(r"^FM\d{6}$", t):
            groups.append((f"From {t[2:4]}th {t[4:6]}:{t[6:8]}Z", []))
        elif t in ("BECMG", "TEMPO", "INTER") or re.match(r"^PROB\d{2}$", t):
            groups.append((t, []))
        elif re.match(r"^\d{4}/\d{4}$", t) and groups[-1][0] in ("BECMG", "TEMPO", "INTER") or \
                (re.match(r"^\d{4}/\d{4}$", t) and groups[-1][0].startswith("PROB")):
            a, b = t.split("/")
            lab = groups[-1][0]
            names = {"BECMG": "Becoming", "TEMPO": "Temporarily", "INTER": "Intermittently"}
            lab = names.get(lab, f"{lab[4:]}% probability")
            groups[-1] = (f"{lab}, {_dh(a)} → {_dh(b)}", [])
        elif re.match(r"^T[XN]M?\d{2}/\d{4}Z$", t):
            m = re.match(r"^T([XN])(M?\d{2})/(\d{2})(\d{2})Z$", t)
            groups[-1][1].append(f"{'Max' if m.group(1) == 'X' else 'Min'} temp {_signed(m.group(2))}°C at {m.group(3)}th {m.group(4)}:00Z")
        else:
            groups[-1][1].append(t)
    for label, tk in groups:
        d = decode_groups([x for x in tk if not x.startswith(("Max", "Min"))])
        extra = [x for x in tk if x.startswith(("Max", "Min"))]
        p = {"label": label, "wind": d["wind"]["text"] if d["wind"] else None,
             "visibility": d["visibility"], "weather": d["weather"], "clouds": d["clouds"],
             "other": d["other"] + extra,
             "flight_category": flight_category(d["vis_m"], d["ceiling_ft"], d["cavok"])}
        head["periods"].append(p)
    return head


# --------------------------------------------------------------- public API


def get_weather(icao: str) -> dict:
    icao = icao.upper()
    result = {"icao": icao, "metar": None, "taf": None, "errors": []}
    try:
        lines = fetch_raw("metar", icao)
        if lines:
            result["metar"] = decode_metar(lines[0])
            result["metar_history"] = lines[1:4]
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        result["errors"].append(f"METAR source unreachable: {e}")
    try:
        lines = fetch_raw("taf", icao)
        if lines:
            result["taf"] = decode_taf(" ".join(lines[0:1]))
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        result["errors"].append(f"TAF source unreachable: {e}")
    return result
