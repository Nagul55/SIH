# app.py - FINAL CODE WITH DATABASE INITIALIZATION FIX

import math
import requests
from flask import Flask, render_template, url_for, request, redirect, jsonify, session, flash
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash 

app = Flask(__name__)
CORS(app) 

# --- DATABASE CONFIGURATION ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///telemedicine.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_super_secret_key_change_this_later'
db = SQLAlchemy(app)

# --- USER MODEL (Database Schema) ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fullname = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# --- UTILITY FUNCTIONS (Unchanged) ---

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371; lat1_rad = math.radians(lat1); lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2); lon2_rad = math.radians(lon2)
    dlon = lon2_rad - lon1_rad; dlat = lat2_rad - lat1_rad
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)

def get_place_name_from_coords(latitude, longitude):
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

def get_nearby_hospitals(user_lat, user_lon, radius_meters=5000):
    query = f"""
    [out:json];
    (
      node["amenity"="hospital"](around:{radius_meters},{user_lat},{user_lon});
      way["amenity"="hospital"](around:{radius_meters},{user_lat},{user_lon});
      relation["amenity"="hospital"](around:{radius_meters},{user_lat},{user_lon});

      node["healthcare"="hospital"](around:{radius_meters},{user_lat},{user_lon});
      way["healthcare"="hospital"](around:{radius_meters},{user_lat},{user_lon});
      relation["healthcare"="hospital"](around:{radius_meters},{user_lat},{user_lon});

      node["amenity"="clinic"](around:{radius_meters},{user_lat},{user_lon});
      way["amenity"="clinic"](around:{radius_meters},{user_lat},{user_lon});
      relation["amenity"="clinic"](around:{radius_meters},{user_lat},{user_lon});

      node["healthcare"="clinic"](around:{radius_meters},{user_lat},{user_lon});
      way["healthcare"="clinic"](around:{radius_meters},{user_lat},{user_lon});
      relation["healthcare"="clinic"](around:{radius_meters},{user_lat},{user_lon});
    );
    out center;
    """
    url = "https://overpass-api.de/api/interpreter"
    
    try:
        response = requests.post(url, data={'data': query}, timeout=15)
        response.raise_for_status() 
    except requests.exceptions.RequestException:
        return []

    osm_data = response.json()
    hospitals = []
    seen_coords = set()
    
    for element in osm_data.get('elements', []):
        lat = element.get('lat') or element.get('center', {}).get('lat')
        lon = element.get('lon') or element.get('center', {}).get('lon')
        
        if lat is not None and lon is not None:
            coord_key = (round(lat, 5), round(lon, 5))
            if coord_key in seen_coords: continue
            seen_coords.add(coord_key)
            
            name = element.get('tags', {}).get('name', 'Unnamed Hospital/Clinic')
            address_data = get_place_name_from_coords(lat, lon)
            distance_km = calculate_distance(user_lat, user_lon, lat, lon)
            
            hospitals.append({
                'name': name,
                'lat': lat,
                'lon': lon,
                'distance_km': distance_km,
                'address': address_data['concise_address']
            })

    hospitals.sort(key=lambda x: x['distance_km'])
    return hospitals


# --- FLASK ROUTES ---

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            session['user_id'] = user.id
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'danger')
            return render_template('login.html')
            
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        fullname = request.form.get('fullname')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('register.html')
            
        if User.query.filter_by(email=email).first():
            flash('Email address already registered.', 'danger')
            return render_template('register.html')

        new_user = User(fullname=fullname, email=email)
        new_user.set_password(password)

        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred during registration.', 'danger')
            return render_template('register.html')
            
    return render_template('register.html')


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please log in to access the dashboard.', 'warning')
        return redirect(url_for('login'))
        
    return render_template('dashboard.html')


@app.route('/api/hospitals', methods=['POST'])
def hospitals_api():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized access."}), 401
    
    if request.content_type != 'application/json': return jsonify({"error": "Unsupported Media Type: Expected 'application/json'"}), 415
    data = request.get_json(silent=True)
    if data is None: return jsonify({"error": "Received empty or malformed JSON data"}), 400
    user_lat = data.get('latitude'); user_lon = data.get('longitude')
    if user_lat is None or user_lon is None: return jsonify({"error": "Missing 'latitude' or 'longitude' in JSON payload"}), 400

    hospitals = get_nearby_hospitals(user_lat, user_lon)
    return jsonify({"hospitals": hospitals})

@app.route('/api/reverse_geocode', methods=['POST'])
def reverse_geocode_api():
    if 'user_id' not in session:
        return jsonify({"place_name": "Login Required"}), 401

    if request.content_type != 'application/json': return jsonify({"error": "Unsupported Media Type: Expected 'application/json'"}), 415
    data = request.get_json(silent=True)
    if data is None: return jsonify({"error": "No JSON data received"}), 400
        
    lat = data.get('latitude'); lon = data.get('longitude')
    if lat is None or lon is None: return jsonify({"error": "Missing latitude/longitude"}), 400

    address_data = get_place_name_from_coords(lat, lon)
    
    return jsonify({"place_name": address_data['concise_address']})

@app.route('/hospital_details/<user_lat>/<user_lon>/<hosp_lat>/<hosp_lon>/<hosp_name>')
def hospital_details(user_lat, user_lon, hosp_lat, hosp_lon, hosp_name):
    if 'user_id' not in session:
        flash('Please log in to view hospital details.', 'warning')
        return redirect(url_for('login'))
        
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

@app.route('/')
def index():
    return redirect(url_for('login'))

if __name__ == '__main__':
    # FIXED: Correct way to initialize the database outside of request scope
    with app.app_context():
        db.create_all()
    app.run(debug=True)