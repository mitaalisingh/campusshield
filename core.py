"""CampusShield core: real hourly weather -> heat-stress, water clock, admin actions.

Pure stdlib so the same code runs locally and inside AWS Lambda.
"""
import json
import math
import os
import urllib.parse
import urllib.request

# VIT Bhopal (Kothri Kalan, Sehore)
LAT, LON = 23.08, 76.85
TZ = "Asia/Kolkata"
HOURLY = "temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation"

DEFAULT_CAMPUS = {
    "students": 4000,          # hostel residents
    "tank_litres": 600_000,    # total overhead storage
    "supply_lph": 18_000,      # municipal/borewell inflow, litres per hour (when running)
    "supply_hours": [5, 6, 7, 8, 9, 17, 18, 19],  # hours the pumps/supply run
    "base_lpcd": 90,           # litres per student per day at mild temperature
}


def _get(url):
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.load(r)


def _rows(h, offset=0):
    return [
        {"hour": i, "t": h["temperature_2m"][offset + i], "rh": h["relative_humidity_2m"][offset + i],
         "wind": h["wind_speed_10m"][offset + i], "sr": h["shortwave_radiation"][offset + i] or 0.0}
        for i in range(24)
    ]


def fetch_days(lat, lon, date=None):
    """Returns (list of day-labels, list of 24-row weather days).
    date=None -> 7-day forecast from today; date='YYYY-MM-DD' -> that single past day (replay)."""
    q = {"latitude": lat, "longitude": lon, "hourly": HOURLY, "timezone": TZ}
    if date:
        q.update(start_date=date, end_date=date)
        url = "https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode(q)
    else:
        q.update(forecast_days=7)
        url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(q)
    h = _get(url)["hourly"]
    n = len(h["time"]) // 24
    return [h["time"][d * 24][:10] for d in range(n)], [_rows(h, d * 24) for d in range(n)]


