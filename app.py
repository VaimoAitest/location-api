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



from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from typing import List

app = FastAPI()

# 1) Interaktive Karte (HTML)
@app.get("/map", response_class=HTMLResponse)
def map_page():
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>VaimoAI Preis-Karte</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <style>
    html, body, #map { height: 100%; margin: 0; }
    .price-label {
      background: white; border-radius: 16px; padding: 6px 10px;
      font-family: system-ui, -apple-system, Segoe UI, Roboto;
      font-weight: 700; box-shadow: 0 2px 8px rgba(0,0,0,.2);
      border: 1px solid rgba(0,0,0,.08);
      white-space: nowrap;
    }
  </style>
</head>
<body>
<div id="map"></div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
  const map = L.map('map').setView([47.3769, 8.5417], 11); // Zürich

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap'
  }).addTo(map);

  let layer;

  async function loadData() {
    const b = map.getBounds();
    const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(",");
    const res = await fetch(`/map/prices?bbox=${encodeURIComponent(bbox)}`);
    const geo = await res.json();

    if (layer) layer.remove();

    layer = L.geoJSON(geo, {
      pointToLayer: (feature, latlng) => {
        const p = feature.properties;
        const html = `<div class="price-label">${p.price} ${p.currency}</div>`;
        const icon = L.divIcon({ html, className: "", iconSize: [1,1] });
        return L.marker(latlng, { icon }).bindPopup(
          `<b>${p.title}</b><br/>${p.price} ${p.currency}<br/>${p.address}`
        );
      }
    }).addTo(map);
  }

  map.on('moveend zoomend', loadData);
  loadData();
</script>
</body>
</html>
"""

# 2) Daten-Endpoint (GeoJSON) – erst mal Dummy, später echte Comparables
@app.get("/map/prices")
def map_prices(bbox: str = Query(..., description="minLon,minLat,maxLon,maxLat")):
    # bbox wird hier nur akzeptiert; du kannst später damit filtern
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [8.5417, 47.3769]},
            "properties": {
                "price": 310, "currency": "CHF",
                "title": "Beispiel-Objekt Zürich",
                "address": "Zürich"
            }
        },
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [8.516, 47.391]},
            "properties": {
                "price": 463, "currency": "CHF",
                "title": "Beispiel-Objekt Kreis 10",
                "address": "Zürich"
            }
        },
    ]
    return JSONResponse({"type": "FeatureCollection", "features": features})
