# app.py - UPDATED CODE WITH PRECISE HOSPITAL/CLINIC QUERY (OSM/NOMINATIM STACK)

import math
import requests
from flask import Flask, render_template, url_for, request, redirect, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# --- Haversine Distance Calculation ---
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371
    lat1_rad = math.radians(lat1); lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2); lon2_rad = math.radians(lon2)
    dlon = lon2_rad - lon1_rad; dlat = lat2_rad - lat1_rad
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c
    return round(distance, 2)

# --- Nominatim Reverse Geocoding Function ---
def get_place_name_from_coords(latitude, longitude):
    """Uses Nominatim to get a concise address (e.g., Town, Road)."""
    nominatim_url = "https://nominatim.openstreetmap.org/reverse"
    params = {'lat': latitude, 'lon': longitude, 'format': 'json', 'zoom': 18, 'addressdetails': 1}
    headers = {'User-Agent': 'TelemedicineApp/1.0 (Contact: user@example.com)'}

    try:
        response = requests.get(nominatim_url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        address = data.get('address', {})
        street = address.get('road') or address.get('pedestrian') or ''
        locality = address.get('village') or address.get('suburb') or address.get('town') or address.get('city') or address.get('county') or ''
        concise_parts = [p for p in [locality, street] if p]
        concise_address = ", ".join(concise_parts) or data.get('display_name', 'Unknown Location')
        return {"concise_address": concise_address, "full_address": data.get('display_name', 'Unknown Location')}
    except requests.exceptions.RequestException as e:
        print(f"Nominatim API Error: {e}")
        return {"concise_address": "Address unavailable", "full_address": "Reverse Geocoding Failed"}

# --- Overpass API Query Function (Find Hospitals + Clinics) ---
def get_nearby_hospitals(user_lat, user_lon, radius_meters=5000):
    query = f"""
    [out:json];
    (
      node["amenity"~"hospital|clinic|doctors"](around:{radius_meters},{user_lat},{user_lon});
      way["amenity"~"hospital|clinic|doctors"](around:{radius_meters},{user_lat},{user_lon});
      relation["amenity"~"hospital|clinic|doctors"](around:{radius_meters},{user_lat},{user_lon});

      node["healthcare"~"hospital|clinic|doctor|centre"](around:{radius_meters},{user_lat},{user_lon});
      way["healthcare"~"hospital|clinic|doctor|centre"](around:{radius_meters},{user_lat},{user_lon});
      relation["healthcare"~"hospital|clinic|doctor|centre"](around:{radius_meters},{user_lat},{user_lon});
    );
    out center;
    """
    url = "https://overpass-api.de/api/interpreter"
    headers = {"User-Agent": "TelemedicineApp/1.0 (contact: your_email@example.com)"}

    try:
        response = requests.post(url, data={'data': query}, headers=headers, timeout=25)
        response.raise_for_status()
        osm_data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Overpass API Error: {e}")
        return []

    hospitals = []
    seen = set()

    for el in osm_data.get('elements', []):
        lat = el.get('lat') or el.get('center', {}).get('lat')
        lon = el.get('lon') or el.get('center', {}).get('lon')
        if not lat or not lon:
            continue

        key = (round(lat, 5), round(lon, 5))
        if key in seen:
            continue
        seen.add(key)

        name = el.get('tags', {}).get('name', 'Unnamed Facility')
        address_data = get_place_name_from_coords(lat, lon)
        distance_km = calculate_distance(user_lat, user_lon, lat, lon)

        hospitals.append({
            "name": name,
            "lat": lat,
            "lon": lon,
            "distance_km": distance_km,
            "address": address_data['concise_address']
        })

    hospitals.sort(key=lambda x: x['distance_km'])
    return hospitals


# --- FLASK ROUTES ---
@app.route('/')
def index(): return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST': return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST': return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/api/hospitals', methods=['POST'])
def hospitals_api():
    if request.content_type != 'application/json': 
        return jsonify({"error": "Unsupported Media Type: Expected 'application/json'"}), 415
    data = request.get_json(silent=True)
    if data is None: 
        return jsonify({"error": "Received empty or malformed JSON data"}), 400
    user_lat = data.get('latitude'); user_lon = data.get('longitude')
    if user_lat is None or user_lon is None: 
        return jsonify({"error": "Missing 'latitude' or 'longitude' in JSON payload"}), 400

    hospitals = get_nearby_hospitals(user_lat, user_lon)
    return jsonify({"hospitals": hospitals})

@app.route('/api/reverse_geocode', methods=['POST'])
def reverse_geocode_api():
    if request.content_type != 'application/json': 
        return jsonify({"error": "Unsupported Media Type: Expected 'application/json'"}), 415
    data = request.get_json(silent=True)
    if data is None: 
        return jsonify({"error": "No JSON data received"}), 400

    lat = data.get('latitude'); lon = data.get('longitude')
    if lat is None or lon is None: 
        return jsonify({"error": "Missing latitude/longitude"}), 400

    address_data = get_place_name_from_coords(lat, lon)
    return jsonify({"place_name": address_data['concise_address']})

@app.route('/hospital_details/<user_lat>/<user_lon>/<hosp_lat>/<hosp_lon>/<hosp_name>')
def hospital_details(user_lat, user_lon, hosp_lat, hosp_lon, hosp_name):
    distance_km = calculate_distance(
        float(user_lat), float(user_lon), float(hosp_lat), float(hosp_lon)
    )
    return render_template('hospital_details.html',
        user_lat=user_lat,
        user_lon=user_lon,
        hosp_lat=hosp_lat,
        hosp_lon=hosp_lon,
        hosp_name=hosp_name,
        distance_km=distance_km
    )

if __name__ == '__main__':
    app.run(debug=True)