def search_places(query):
    """Find a campus by name via OpenStreetMap Nominatim (https://nominatim.org, data (c) OSM contributors)."""
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": query, "format": "json", "limit": 6, "countrycodes": "in"})
    req = urllib.request.Request(url, headers={"User-Agent": "CampusShield-hackathon/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        res = json.load(r)
    return [{"name": p["display_name"], "lat": round(float(p["lat"]), 4), "lon": round(float(p["lon"]), 4)}
            for p in res]


# ---------- heat stress ----------
def wbgt(t, rh, sr):
    """Outdoor WBGT estimate: BoM approximation (temp+humidity) plus a solar-load term."""
    e = rh / 100 * 6.105 * math.exp(17.27 * t / (237.7 + t))  # vapour pressure, hPa
    return 0.567 * t + 0.393 * e + 3.94 + 2.5 * (sr / 1000)


def level(w):
    """Thresholds follow the standard WBGT heat flags (US Army / ACSM): 82, 85, 88 degF."""
    if w < 27.8: return "safe"
    if w < 29.4: return "caution"
    if w < 31.1: return "danger"
    return "extreme"


def loo(t, rh, wind):
    return t >= 40 and rh <= 30 and wind >= 15


def corridor_feel(t, sr, wind):
    """Heat felt on an unshaded concrete walkway: air temp + radiant gain from the surface."""
    return t + 0.012 * sr * (1 - 0.01 * min(wind, 30))


def top_floor_room(temps, hour):
    """Non-AC top-floor room: roof stores heat, so it lags the outdoors by ~3h and stays warmer at night."""
    lagged = [temps[(hour - k) % 24] for k in range(0, 6)]
    return sum(lagged) / len(lagged) + 3.5


def hourly_analysis(wx):
    temps = [x["t"] for x in wx]
    out = []
    for x in wx:
        w = wbgt(x["t"], x["rh"], x["sr"])
        out.append({
            **x,
            "wbgt": round(w, 1),
            "level": level(w),
            "loo": loo(x["t"], x["rh"], x["wind"]),
            "corridor": round(corridor_feel(x["t"], x["sr"], x["wind"]), 1),
            "room": round(top_floor_room(temps, x["hour"]), 1),
        })
    return out


# ---------- water ----------
def water_clock(hours, campus):
    """Hour-by-hour tank simulation. Heat raises per-student draw (cooling, bathing, coolers)."""
    cap = campus["tank_litres"]
    level_l = cap * 0.55  # tanks start the day 55% full
    series, dry_hour = [], None
    # shape of daily demand: morning + evening peaks
    shape = [0.2, 0.1, 0.1, 0.1, 0.2, 0.6, 1.6, 2.0, 1.6, 1.0, 0.8, 0.9,
             1.0, 1.0, 0.9, 0.9, 1.0, 1.3, 1.6, 1.4, 1.1, 0.8, 0.5, 0.3]
    norm = sum(shape)
    for hr in hours:
        heat = 1 + 0.55 * max(0.0, min(1.0, (hr["t"] - 30) / 15))
        draw = campus["students"] * campus["base_lpcd"] * heat * shape[hr["hour"]] / norm
        inflow = campus["supply_lph"] if hr["hour"] in campus["supply_hours"] else 0
        level_l = max(0.0, min(cap, level_l + inflow - draw))
        series.append({"hour": hr["hour"], "pct": round(100 * level_l / cap, 1),
                       "draw": round(draw), "heat_factor": round(heat, 2)})
        if dry_hour is None and level_l <= 0.05 * cap:
            dry_hour = hr["hour"]
    day_demand = sum(s["draw"] for s in series)
    day_supply = campus["supply_lph"] * len(campus["supply_hours"])
    return {"series": series, "dry_hour": dry_hour,
            "deficit_litres": max(0, round(day_demand - day_supply)),
            "tankers_needed": max(0, math.ceil((day_demand - day_supply) / 10_000))}


# ---------- decisions ----------
def fmt(h): return f"{h % 12 or 12}:00 {'AM' if h < 12 else 'PM'}"


def safe_windows(hours, lo=6, hi=20):
    ok = [h["hour"] for h in hours if lo <= h["hour"] <= hi and h["wbgt"] < 29.4]
    runs, cur = [], []
    for x in ok:
        if cur and x != cur[-1] + 1:
            runs.append(cur); cur = []
        cur.append(x)
    if cur: runs.append(cur)
    return [(r[0], r[-1] + 1) for r in runs]


def actions(hours, water):
    acts = []
    worst = max(hours, key=lambda h: h["wbgt"])
    bad = [h["hour"] for h in hours if 8 <= h["hour"] <= 18 and h["level"] in ("danger", "extreme")]
    wins = safe_windows(hours)
    if wins:
        win_txt = " and ".join(f"{fmt(a)}–{fmt(b)}" for a, b in wins) + " (WBGT below the 29.4 danger line)"
    else:
        a = min(range(6, 18), key=lambda s: sum(hours[s + k]["wbgt"] for k in range(3)))
        win_txt = f"{fmt(a)}–{fmt(a + 3)} (no fully safe window today; this is the least dangerous, so keep it short with water breaks)"
    if bad:
        acts.append({"sev": "critical" if worst["level"] == "extreme" else "high",
                     "title": "Move classes and exams out of the dangerous hours",
                     "why": f"Heat stress is {worst['level']} (WBGT {worst['wbgt']}°C) peaking near {fmt(worst['hour'])}; "
                            f"{len(bad)} daytime hours are danger or worse.",
                     "do": f"Hold exams and outdoor activity only in: {win_txt}. "
                           f"Otherwise use air-conditioned halls or go online between {fmt(bad[0])} and {fmt(bad[-1] + 1)}."})
    night = [h for h in hours if h["hour"] >= 21 or h["hour"] <= 4]
    hot_nights = [h for h in night if h["room"] >= 35]
    if hot_nights:
        peak = max(hot_nights, key=lambda h: h["room"])
        acts.append({"sev": "high",
                     "title": "Open cool sleeping zones tonight",
                     "why": f"Top-floor non-AC rooms are estimated at {peak['room']}°C at {fmt(peak['hour'])} "
                            f"with the roof still releasing stored heat.",
                     "do": "Keep the central library, labs and auditorium open overnight with seating, fans and water. "
                           "Allow students to move there and tell wardens to do hourly welfare rounds."})
    if any(h["loo"] for h in hours):
        acts.append({"sev": "high", "title": "Loo (hot dry wind) alert",
                     "why": "Temperature ≥40°C with dry air and strong wind: sweat evaporates instantly so dehydration is silent.",
                     "do": "Cancel outdoor events, keep water points staffed, and add ORS and drinking water at hostel gates."})
    if water["dry_hour"] is not None:
        acts.append({"sev": "critical", "title": "Water: tanks run dry today",
                     "why": f"At today's heat-driven usage the tanks hit empty around {fmt(water['dry_hour'])}.",
                     "do": f"Order about {water['tankers_needed']} tankers (10,000 L each) before 8 AM, "
                           f"prioritise hostel blocks, and run pumps for the extra hours."})
    elif water["deficit_litres"] > 0:
        acts.append({"sev": "medium", "title": "Water: daily deficit forecast",
                     "why": f"Demand exceeds supply by about {water['deficit_litres']:,} litres today.",
                     "do": f"Pre-book {water['tankers_needed']} tankers so taps never go dry."})
    if not acts:
        acts.append({"sev": "ok", "title": "Conditions are manageable",
                     "why": "Heat stress and water levels are within safe limits.",
                     "do": "Carry on as normal and keep water points stocked."})
    order = {"critical": 0, "high": 1, "medium": 2, "ok": 3}
    return sorted(acts, key=lambda a: order[a["sev"]])


def narrate(report):
    """Optional: Bedrock rewrites the action list as a short note to the Director. Falls back silently."""
    model = os.environ.get("BEDROCK_MODEL_ID")
    if not model:
        return None
    try:
        import boto3
        brt = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "ap-south-1"))
        prompt = ("You advise the Director of a hostel campus in Bhopal. Using these facts, write a 4-sentence "
                  "plain-language briefing with the most urgent decision first. No jargon.\n"
                  + json.dumps({"actions": report["actions"], "peak_wbgt": report["summary"]["peak_wbgt"]}))
        r = brt.converse(modelId=model, messages=[{"role": "user", "content": [{"text": prompt}]}])
        return r["output"]["message"]["content"][0]["text"]
    except Exception:
        return None


