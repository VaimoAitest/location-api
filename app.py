from fastapi import FastAPI, HTTPException
import requests
from math import radians, cos, sin, asin, sqrt

app = FastAPI(title="Location API", version="1.0.0")

HEADERS = {"User-Agent": "vaimoai-location-api/1.0 (contact: you@example.com)"}

# 1) Adresse -> Koordinaten (Nominatim)
def geocode(address: str):
    url = "https://nominatim.openstreetmap.org/search"
    try:
        r = requests.get(
            url,
            params={"format": "json", "q": address, "limit": 1},
            headers=HEADERS,
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Nominatim error: {str(e)}")

    if not data:
        # statt 500: sauberer Fehler
        raise HTTPException(
            status_code=422,
            detail=f"Adresse nicht gefunden. Bitte genauer schreiben (z.B. 'Bahnhofstrasse 6, Zürich'). Input: {address}"
        )

    return float(data[0]["lat"]), float(data[0]["lon"])


# 2) POIs (Overpass) - Restaurants im 500m Radius
def get_restaurants(lat: float, lon: float, radius_m: int = 500):
    query = f"""
    [out:json][timeout:25];
    (
      node["amenity"="restaurant"](around:{radius_m},{lat},{lon});
      way["amenity"="restaurant"](around:{radius_m},{lat},{lon});
      relation["amenity"="restaurant"](around:{radius_m},{lat},{lon});
    );
    out count;
    """

    try:
        r = requests.post(
            "https://overpass-api.de/api/interpreter",
            data=query.encode("utf-8"),
            headers=HEADERS,
            timeout=35,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        # Overpass ist manchmal langsam/überlastet -> trotzdem sauber antworten
        raise HTTPException(status_code=502, detail=f"Overpass error: {str(e)}")

    # out count liefert oft: {"elements":[{"type":"count","id":0,"tags":{"nodes":"X",...}}]}
    elements = data.get("elements", [])
    if elements and elements[0].get("type") == "count":
        tags = elements[0].get("tags", {})
        nodes = int(tags.get("nodes", 0))
        ways = int(tags.get("ways", 0))
        rels = int(tags.get("relations", 0))
        return nodes + ways + rels

    # fallback (falls out count nicht greift)
    return len(elements)


# 3) Distanz (Luftlinie) -> Zürich HB
def distance_to_zh_hb_m(lat: float, lon: float):
    hb_lat, hb_lon = 47.3779, 8.5402  # Zürich HB

    R = 6371
    dlat = radians(hb_lat - lat)
    dlon = radians(hb_lon - lon)
    a = sin(dlat / 2) ** 2 + cos(radians(lat)) * cos(radians(hb_lat)) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    km = R * c
    return round(km * 1000)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/location-score")
def location_score(address: str):
    lat, lon = geocode(address)
    restaurants = get_restaurants(lat, lon, radius_m=500)
    distance = distance_to_zh_hb_m(lat, lon)

    # simple Score (MVP)
    score = 100 - (distance / 100) + restaurants

    return {
        "input_address": address,
        "latitude": lat,
        "longitude": lon,
        "restaurants_500m": restaurants,
        "distance_to_ZH_HB_m": distance,
        "location_score": round(score, 1),
    }
