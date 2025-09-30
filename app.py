# app.py

import math
import requests
from flask import Flask, render_template, url_for, request, redirect, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app) 

# --- Distance Calculation Function (Haversine Formula) ---
# NOTE: Re-introducing the Haversine calculation to meet the requirement 
# of showing distance (which your old API code didn't calculate).
def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the distance (in km) between two points on the earth.
    """
    R = 6371  # Radius of earth in kilometers
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad

    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance = R * c
    return round(distance, 2)

# --- FLASK ROUTES ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # --- DUMMY LOGIN LOGIC ---
        email = request.form.get('email')
        print(f"Login attempt for: {email}") 
        return redirect(url_for('dashboard'))
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # --- DUMMY REGISTRATION LOGIC ---
        fullname = request.form.get('fullname')
        print(f"Registration attempt for: {fullname}")
        return redirect(url_for('login')) 
        
    return render_template('register.html')


@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')


# NEW: Merged your 'nearby_hospitals' logic into our existing '/api/hospitals' route
@app.route('/api/hospitals', methods=['POST'])
def hospitals_api():
    # 1. CHECK CONTENT TYPE and get user coordinates
    if request.content_type != 'application/json':
        return jsonify({"error": f"Unsupported Media Type: Expected 'application/json', got '{request.content_type}'"}), 415

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Received empty or malformed JSON data"}), 400
        
    user_lat = data.get('latitude')
    user_lon = data.get('longitude')

    if user_lat is None or user_lon is None:
        return jsonify({"error": "Missing 'latitude' or 'longitude' in JSON payload"}), 400

    # 2. Overpass API query (using your previous, comprehensive query logic)
    # Note: Using POST to match how we send the data, though the original used GET.
    query = f"""
    [out:json];
    (
      node["amenity"="hospital"](around:5000,{user_lat},{user_lon});
      way["amenity"="hospital"](around:5000,{user_lat},{user_lon});
      relation["amenity"="hospital"](around:5000,{user_lat},{user_lon});
    );
    out center;
    """
    url = "https://overpass-api.de/api/interpreter"
    
    try:
        # Use POST for robust query submission
        response = requests.post(url, data={'data': query}, timeout=15)
        response.raise_for_status() 
    except requests.exceptions.RequestException as e:
        print(f"Overpass API Request Error: {e}")
        return jsonify({"error": "Failed to fetch data from OpenStreetMap API."}), 500

    osm_data = response.json()

    # 3. Process data, extract coordinates, and calculate distance
    hospitals = []
    for element in osm_data.get('elements', []):
        
        # Extract coordinates: check 'lat'/'lon' first (for nodes), then 'center' (for ways/relations)
        lat = element.get('lat') or element.get('center', {}).get('lat')
        lon = element.get('lon') or element.get('center', {}).get('lon')

        if lat is not None and lon is not None:
            name = element.get('tags', {}).get('name', 'Unnamed Hospital')
            
            # Calculate distance using Haversine
            distance_km = calculate_distance(user_lat, user_lon, lat, lon)
            
            hospitals.append({
                'name': name,
                'lat': lat,
                'lon': lon,
                'distance_km': distance_km
            })

    # Sort and return
    hospitals.sort(key=lambda x: x['distance_km'])
    return jsonify({"hospitals": hospitals})


@app.route('/')
def index():
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)