def day_outlook(label, hours):
    peak = max(hours, key=lambda h: h["wbgt"])
    wins = safe_windows(hours)
    return {"date": label, "peak_temp": max(h["t"] for h in hours), "peak_wbgt": peak["wbgt"],
            "level": peak["level"], "loo": any(h["loo"] for h in hours),
            "safe_windows": [[a, b] for a, b in wins]}


def report(lat=LAT, lon=LON, name="VIT Bhopal", date=None, day=0, campus=None):
    campus = {**DEFAULT_CAMPUS, **(campus or {})}
    labels, days = fetch_days(lat, lon, date)
    analysed = [hourly_analysis(d) for d in days]
    day = max(0, min(day, len(days) - 1))
    hours = analysed[day]
    water = water_clock(hours, campus)
    peak = max(hours, key=lambda h: h["wbgt"])
    rep = {
        "mode": "replay" if date else "live",
        "place": {"name": name, "lat": lat, "lon": lon},
        "date": labels[day],
        "day": day,
        "campus": campus,
        "outlook": [day_outlook(l, a) for l, a in zip(labels, analysed)],
        "hours": hours,
        "water": water,
        "summary": {"peak_wbgt": peak["wbgt"], "peak_hour": peak["hour"], "peak_level": peak["level"],
                    "peak_temp": max(h["t"] for h in hours),
                    "peak_corridor": max(h["corridor"] for h in hours),
                    "peak_room": max(h["room"] for h in hours)},
    }
    rep["actions"] = actions(hours, water)
    rep["briefing"] = narrate(rep)
    return rep
