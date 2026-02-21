from fastapi import FastAPI
import requests

app = FastAPI()

# 1️⃣ Adresse → Koordinaten (Nominatim)
def geocode(address):
    url = f"https://nominatim.openstreetmap.org/search?format=json&q={address}"
    res = requests.get(url, headers={"User-Agent": "realestate-app"}).json()
    return float(res[0]["lat"]), float(res[0]["lon"])


# 2️⃣ Restaurants im 500m Radius (Overpass API)
def get_restaurants(lat, lon):
    query = f"""
    [out:json];
    (
      node["amenity"="restaurant"](around:500,{lat},{lon});
    );
    out;
    """
    res = requests.post(
        "https://overpass-api.de/api/interpreter",
        data=query
    ).json()
    return len(res["elements"])


# 3️⃣ Distanz (OpenRouteService – optional)
def walking_distance(lat, lon):
    # einfache Luftlinie als MVP
    hb_lat = 47.3779
    hb_lon = 8.5402
    
    from math import radians, cos, sin, asin, sqrt

    def haversine(lat1, lon1, lat2, lon2):
        R = 6371
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        return R * c

    distance_km = haversine(lat, lon, hb_lat, hb_lon)
    return round(distance_km * 1000)


@app.get("/location-score")
def location_score(address: str):

    lat, lon = geocode(address)
    restaurants = get_restaurants(lat, lon)
    distance = walking_distance(lat, lon)

    score = 100 - (distance / 100) + restaurants

    return {
        "latitude": lat,
        "longitude": lon,
        "restaurants_500m": restaurants,
        "distance_to_ZH_HB_m": distance,
        "location_score": round(score, 1)
    }
