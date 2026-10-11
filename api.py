"""Request routing shared by the Lambda handler and the local dev server."""
import core


def handle(path, qs):
    """Returns (status, json-serialisable body)."""
    try:
        if path == "/api/search":
            return 200, core.search_places(qs.get("q", ""))
        if path == "/api/report":
            campus = {k: int(qs[k]) for k in ("students", "tank_litres", "supply_lph") if qs.get(k)}
            return 200, core.report(
                lat=float(qs.get("lat", core.LAT)), lon=float(qs.get("lon", core.LON)),
                name=qs.get("name") or "VIT Bhopal", date=qs.get("date") or None,
                day=int(qs.get("day", 0)), campus=campus)
    except Exception as e:
        return 502, {"error": str(e)}
    return 404, {"error": "not found"}
