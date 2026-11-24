import csv
from datetime import datetime, timedelta, timezone
from functools import wraps
import io
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from werkzeug.utils import secure_filename
from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "vortex-ghost-aero-session-key-2026")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024

DATA_FILE = "missions.json"
BANNER_FILE = "banner.json"
GUESTBOOK_FILE = "guestbook.json"
SKY_PHOTOS_FILE = "sky_photos.json"
UPLOAD_FOLDER = os.path.join("static", "sky_uploads")
ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

NASA_API_KEY = os.environ.get("NASA_API_KEY", "DEMO_KEY")
FIREBASE_DB_URL = os.environ.get(
    "FIREBASE_DB_URL", "https://vortexchat-7dbb2-default-rtdb.firebaseio.com"
).rstrip("/")
FIREBASE_AUTH = os.environ.get("FIREBASE_AUTH", "").strip()

# Sylacauga, Alabama reference station (Ghost 1)
DEFAULT_OBS_LAT = 33.1732
DEFAULT_OBS_LON = -86.2517
DEFAULT_OBS_ALT_KM = 0.14

AU_KM = 149597870.7
SPEED_OF_LIGHT_KMS = 299792.458

US_STATES_COORDS = {
    "AL": {"name": "Alabama (Sylacauga HQ)", "lat": 33.1732, "lon": -86.2517},
    "AK": {"name": "Alaska (Fairbanks)", "lat": 64.8378, "lon": -147.7164},
    "AZ": {"name": "Arizona (Flagstaff)", "lat": 35.1983, "lon": -111.6513},
    "AR": {"name": "Arkansas (Little Rock)", "lat": 34.7465, "lon": -92.2896},
    "CA": {"name": "California (Mount Wilson)", "lat": 34.2244, "lon": -118.0572},
    "CO": {"name": "Colorado (Boulder)", "lat": 40.0150, "lon": -105.2705},
    "CT": {"name": "Connecticut (Hartford)", "lat": 41.7658, "lon": -72.6734},
    "DE": {"name": "Delaware (Dover)", "lat": 39.1582, "lon": -75.5244},
    "FL": {"name": "Florida (Cape Canaveral)", "lat": 28.3922, "lon": -80.6077},
    "GA": {"name": "Georgia (Atlanta)", "lat": 33.7490, "lon": -84.3880},
    "HI": {"name": "Hawaii (Mauna Kea)", "lat": 19.8207, "lon": -155.4681},
    "ID": {"name": "Idaho (Boise)", "lat": 43.6150, "lon": -116.2023},
    "IL": {"name": "Illinois (Chicago)", "lat": 41.8781, "lon": -87.6298},
    "IN": {"name": "Indiana (Indianapolis)", "lat": 39.7684, "lon": -86.1581},
    "IA": {"name": "Iowa (Des Moines)", "lat": 41.5868, "lon": -93.6250},
    "KS": {"name": "Kansas (Wichita)", "lat": 37.6872, "lon": -97.3301},
    "KY": {"name": "Kentucky (Lexington)", "lat": 38.0406, "lon": -84.5037},
    "LA": {"name": "Louisiana (Baton Rouge)", "lat": 30.4515, "lon": -91.1871},
    "ME": {"name": "Maine (Bangor)", "lat": 44.8016, "lon": -68.7712},
    "MD": {"name": "Maryland (Greenbelt / GSFC)", "lat": 39.0046, "lon": -76.8755},
    "MA": {"name": "Massachusetts (Cambridge)", "lat": 42.3736, "lon": -71.1097},
    "MI": {"name": "Michigan (Marquette)", "lat": 46.5436, "lon": -87.3954},
    "MN": {"name": "Minnesota (Duluth)", "lat": 46.7867, "lon": -92.1005},
    "MS": {"name": "Mississippi (Jackson)", "lat": 32.2988, "lon": -90.1848},
    "MO": {"name": "Missouri (St. Louis)", "lat": 38.6270, "lon": -90.1994},
    "MT": {"name": "Montana (Bozeman)", "lat": 45.6770, "lon": -111.0429},
    "NE": {"name": "Nebraska (Omaha)", "lat": 41.2565, "lon": -95.9345},
    "NV": {"name": "Nevada (Reno)", "lat": 39.5296, "lon": -119.8138},
    "NH": {"name": "New Hampshire (Concord)", "lat": 43.2081, "lon": -71.5376},
    "NJ": {"name": "New Jersey (Princeton)", "lat": 40.3573, "lon": -74.6672},
    "NM": {"name": "New Mexico (Socorro / VLA)", "lat": 34.0584, "lon": -106.8914},
    "NY": {"name": "New York (Ithaca)", "lat": 42.4440, "lon": -76.5019},
    "NC": {"name": "North Carolina (Raleigh)", "lat": 35.7796, "lon": -78.6382},
    "ND": {"name": "North Dakota (Bismarck)", "lat": 46.8083, "lon": -100.7837},
    "OH": {"name": "Ohio (Cleveland / Glenn)", "lat": 41.4993, "lon": -81.6944},
    "OK": {"name": "Oklahoma (Norman)", "lat": 35.2226, "lon": -97.4395},
    "OR": {"name": "Oregon (Bend)", "lat": 44.0582, "lon": -121.3153},
    "PA": {"name": "Pennsylvania (State College)", "lat": 40.7934, "lon": -77.8600},
    "RI": {"name": "Rhode Island (Providence)", "lat": 41.8240, "lon": -71.4128},
    "SC": {"name": "South Carolina (Columbia)", "lat": 34.0007, "lon": -81.0348},
    "SD": {"name": "South Dakota (Rapid City)", "lat": 44.0805, "lon": -103.2310},
    "TN": {"name": "Tennessee (Nashville)", "lat": 36.1627, "lon": -86.7816},
    "TX": {"name": "Texas (Houston / JSC)", "lat": 29.5593, "lon": -95.0900},
    "UT": {"name": "Utah (Salt Lake City)", "lat": 40.7608, "lon": -111.8910},
    "VT": {"name": "Vermont (Burlington)", "lat": 44.4759, "lon": -73.2121},
    "VA": {"name": "Virginia (Wallops Island)", "lat": 37.9402, "lon": -75.4664},
    "WA": {"name": "Washington (Seattle)", "lat": 47.6062, "lon": -122.3321},
    "WV": {"name": "West Virginia (Green Bank)", "lat": 38.4331, "lon": -79.8398},
    "WI": {"name": "Wisconsin (Madison)", "lat": 43.0731, "lon": -89.4012},
    "WY": {"name": "Wyoming (Cheyenne)", "lat": 41.1400, "lon": -104.8202},
}

PLANET_ELEMENTS = [
    {
        "id": "mercury",
        "jpl_id": "199",
        "name": "Mercury",
        "class": "Terrestrial World",
        "color": "#b8c0cc",
        "gravity_g": 0.38,
        "radius_km": 2439.7,
        "fact": (
            "A year on Mercury takes only 88 Earth days, but a single solar day"
            " from sunrise to sunrise lasts 176 Earth days!"
        ),
        "a": 0.387098,
        "e": 0.205630,
        "i": 7.00487,
        "Omega": 48.33167,
        "omega": 29.12478,
        "M0": 174.7948,
        "n": 4.09233445,
        "period_days": 87.97,
    },
    {
        "id": "venus",
        "jpl_id": "299",
        "name": "Venus",
        "class": "Terrestrial / Greenhouse",
        "color": "#e5c07b",
        "gravity_g": 0.90,
        "radius_km": 6051.8,
        "fact": (
            "Venus spins backward compared to most planets, so the Sun rises in"
            " the west and sets in the east."
        ),
        "a": 0.723332,
        "e": 0.006772,
        "i": 3.39471,
        "Omega": 76.68069,
        "omega": 54.88423,
        "M0": 50.4161,
        "n": 1.60213034,
        "period_days": 224.70,
    },
    {
        "id": "earth",
        "jpl_id": "399",
        "name": "Earth",
        "class": "Home / Reference World",
        "color": "#4ea8de",
        "gravity_g": 1.00,
        "radius_km": 6378.1,
        "fact": (
            "Earth is the densest planet in our solar system and the only known"
            " world with liquid water oceans covering most of its surface."
        ),
        "a": 1.000000,
        "e": 0.016708,
        "i": 0.00005,
        "Omega": -11.26064,
        "omega": 102.94719,
        "M0": 100.46435,
        "n": 0.9856076686,
        "period_days": 365.256,
    },
    {
        "id": "mars",
        "jpl_id": "499",
        "name": "Mars",
        "class": "Terrestrial / Frontier",
        "color": "#e06c75",
        "gravity_g": 0.38,
        "radius_km": 3396.2,
        "fact": (
            "Mars is home to Olympus Mons, a shield volcano nearly three times"
            " taller than Mount Everest."
        ),
        "a": 1.523679,
        "e": 0.093400,
        "i": 1.85061,
        "Omega": 49.57854,
        "omega": 286.50158,
        "M0": 19.3730,
        "n": 0.52402068,
        "period_days": 686.98,
    },
    {
        "id": "jupiter",
        "jpl_id": "599",
        "name": "Jupiter",
        "class": "Gas Giant",
        "color": "#d19a66",
        "gravity_g": 2.53,
        "radius_km": 71492.0,
        "fact": (
            "Jupiter is more than twice as massive as all the other planets in"
            " our solar system combined and has the shortest day (~10 hours)."
        ),
        "a": 5.204417,
        "e": 0.048900,
        "i": 1.30326,
        "Omega": 100.4644,
        "omega": 273.867,
        "M0": 20.020,
        "n": 0.08308529,
        "period_days": 4332.59,
    },
    {
        "id": "saturn",
        "jpl_id": "699",
        "name": "Saturn",
        "class": "Ringed Gas Giant",
        "color": "#e6db74",
        "gravity_g": 1.07,
        "radius_km": 60268.0,
        "fact": (
            "Saturn's famous ring system spans up to 175,000 miles across, yet"
            " is mostly made of ice chunks and rock and is only tens of meters"
            " thick in many places."
        ),
        "a": 9.582670,
        "e": 0.056500,
        "i": 2.48891,
        "Omega": 113.665,
        "omega": 339.392,
        "M0": 317.020,
        "n": 0.03344414,
        "period_days": 10759.22,
    },
    {
        "id": "uranus",
        "jpl_id": "799",
        "name": "Uranus",
        "class": "Ice Giant",
        "color": "#73d2de",
        "gravity_g": 0.89,
        "radius_km": 25559.0,
        "fact": (
            "Uranus is tilted on its side at about 98 degrees, so it looks like"
            " it is rolling around the Sun on its side."
        ),
        "a": 19.218446,
        "e": 0.046381,
        "i": 0.77319,
        "Omega": 74.006,
        "omega": 96.998857,
        "M0": 142.2386,
        "n": 0.01172834,
        "period_days": 30688.5,
    },
    {
        "id": "neptune",
        "jpl_id": "899",
        "name": "Neptune",
        "class": "Outer Ice Giant",
        "color": "#5c7cfa",
        "gravity_g": 1.14,
        "radius_km": 24764.0,
        "fact": (
            "Neptune orbits so far from the Sun that one Neptune year lasts"
            " about 165 Earth years—and it was discovered in 1846, completing"
            " its first full orbit since discovery in 2011!"
        ),
        "a": 30.110387,
        "e": 0.009456,
        "i": 1.76995,
        "Omega": 131.784,
        "omega": 276.336,
        "M0": 256.228,
        "n": 0.00598103,
        "period_days": 60195.0,
    },
]

GEOSCIENCE_TOPICS = [
    {
        "code": "GEO-01",
        "title": "Tectonic Plate Boundaries",
        "focus": "Lithosphere & Crustal Dynamics",
        "summary": (
            "Earth's rigid lithosphere is broken into major tectonic plates that"
            " diverge, converge, or slide past one another along transform"
            " faults, driving mountain building, volcanism, and earthquakes."
        ),
        "kid_note": (
            "Imagine giant puzzle pieces floating slowly on warm, gooey rock"
            " below—moving only about as fast as your fingernails grow each"
            " year!"
        ),
    },
    {
        "code": "GEO-02",
        "title": "Seismic Waves & Fault Rupture",
        "focus": "Seismology & Earth Interior",
        "summary": (
            "Sudden slip along a fault releases strain energy as compressional"
            " P-waves, shear S-waves, and surface waves that seismographs record"
            " to locate hypocenters and map crust/mantle structure."
        ),
        "kid_note": (
            "P-waves push and pull like a slinky, while S-waves wiggle side to"
            " side like a jump rope!"
        ),
    },
    {
        "code": "GEO-03",
        "title": "Appalachians & Alabama Piedmont",
        "focus": "Regional Bedrock & Stratigraphy",
        "summary": (
            "Central Alabama sits right along the transition between ancient"
            " crystalline metamorphic/igneous rocks of the Piedmont and folded"
            " Paleozoic ridges, valleys, and karst terrain toward the"
            " Appalachians."
        ),
        "kid_note": (
            "Around Sylacauga and central Alabama, ancient rocks and marble/karst"
            " formations tell a story hundreds of millions of years old."
        ),
    },
]

SPACE_GLOSSARY = [
    {
        "term": "Astronomical Unit (AU)",
        "kid_desc": (
            "A giant space ruler! 1 AU is the average distance from Earth to the"
            " Sun (about 93 million miles)."
        ),
    },
    {
        "term": "Orbit",
        "kid_desc": (
            "The curved path a planet, moon, or spacecraft follows around a"
            " bigger object because of gravity."
        ),
    },
    {
        "term": "Exoplanet",
        "kid_desc": (
            "A planet that orbits a star outside our own solar system."
        ),
    },
    {
        "term": "Light-Time",
        "kid_desc": (
            "How long light or a radio signal takes to travel through space."
            " Light is super fast, but space is huge!"
        ),
    },
    {
        "term": "Solar Flare & CME",
        "kid_desc": (
            "Giant bursts of energy and super-hot gas blasting off the Sun that"
            " can create auroras on Earth."
        ),
    },
    {
        "term": "Delta-V",
        "kid_desc": (
            "The total change in speed a rocket needs to escape Earth's gravity"
            " and steer to another world."
        ),
    },
]

DEEP_SPACE_PROBES = [
    {
        "code": "VGR-1",
        "name": "Voyager 1",
        "status": "INTERSTELLAR MISSION",
        "target": "Interstellar Medium / Heliopause",
        "launch": "1977-09-05",
        "range_note": "~165+ AU from Earth (~23h light-time)",
        "summary": (
            "Farthest human-made object in space, sampling interstellar plasma"
            " and cosmic rays beyond the heliosphere."
        ),
        "eyes_url": "https://eyes.nasa.gov/apps/solar-system/#/sc_voyager_1",
    },
    {
        "code": "PSP",
        "name": "Parker Solar Probe",
        "status": "ACTIVE SOLAR PERIHELION",
        "target": "Solar Corona & Heliosphere",
        "launch": "2018-08-12",
        "range_note": "Closest approach ~6.1 million km to Sun",
        "summary": (
            "Fastest spacecraft ever built, flying directly through the Sun's"
            " outer corona to trace solar wind acceleration."
        ),
        "eyes_url": (
            "https://eyes.nasa.gov/apps/solar-system/#/sc_parker_solar_probe"
        ),
    },
    {
        "code": "EUROPA-C",
        "name": "Europa Clipper",
        "status": "CRUISE TO JUPITER",
        "target": "Jovian Moon Europa (Subsurface Ocean)",
        "launch": "2024-10-14",
        "range_note": "En route for 2030 Jupiter orbit insertion",
        "summary": (
            "Conducting detailed reconnaissance of Jupiter's icy moon Europa to"
            " investigate habitability beneath its ice shell."
        ),
        "eyes_url": "https://eyes.nasa.gov/apps/solar-system/#/sc_europa_clipper",
    },
    {
        "code": "JWST",
        "name": "James Webb Space Telescope",
        "status": "ACTIVE L2 OBSERVATORY",
        "target": "Exoplanet Atmospheres & Early Universe",
        "launch": "2021-12-25",
        "range_note": "Sun-Earth L2 Halo Orbit (~1.5M km)",
        "summary": (
            "6.5-meter infrared space observatory performing transit spectroscopy"
            " on exoplanets and deep-field cosmology."
        ),
        "eyes_url": "https://eyes.nasa.gov/apps/solar-system/#/sc_jwst",
    },
]

PAYLOAD_MANIFEST = [
    {
        "code": "PAY-01",
        "name": "Surface & Boundary Probe Pod",
        "subsystem": "Atmospheric Instrumentation",
        "revision": "Rev 1.2",
        "specs": {
            "Mass": "640 g",
            "Power Bus": "7.4V Li-Ion / Regulated 5V & 3.3V",
            "Sensors": "Barometric Pressure, Temp, RH, GNSS",
            "Comms / Link": "Starlink / LoRa Telemetry Packet",
        },
        "summary": (
            "Ruggedized ground and boundary-layer sensor housing engineered for"
            " rapid deployment and convective inflow profiling."
        ),
    },
    {
        "code": "PAY-02",
        "name": "Upper-Air Radiosonde & Beacon",
        "subsystem": "High-Altitude & Recovery",
        "revision": "Rev 0.9",
        "specs": {
            "Target Ceiling": "24,000+ m AGL",
            "Power Bus": "Lithium Primary Pack",
            "Sensors": "PTU + Altitude + IMU Attitude",
            "Recovery": "GPS Beacon + High-Vis Shell",
        },
        "summary": (
            "Lightweight sounding package designed for vertical thermodynamic"
            " profiling, telemetry tracking, and post-flight recovery."
        ),
    },
    {
        "code": "PAY-03",
        "name": "Mobile Telemetry & Dispatch Bus",
        "subsystem": "Avionics & Field Comms",
        "revision": "Rev 2.0",
        "specs": {
            "Platform": "Field Vehicle / Mobile Command",
            "Power Bus": "12V Vehicle Bus + Isolation",
            "Uplink": "Low-Earth Orbit Satellite + Cellular",
            "Logging": "UTC Timestamped JSON / CSV",
        },
        "summary": (
            "Field-hardened telemetry relay and real-time logging interface"
            " linking ground/air experiments with mission control."
        ),
    },
]

BRIEFING_LINKS = [
    {
        "title": "NASA Eyes on the Solar System (3D)",
        "category": "Interactive 3D Visualization",
        "url": "https://eyes.nasa.gov/apps/solar-system/",
        "desc": (
            "Real-time 3D trajectories of planets, moons, asteroids, and active"
            " NASA spacecraft."
        ),
    },
    {
        "title": "USGS Latest Earthquakes Portal",
        "category": "Geoscience & Seismology",
        "url": "https://earthquake.usgs.gov/earthquakes/map/",
        "desc": (
            "Global seismic monitoring, fault rupture maps, and magnitude/depth"
            " catalogs."
        ),
    },
    {
        "title": "NASA Exoplanet Archive",
        "category": "Exoplanets & Worlds",
        "url": "https://exoplanetarchive.ipac.caltech.edu/",
        "desc": (
            "Confirmed exoplanet catalog, planetary systems, and transit"
            " discovery data."
        ),
    },
    {
        "title": "NOAA Space Weather Prediction Center",
        "category": "Geomagnetic & Solar",
        "url": "https://www.swpc.noaa.gov/",
        "desc": (
            "Live solar wind, geomagnetic storm alerts, and G/S/R space weather"
            " scales."
        ),
    },
]

_swpc_cache = {
    "ts": 0.0,
    "kp": "N/A",
    "kp_num": 1.0,
    "scale": "STANDBY",
    "updated_utc": "STANDBY",
}

_nws_sky_cache = {}

_donki_cache = {
    "ts": 0.0,
    "flares": [],
    "cmes": [],
}

_eq_cache = {
    "key": "",
    "ts": 0.0,
    "quakes": [],
}

_sat_cache = {
    "ts": 0.0,
    "name": "ISS (ZARYA)",
    "norad_id": "25544",
    "lat": 0.0,
    "lon": 0.0,
    "alt_km": 0.0,
    "vel_kmh": 0.0,
    "visibility": "STANDBY",
    "source": "STANDBY",
}

_daily_nasa_cache = {
    "day_key": "",
    "apod": {
        "title": "Daily NASA Discovery Feed Standby",
        "date": "",
        "media_type": "image",
        "url": "",
        "explanation": "Awaiting daily NASA APOD synchronization.",
    },
    "galleries": {},
    "exoplanets": [],
    "neo_count": "STANDBY",
}

ALLOWED_GALLERY_TOPICS = {
    "exoplanet": "Exoplanets & New Worlds",
    "james webb": "James Webb Space Telescope",
    "mars rover": "Mars Surface Exploration",
    "nebula": "Nebulae & Deep Galaxies",
}


def utc_day_str():
  return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fetch_json(url, method="GET", payload=None, timeout=8):
  data_bytes = None
  headers = {
      "User-Agent": "VortexGhostAerospace/1.0 (contact@vortexghost.site)",
      "Accept": "application/geo+json, application/json",
  }
  if payload is not None:
    data_bytes = json.dumps(payload).encode("utf-8")
    headers["Content-Type"] = "application/json"
  req = urllib.request.Request(
      url, data=data_bytes, headers=headers, method=method
  )
  with urllib.request.urlopen(req, timeout=timeout) as resp:
    raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw.strip() else None


def get_nws_sky_scorecard(state_code="AL", custom_lat=None, custom_lon=None):
  code = (state_code or "AL").strip().upper()
  if code not in US_STATES_COORDS:
    code = "AL"

  if custom_lat is not None and custom_lon is not None:
    lat = round(float(custom_lat), 4)
    lon = round(float(custom_lon), 4)
    label = f"Custom Station ({lat}, {lon})"
    cache_key = f"CUSTOM:{lat}:{lon}"
  else:
    st = US_STATES_COORDS[code]
    lat, lon = st["lat"], st["lon"]
    label = f"{code} — {st['name']}"
    cache_key = f"STATE:{code}"

  now = time.time()
  cached = _nws_sky_cache.get(cache_key)
  nws_info = None
  if cached and (now - cached["ts"]) < 900:
    nws_info = cached["data"]
  else:
    try:
      req_headers = {
          "User-Agent": "(vortexghost.site, contact@vortexghost.site)",
          "Accept": "application/geo+json, application/json",
      }
      pt_req = urllib.request.Request(
          f"https://api.weather.gov/points/{round(lat, 4)},{round(lon, 4)}",
          headers=req_headers,
      )
      with urllib.request.urlopen(pt_req, timeout=5) as resp:
        pt = json.loads(resp.read().decode("utf-8"))
      props = (pt or {}).get("properties") or {}
      fc_url = props.get("forecast")
      office = props.get("gridId") or "NWS"
      if fc_url:
        fc_req = urllib.request.Request(fc_url, headers=req_headers)
        with urllib.request.urlopen(fc_req, timeout=5) as fresp:
          fc = json.loads(fresp.read().decode("utf-8"))
        periods = ((fc or {}).get("properties") or {}).get("periods") or []
        tonight = next(
            (p for p in periods if not p.get("isDaytime", True)),
            periods[0] if periods else None,
        )
        if tonight:
          sf = tonight.get("shortForecast") or "Partly Cloudy"
          sf_low = sf.lower()
          if "clear" in sf_low or "sunny" in sf_low:
            pen = 0
          elif (
              "partly" in sf_low
              or "mostly clear" in sf_low
              or "few clouds" in sf_low
          ):
            pen = 12
          elif "mostly cloudy" in sf_low:
            pen = 28
          else:
            pen = 42
          nws_info = {
              "short_forecast": f"{tonight.get('name', 'Tonight')}: {sf}",
              "temp": (
                  f"{tonight.get('temperature', '--')}°{tonight.get('temperatureUnit', 'F')}"
              ),
              "wind": (
                  f"{tonight.get('windSpeed', '--')} {tonight.get('windDirection', '')}".strip()
              ),
              "cloud_penalty": pen,
              "office": office,
              "live_nws": True,
          }
          _nws_sky_cache[cache_key] = {"ts": now, "data": nws_info}
    except Exception:
      nws_info = None

  if not nws_info:
    nws_info = {
        "short_forecast": "Estimated Sky Profile (NWS Feed Offline/Timeout)",
        "temp": "N/A",
        "wind": "N/A",
        "cloud_penalty": 15,
        "office": code,
        "live_nws": False,
    }

  lunar = get_lunar_telemetry()
  swx = get_space_weather()
  kp_num = float(swx.get("kp_num", 1.0))
  illum = float(lunar.get("illumination", 50.0))

  moon_penalty = int(round((illum / 100.0) * 30.0))
  sky_score = max(10, min(100, 100 - nws_info["cloud_penalty"] - moon_penalty))
  if sky_score >= 75:
    verdict = "GO // PRIME DEEP-SKY & PLANETARY WINDOW"
  elif sky_score >= 50:
    verdict = "MARGINAL // BRIGHT PLANETS & MOON ONLY"
  else:
    verdict = "NO-GO // HEAVY CLOUDS OR BRIGHT GLARE"

  needed_kp = max(1.0, min(9.0, round((67.0 - abs(lat)) / 3.4, 1)))
  if kp_num >= needed_kp:
    aurora_status = (
        f"ACTIVE WATCH (Kp {kp_num:.1f} >= {needed_kp:.1f} threshold)"
    )
  else:
    aurora_status = f"LOW (Needs Kp {needed_kp:.1f}+; Live Kp {kp_num:.1f})"

  return {
      "state_code": code,
      "label": label,
      "lat": lat,
      "lon": lon,
      "office": nws_info["office"],
      "live_nws": nws_info.get("live_nws", False),
      "short_forecast": nws_info["short_forecast"],
      "temp": nws_info["temp"],
      "wind": nws_info["wind"],
      "sky_score": sky_score,
      "verdict": verdict,
      "aurora_status": aurora_status,
      "kp": swx["kp"],
      "lunar_illum": illum,
  }


@app.route("/api/sky-scorecard")
def api_sky_scorecard():
  state_code = request.args.get("state", "AL")
  lat_raw = request.args.get("lat", "").strip()
  lon_raw = request.args.get("lon", "").strip()
  custom_lat, custom_lon = None, None
  if lat_raw and lon_raw:
    try:
      custom_lat = float(lat_raw)
      custom_lon = float(lon_raw)
    except ValueError:
      pass
  return jsonify(
      get_nws_sky_scorecard(
          state_code=state_code, custom_lat=custom_lat, custom_lon=custom_lon
      )
  )


def is_team_authenticated():
  return session.get("team_auth") is True


def team_required(fn):
  @wraps(fn)
  def wrapper(*args, **kwargs):
    if not is_team_authenticated():
      return redirect(
          url_for("index", auth_msg="Team login required.") + "#team-access"
      )
    return fn(*args, **kwargs)

  return wrapper


def _load_local_missions():
  if not os.path.exists(DATA_FILE):
    return []
  try:
    with open(DATA_FILE, "r") as f:
      data = json.load(f)
      return data if isinstance(data, list) else []
  except Exception:
    return []


def _save_local_missions(missions):
  try:
    with open(DATA_FILE, "w") as f:
      json.dump(missions, f, indent=2)
  except Exception:
    pass


def load_missions():
  try:
    raw = fetch_json(_firebase_url("missions"), timeout=6)
    if isinstance(raw, list):
      missions = [m for m in raw if isinstance(m, dict)]
      _save_local_missions(missions)
      return missions
    if isinstance(raw, dict):
      missions = [v for v in raw.values() if isinstance(v, dict)]
      missions.sort(key=lambda x: x.get("updated_utc", ""), reverse=True)
      _save_local_missions(missions)
      return missions
    if raw is None:
      local = _load_local_missions()
      return local if local else []
  except Exception:
    pass
  return _load_local_missions()


def save_missions(missions):
  _save_local_missions(missions)
  try:
    fetch_json(
        _firebase_url("missions"), method="PUT", payload=missions, timeout=6
    )
  except Exception:
    pass


def _load_local_banner():
  if not os.path.exists(BANNER_FILE):
    return {"message": "", "level": "INFO", "updated_utc": "", "author": ""}
  try:
    with open(BANNER_FILE, "r") as f:
      data = json.load(f)
      return data if isinstance(data, dict) else {"message": ""}
  except Exception:
    return {"message": ""}


def _save_local_banner(banner_obj):
  try:
    with open(BANNER_FILE, "w") as f:
      json.dump(banner_obj, f, indent=2)
  except Exception:
    pass


def load_banner():
  try:
    raw = fetch_json(_firebase_url("banner"), timeout=5)
    if isinstance(raw, dict):
      _save_local_banner(raw)
      return raw
  except Exception:
    pass
  return _load_local_banner()


def save_banner(banner_obj):
  _save_local_banner(banner_obj)
  try:
    fetch_json(
        _firebase_url("banner"), method="PUT", payload=banner_obj, timeout=5
    )
  except Exception:
    pass


def _load_local_guestbook():
  if not os.path.exists(GUESTBOOK_FILE):
    return []
  try:
    with open(GUESTBOOK_FILE, "r") as f:
      data = json.load(f)
      return data if isinstance(data, list) else []
  except Exception:
    return []


def _save_local_guestbook(entries):
  try:
    with open(GUESTBOOK_FILE, "w") as f:
      json.dump(entries, f, indent=2)
  except Exception:
    pass


def load_guestbook():
  try:
    raw = fetch_json(_firebase_url("guestbook"), timeout=5)
    entries = []
    if isinstance(raw, list):
      entries = [e for e in raw if isinstance(e, dict)]
    elif isinstance(raw, dict):
      entries = [v for v in raw.values() if isinstance(v, dict)]
    entries.sort(key=lambda x: x.get("created_utc", ""), reverse=True)
    _save_local_guestbook(entries)
    return entries[:20]
  except Exception:
    pass
  return _load_local_guestbook()[:20]


def save_guestbook(entries):
  _save_local_guestbook(entries)
  try:
    fetch_json(
        _firebase_url("guestbook"), method="PUT", payload=entries, timeout=5
    )
  except Exception:
    pass


def _load_local_sky_photos():
  if not os.path.exists(SKY_PHOTOS_FILE):
    return []
  try:
    with open(SKY_PHOTOS_FILE, "r") as f:
      data = json.load(f)
      return data if isinstance(data, list) else []
  except Exception:
    return []


def _save_local_sky_photos(photos):
  try:
    with open(SKY_PHOTOS_FILE, "w") as f:
      json.dump(photos, f, indent=2)
  except Exception:
    pass


def load_sky_photos():
  try:
    raw = fetch_json(_firebase_url("sky_photos"), timeout=5)
    photos = []
    if isinstance(raw, list):
      photos = [p for p in raw if isinstance(p, dict)]
    elif isinstance(raw, dict):
      photos = [v for v in raw.values() if isinstance(v, dict)]
    photos.sort(key=lambda x: x.get("uploaded_utc", ""), reverse=True)
    _save_local_sky_photos(photos)
    return photos[:24]
  except Exception:
    pass
  return _load_local_sky_photos()[:24]


def save_sky_photos(photos):
  _save_local_sky_photos(photos)
  try:
    fetch_json(
        _firebase_url("sky_photos"), method="PUT", payload=photos, timeout=5
    )
  except Exception:
    pass


def solve_kepler(M_rad, e, tol=1e-9, max_iter=30):
  E = M_rad if e < 0.8 else math.pi
  for _ in range(max_iter):
    f = E - e * math.sin(E) - M_rad
    f_prime = 1.0 - e * math.cos(E)
    delta = f / f_prime
    E -= delta
    if abs(delta) < tol:
      break
  return E


def compute_heliocentric_coords(el, days_since_j2000):
  a = el["a"]
  e = el["e"]
  inc = math.radians(el["i"])
  Omega = math.radians(el["Omega"])
  omega = math.radians(el["omega"])

  M_deg = (el["M0"] + el["n"] * days_since_j2000) % 360.0
  M_rad = math.radians(M_deg)
  E_rad = solve_kepler(M_rad, e)

  cos_E = math.cos(E_rad)
  sin_E = math.sin(E_rad)
  sqrt_one_minus_e2 = math.sqrt(max(0.0, 1.0 - e * e))

  r = a * (1.0 - e * cos_E)
  nu = math.atan2(sqrt_one_minus_e2 * sin_E, cos_E - e)

  cos_O, sin_O = math.cos(Omega), math.sin(Omega)
  cos_i, sin_i = math.cos(inc), math.sin(inc)

  u = omega + nu
  cos_u, sin_u = math.cos(u), math.sin(u)

  x = r * (cos_O * cos_u - sin_O * sin_u * cos_i)
  y = r * (sin_O * cos_u + cos_O * sin_u * cos_i)
  z = r * (sin_u * sin_i)

  lon_deg = (math.degrees(math.atan2(y, x))) % 360.0
  k = 0.01720209895
  v_au_day = k * math.sqrt(max(0.0, (2.0 / r) - (1.0 / a)))
  speed_kms = (v_au_day * AU_KM) / 86400.0

  return {
      "x": x,
      "y": y,
      "z": z,
      "r_au": r,
      "lon_deg": lon_deg,
      "speed_kms": speed_kms,
  }


def format_light_time(dist_km):
  sec = dist_km / SPEED_OF_LIGHT_KMS
  if sec < 60:
    return f"{sec:.1f} sec"
  mins = sec / 60.0
  if mins < 60:
    return f"{mins:.1f} min"
  hrs = int(mins // 60)
  rem_m = int(round(mins % 60))
  return f"{hrs}h {rem_m}m"


def get_lunar_telemetry(dt_utc=None):
  if dt_utc is None:
    dt_utc = datetime.now(timezone.utc)

  ref_new_moon = datetime(2000, 1, 6, 18, 14, 0, tzinfo=timezone.utc)
  synodic_days = 29.530588853
  elapsed_days = (dt_utc - ref_new_moon).total_seconds() / 86400.0
  age_days = elapsed_days % synodic_days
  phase_frac = age_days / synodic_days

  illum_pct = round(
      0.5 * (1.0 - math.cos(2.0 * math.pi * phase_frac)) * 100.0, 1
  )

  anomalistic_days = 27.55455
  anom_angle = (
      2.0 * math.pi * ((elapsed_days % anomalistic_days) / anomalistic_days)
  )
  dist_km = int(round(384400.0 - 21100.0 * math.cos(anom_angle)))

  if phase_frac < 0.03 or phase_frac >= 0.97:
    phase_name = "New Moon"
  elif phase_frac < 0.22:
    phase_name = "Waxing Crescent"
  elif phase_frac < 0.28:
    phase_name = "First Quarter"
  elif phase_frac < 0.47:
    phase_name = "Waxing Gibbous"
  elif phase_frac < 0.53:
    phase_name = "Full Moon"
  elif phase_frac < 0.72:
    phase_name = "Waning Gibbous"
  elif phase_frac < 0.78:
    phase_name = "Last Quarter"
  else:
    phase_name = "Waning Crescent"

  if illum_pct < 25.0:
    sky_quality = "DARK SKY WINDOW (Ideal for Nebulae & Galaxies)"
  elif illum_pct < 65.0:
    sky_quality = "MODERATE MOONLIGHT (Good for Planets & Clusters)"
  else:
    sky_quality = "BRIGHT MOONLIGHT (Best for Moon & Bright Planets)"

  return {
      "phase_name": phase_name,
      "illumination": illum_pct,
      "age_days": round(age_days, 1),
      "phase_frac": round(phase_frac, 4),
      "dist_km": f"{dist_km:,}",
      "sky_quality": sky_quality,
  }


def get_planetary_positions(dt_utc=None, day_offset=0.0):
  if dt_utc is None:
    dt_utc = datetime.now(timezone.utc)
  target_dt = dt_utc + timedelta(days=float(day_offset))

  j2000 = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
  days_j2000 = (target_dt - j2000).total_seconds() / 86400.0

  raw_positions = {}
  for el in PLANET_ELEMENTS:
    raw_positions[el["id"]] = compute_heliocentric_coords(el, days_j2000)

  earth = raw_positions["earth"]
  es_x, es_y, es_z = -earth["x"], -earth["y"], -earth["z"]
  es_norm = math.sqrt(es_x * es_x + es_y * es_y + es_z * es_z)

  planets_out = []

  for el in PLANET_ELEMENTS:
    pid = el["id"]
    pos = raw_positions[pid]
    dx = pos["x"] - earth["x"]
    dy = pos["y"] - earth["y"]
    dz = pos["z"] - earth["z"]
    dist_earth_au = math.sqrt(dx * dx + dy * dy + dz * dz)
    dist_earth_km = dist_earth_au * AU_KM
    dist_earth_mkm = dist_earth_km / 1_000_000.0

    car_hours = dist_earth_km / 104.6
    car_years = car_hours / (24.0 * 365.25)
    if pid == "earth":
      kid_trip = "You are standing here!"
    elif car_years < 1.0:
      kid_trip = f"~{int(round(car_hours / 24.0)):,} days nonstop at 65 mph"
    else:
      kid_trip = f"~{car_years:,.1f} years nonstop at 65 mph"

    if pid == "earth":
      light_time = "0.0 sec"
      chem_days = "0 days"
      elongation_deg = 0.0
      visibility_window = "Observer Reference"
    else:
      light_time = format_light_time(dist_earth_km)
      days_est = int(round((dist_earth_km / 15.0) / 86400.0))
      chem_days = (
          f"~{days_est} days"
          if days_est < 730
          else f"~{days_est / 365.25:.1f} yrs"
      )
      dot = dx * es_x + dy * es_y + dz * es_z
      cos_el = max(-1.0, min(1.0, dot / max(dist_earth_au * es_norm, 1e-9)))
      elongation_deg = round(math.degrees(math.acos(cos_el)), 1)

      cross_z = es_x * dy - es_y * dx
      side = "Evening Sky" if cross_z > 0 else "Morning Sky"
      if elongation_deg < 15.0:
        visibility_window = "Solar Conjunction (Glare)"
      elif elongation_deg > 150.0:
        visibility_window = "Near Opposition (All Night)"
      else:
        visibility_window = f"{side} ({elongation_deg}°)"

    planets_out.append({
        "id": pid,
        "jpl_id": el["jpl_id"],
        "name": el["name"],
        "class": el["class"],
        "color": el["color"],
        "gravity_g": el["gravity_g"],
        "radius_km": el["radius_km"],
        "fact": el["fact"],
        "kid_trip": kid_trip,
        "x": round(pos["x"], 4),
        "y": round(pos["y"], 4),
        "z": round(pos["z"], 4),
        "sun_au": round(pos["r_au"], 3),
        "earth_au": round(dist_earth_au, 3),
        "earth_mkm": round(dist_earth_mkm, 1),
        "lon_deg": round(pos["lon_deg"], 1),
        "speed_kms": round(pos["speed_kms"], 1),
        "light_time": light_time,
        "transit_est": chem_days,
        "elongation_deg": elongation_deg,
        "visibility_window": visibility_window,
        "period_days": el["period_days"],
    })

  return {
      "timestamp_utc": target_dt.strftime("%Y-%m-%d %H:%M:%S UTC"),
      "day_offset": round(float(day_offset), 1),
      "planets": planets_out,
      "lunar": get_lunar_telemetry(target_dt),
  }


def query_jpl_horizons(jpl_id):
  now_utc = datetime.now(timezone.utc)
  start_str = now_utc.strftime("%Y-%m-%d %H:%M")
  stop_str = (now_utc + timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M")

  params = {
      "format": "json",
      "COMMAND": f"'{jpl_id}'",
      "OBJ_DATA": "'NO'",
      "MAKE_EPHEM": "'YES'",
      "EPHEM_TYPE": "'OBSERVER'",
      "CENTER": "'500@399'",
      "START_TIME": f"'{start_str}'",
      "STOP_TIME": f"'{stop_str}'",
      "STEP_SIZE": "'2m'",
      "QUANTITIES": "'20'",
  }
  url = "https://ssd.jpl.nasa.gov/api/horizons.api?" + urllib.parse.urlencode(
      params
  )
  data = fetch_json(url, timeout=10)
  result_text = (data or {}).get("result", "")

  m = re.search(r"\$\$SOE\s*(.*?)\s*\$\$EOE", result_text, re.DOTALL)
  if not m:
    return None

  lines = [ln.strip() for ln in m.group(1).strip().splitlines() if ln.strip()]
  if not lines:
    return None

  parts = lines[0].split()
  if len(parts) < 3:
    return None

  delta_au = float(parts[2])
  dist_km = delta_au * AU_KM
  return {
      "epoch_utc": f"{parts[0]} {parts[1]} UTC",
      "earth_au": round(delta_au, 5),
      "earth_mkm": round(dist_km / 1_000_000.0, 2),
      "light_time": format_light_time(dist_km),
      "source": "NASA JPL HORIZONS EPHEMERIS",
  }


def get_donki_space_weather():
  now = time.time()
  if now - _donki_cache["ts"] < 1800 and (
      _donki_cache["flares"] or _donki_cache["cmes"]
  ):
    return _donki_cache

  end_dt = datetime.now(timezone.utc)
  start_dt = end_dt - timedelta(days=14)
  s_str = start_dt.strftime("%Y-%m-%d")
  e_str = end_dt.strftime("%Y-%m-%d")

  flares = []
  try:
    flr_url = (
        "https://api.nasa.gov/DONKI/FLR?"
        + urllib.parse.urlencode({
            "startDate": s_str,
            "endDate": e_str,
            "api_key": NASA_API_KEY,
        })
    )
    raw_flr = fetch_json(flr_url, timeout=8)
    if isinstance(raw_flr, list):
      for item in reversed(raw_flr[-6:]):
        flares.append({
            "class_type": item.get("classType", "N/A"),
            "peak_time": (item.get("peakTime") or "")
            .replace("T", " ")
            .replace("Z", " UTC"),
            "region": item.get("activeRegionNum") or "Unnumbered",
            "location": item.get("sourceLocation") or "Solar Disk",
        })
  except Exception:
    flares = _donki_cache["flares"]

  cmes = []
  try:
    cme_url = (
        "https://api.nasa.gov/DONKI/CME?"
        + urllib.parse.urlencode({
            "startDate": s_str,
            "endDate": e_str,
            "api_key": NASA_API_KEY,
        })
    )
    raw_cme = fetch_json(cme_url, timeout=8)
    if isinstance(raw_cme, list):
      for item in reversed(raw_cme[-6:]):
        analyses = item.get("cmeAnalyses") or []
        speed = "N/A"
        cme_type = "CME"
        if analyses:
          first_a = analyses[0]
          if first_a.get("speed") is not None:
            speed = f"{int(round(float(first_a['speed'])))} km/s"
          cme_type = first_a.get("type") or "CME"
        raw_note = item.get("note") or "Coronal mass ejection detected."
        cmes.append({
            "start_time": (item.get("startTime") or "")
            .replace("T", " ")
            .replace("Z", " UTC"),
            "speed": speed,
            "type": cme_type,
            "note": (raw_note[:120] + "...") if len(raw_note) > 120 else raw_note,
        })
  except Exception:
    cmes = _donki_cache["cmes"]

  _donki_cache.update({
      "ts": now,
      "flares": flares,
      "cmes": cmes,
  })
  return _donki_cache


def compute_station_pass_metrics(
    sat_lat, sat_lon, sat_alt_km, obs_lat, obs_lon, obs_alt_km
):
  R_e = 6371.0
  r_obs = R_e + obs_alt_km
  r_sat = R_e + sat_alt_km

  phi1 = math.radians(obs_lat)
  lam1 = math.radians(obs_lon)
  phi2 = math.radians(sat_lat)
  lam2 = math.radians(sat_lon)

  x1, y1, z1 = (
      r_obs * math.cos(phi1) * math.cos(lam1),
      r_obs * math.cos(phi1) * math.sin(lam1),
      r_obs * math.sin(phi1),
  )
  x2, y2, z2 = (
      r_sat * math.cos(phi2) * math.cos(lam2),
      r_sat * math.cos(phi2) * math.sin(lam2),
      r_sat * math.sin(phi2),
  )

  dx, dy, dz = x2 - x1, y2 - y1, z2 - z1
  slant_km = math.sqrt(dx * dx + dy * dy + dz * dz)

  ux, uy, uz = (
      math.cos(phi1) * math.cos(lam1),
      math.cos(phi1) * math.sin(lam1),
      math.sin(phi1),
  )
  dot_up = (dx * ux + dy * uy + dz * uz) / max(slant_km, 1e-6)
  elev_deg = math.degrees(math.asin(max(-1.0, min(1.0, dot_up))))

  nx = -math.sin(phi1) * math.cos(lam1)
  ny = -math.sin(phi1) * math.sin(lam1)
  nz = math.cos(phi1)

  ex = -math.sin(lam1)
  ey = math.cos(lam1)
  ez = 0.0

  east_comp = dx * ex + dy * ey + dz * ez
  north_comp = dx * nx + dy * ny + dz * nz
  az_deg = (math.degrees(math.atan2(east_comp, north_comp))) % 360.0

  return {
      "range_km": int(round(slant_km)),
      "elevation_deg": round(elev_deg, 1),
      "azimuth_deg": round(az_deg, 1),
      "above_horizon": elev_deg > 0.0,
  }


def fetch_nasa_image_topic(topic_query):
  today = utc_day_str()
  if _daily_nasa_cache["day_key"] != today:
    _daily_nasa_cache["galleries"] = {}

  if topic_query in _daily_nasa_cache["galleries"]:
    return _daily_nasa_cache["galleries"][topic_query]

  results = []
  try:
    query = urllib.parse.urlencode({
        "q": topic_query,
        "media_type": "image",
        "page": "1",
    })
    raw_imgs = fetch_json(f"https://images-api.nasa.gov/search?{query}")
    items = raw_imgs.get("collection", {}).get("items", [])

    day_num = datetime.now(timezone.utc).timetuple().tm_yday
    clean_items = []
    for it in items:
      links = it.get("links", [])
      meta_list = it.get("data", [])
      if not links or not meta_list:
        continue
      href = links[0].get("href", "")
      if not href:
        continue
      meta = meta_list[0]
      desc = (meta.get("description") or "").strip()
      if len(desc) > 200:
        desc = desc[:197].rsplit(" ", 1)[0] + "..."
      clean_items.append({
          "nasa_id": meta.get("nasa_id", "NASA"),
          "title": meta.get("title", "NASA Space Observation"),
          "date_created": (meta.get("date_created") or "")[:10],
          "description": desc or "NASA observation imagery and archival record.",
          "image_url": href,
      })

    if clean_items:
      offset = day_num % len(clean_items)
      rotated = clean_items[offset:] + clean_items[:offset]
      results = rotated[:6]
      _daily_nasa_cache["galleries"][topic_query] = results
  except Exception:
    pass

  return results


def _format_exo_rows(rows):
  out = []
  for r in rows or []:
    dist_pc = r.get("sy_dist")
    dist_ly = (
        f"{float(dist_pc) * 3.26156:.1f} ly" if dist_pc is not None else "N/A"
    )
    rad = r.get("pl_rade")
    rad_str = f"{float(rad):.2f}x Earth" if rad is not None else "Unknown"
    eqt = r.get("pl_eqt")
    temp_str = f"{int(round(float(eqt)))} K" if eqt is not None else "N/A"
    period = r.get("pl_orbper")
    period_str = f"{float(period):.1f} d" if period is not None else "N/A"
    out.append({
        "name": r.get("pl_name", "Unknown Exoplanet"),
        "host": r.get("hostname", "Unknown Star"),
        "year": r.get("disc_year", "Recent"),
        "method": r.get("discoverymethod", "Transit"),
        "distance": dist_ly,
        "radius": rad_str,
        "temp": temp_str,
        "period": period_str,
    })
  return out


def fetch_recent_exoplanets():
  try:
    tap_query = (
        "select top 8"
        " pl_name,hostname,disc_year,discoverymethod,sy_dist,pl_rade,pl_eqt,pl_orbper"
        " from pscomppars where disc_year >= 2024 and sy_dist is not null"
        " order by disc_year desc, pl_name asc"
    )
    url = (
        "https://exoplanetarchive.ipac.caltech.edu/TAP/sync?"
        + urllib.parse.urlencode({"query": tap_query, "format": "json"})
    )
    rows = fetch_json(url, timeout=9)
    formatted = _format_exo_rows(rows)
    if formatted:
      return formatted
  except Exception:
    pass
  return _daily_nasa_cache["exoplanets"]


def search_exoplanets(query_text):
  cleaned = "".join(
      ch for ch in query_text if ch.isalnum() or ch in " -._+"
  ).strip()
  if not cleaned:
    return []
  safe_like = cleaned.replace("'", "''")
  tap_query = (
      "select top 12"
      " pl_name,hostname,disc_year,discoverymethod,sy_dist,pl_rade,pl_eqt,pl_orbper"
      f" from pscomppars where lower(pl_name) like lower('%{safe_like}%')"
      f" or lower(hostname) like lower('%{safe_like}%') order by disc_year"
      " desc, pl_name asc"
  )
  url = (
      "https://exoplanetarchive.ipac.caltech.edu/TAP/sync?"
      + urllib.parse.urlencode({"query": tap_query, "format": "json"})
  )
  rows = fetch_json(url, timeout=9)
  return _format_exo_rows(rows)


def get_daily_nasa_feed():
  today = utc_day_str()
  if (
      _daily_nasa_cache["day_key"] == today
      and "exoplanet" in _daily_nasa_cache["galleries"]
  ):
    return _daily_nasa_cache

  _daily_nasa_cache["galleries"] = {}

  apod_data = _daily_nasa_cache["apod"]
  try:
    apod_url = (
        "https://api.nasa.gov/planetary/apod?"
        + urllib.parse.urlencode({"api_key": NASA_API_KEY, "thumbs": "true"})
    )
    raw_apod = fetch_json(apod_url)
    media_type = raw_apod.get("media_type", "image")
    img_url = (
        raw_apod.get("url", "")
        if media_type == "image"
        else raw_apod.get("thumbnail_url", "")
    )
    apod_data = {
        "title": raw_apod.get("title", "NASA Daily Feature"),
        "date": raw_apod.get("date", today),
        "media_type": media_type,
        "url": img_url,
        "explanation": raw_apod.get("explanation", ""),
    }
  except Exception:
    pass

  exo_discoveries = fetch_nasa_image_topic("exoplanet")
  recent_exoplanets = fetch_recent_exoplanets()

  neo_count = _daily_nasa_cache["neo_count"]
  try:
    neo_url = (
        "https://api.nasa.gov/neo/rest/v1/feed?"
        + urllib.parse.urlencode({
            "start_date": today,
            "end_date": today,
            "api_key": NASA_API_KEY,
        })
    )
    raw_neo = fetch_json(neo_url)
    neo_list = raw_neo.get("near_earth_objects", {}).get(today, [])
    neo_count = f"{len(neo_list)} NEOs"
  except Exception:
    if neo_count == "STANDBY":
      neo_count = "CACHED"

  _daily_nasa_cache.update({
      "day_key": today,
      "apod": apod_data,
      "exoplanets": recent_exoplanets,
      "neo_count": neo_count,
  })
  _daily_nasa_cache["galleries"]["exoplanet"] = exo_discoveries
  return _daily_nasa_cache


def get_space_weather():
  now = time.time()
  if now - _swpc_cache["ts"] < 600:
    return _swpc_cache

  try:
    url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
    rows = fetch_json(url, timeout=5)
    if isinstance(rows, list) and len(rows) > 1:
      latest = rows[-1]
      kp_val = float(latest[1])
      if kp_val >= 5.0:
        g_level = min(5, int(kp_val) - 4)
        scale = f"G{g_level} STORM"
      elif kp_val >= 4.0:
        scale = "ACTIVE / UNSETTLED"
      else:
        scale = "NOMINAL"

      _swpc_cache.update({
          "ts": now,
          "kp": f"{kp_val:.2f}",
          "kp_num": kp_val,
          "scale": scale,
          "updated_utc": str(latest[0]),
      })
  except Exception:
    if _swpc_cache["updated_utc"] == "STANDBY":
      _swpc_cache["updated_utc"] = "CACHED / OFFLINE"

  return _swpc_cache


def get_satellite_telemetry(obs_lat=DEFAULT_OBS_LAT, obs_lon=DEFAULT_OBS_LON):
  now = time.time()
  if now - _sat_cache["ts"] >= 5:
    try:
      url = "https://api.wheretheiss.at/v1/satellites/25544"
      data = fetch_json(url, timeout=5)
      _sat_cache.update({
          "ts": now,
          "name": "ISS (ZARYA)",
          "norad_id": str(data.get("id", "25544")),
          "lat": float(data["latitude"]),
          "lon": float(data["longitude"]),
          "alt_km": float(data["altitude"]),
          "vel_kmh": float(data["velocity"]),
          "visibility": str(data.get("visibility", "UNKNOWN")).upper(),
          "source": "LIVE TELEMETRY",
      })
    except Exception:
      if _sat_cache["source"] == "STANDBY":
        _sat_cache["source"] = "CACHED / STANDBY"

  pass_info = compute_station_pass_metrics(
      _sat_cache["lat"],
      _sat_cache["lon"],
      _sat_cache["alt_km"],
      obs_lat,
      obs_lon,
      DEFAULT_OBS_ALT_KM,
  )

  return {
      "name": _sat_cache["name"],
      "norad_id": _sat_cache["norad_id"],
      "lat": f"{_sat_cache['lat']:.4f}",
      "lon": f"{_sat_cache['lon']:.4f}",
      "alt_km": f"{_sat_cache['alt_km']:.1f}",
      "vel_kmh": f"{_sat_cache['vel_kmh']:.0f}",
      "visibility": _sat_cache["visibility"],
      "source": _sat_cache["source"],
      "station_range_km": pass_info["range_km"],
      "station_elev_deg": pass_info["elevation_deg"],
      "station_az_deg": pass_info["azimuth_deg"],
      "above_horizon": pass_info["above_horizon"],
  }


def get_usgs_earthquakes(min_mag="2.5", region="global"):
  min_mag = str(min_mag).strip()
  if min_mag not in {"all", "1.0", "2.5", "4.5"}:
    min_mag = "2.5"
  region = (region or "global").strip().lower()
  cache_key = f"{min_mag}:{region}"
  now = time.time()
  if _eq_cache["key"] == cache_key and (now - _eq_cache["ts"]) < 300:
    return _eq_cache["quakes"]

  if region == "se":
    start_dt = (datetime.now(timezone.utc) - timedelta(days=30)).strftime(
        "%Y-%m-%d"
    )
    mag_val = "0.0" if min_mag == "all" else min_mag
    url = (
        "https://earthquake.usgs.gov/fdsnws/event/1/query?"
        + urllib.parse.urlencode({
            "format": "geojson",
            "starttime": start_dt,
            "minmagnitude": mag_val,
            "minlatitude": "24.0",
            "maxlatitude": "39.0",
            "minlongitude": "-92.0",
            "maxlongitude": "-75.0",
            "limit": "8",
        })
    )
  else:
    feed_mag = "0.0" if min_mag == "all" else min_mag
    start_dt = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(
        "%Y-%m-%d"
    )
    url = (
        "https://earthquake.usgs.gov/fdsnws/event/1/query?"
        + urllib.parse.urlencode({
            "format": "geojson",
            "starttime": start_dt,
            "minmagnitude": feed_mag,
            "limit": "8",
        })
    )

  quakes = []
  try:
    raw = fetch_json(url, timeout=8)
    for feat in (raw or {}).get("features", [])[:8]:
      props = feat.get("properties") or {}
      geom = (feat.get("geometry") or {}).get("coordinates") or [0, 0, 0]
      mag = props.get("mag")
      mag_str = f"{float(mag):.1f}" if mag is not None else "N/A"
      depth_km = (
          f"{float(geom[2]):.1f} km"
          if len(geom) > 2 and geom[2] is not None
          else "N/A"
      )
      t_ms = props.get("time")
      if t_ms:
        t_str = datetime.fromtimestamp(
            float(t_ms) / 1000.0, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M UTC")
      else:
        t_str = "Recent"
      quakes.append({
          "mag": mag_str,
          "place": props.get("place") or "Unknown Seismic Zone",
          "depth": depth_km,
          "time_utc": t_str,
          "url": (
              props.get("url")
              or "https://earthquake.usgs.gov/earthquakes/map/"
          ),
      })
    _eq_cache.update({"key": cache_key, "ts": now, "quakes": quakes})
  except Exception:
    quakes = _eq_cache["quakes"]

  return quakes


@app.route("/api/earthquakes")
def api_earthquakes():
  min_mag = request.args.get("mag", "2.5")
  region = request.args.get("region", "global")
  return jsonify({"quakes": get_usgs_earthquakes(min_mag=min_mag, region=region)})


@app.route("/api/satellite")
def api_satellite():
  try:
    obs_lat = float(request.args.get("lat", DEFAULT_OBS_LAT))
    obs_lon = float(request.args.get("lon", DEFAULT_OBS_LON))
  except ValueError:
    obs_lat, obs_lon = DEFAULT_OBS_LAT, DEFAULT_OBS_LON
  return jsonify(get_satellite_telemetry(obs_lat, obs_lon))


@app.route("/api/planets")
def api_planets():
  try:
    day_offset = float(request.args.get("days", "0"))
    day_offset = max(-365.0, min(730.0, day_offset))
  except ValueError:
    day_offset = 0.0
  return jsonify(get_planetary_positions(day_offset=day_offset))


@app.route("/api/jpl-horizons")
def api_jpl_horizons():
  pid = request.args.get("planet", "mars").strip().lower()
  target = next((el for el in PLANET_ELEMENTS if el["id"] == pid), None)
  if not target or pid == "earth":
    return (
        jsonify({"error": "Select a non-Earth planet for JPL Horizons query."}),
        400,
    )
  try:
    ephem = query_jpl_horizons(target["jpl_id"])
    if not ephem:
      return jsonify({"error": "JPL Horizons response unavailable."}), 502
    ephem["planet"] = target["name"]
    return jsonify(ephem)
  except Exception:
    return jsonify({"error": "JPL Horizons connection timeout."}), 502


@app.route("/api/nasa-gallery")
def api_nasa_gallery():
  topic = request.args.get("topic", "exoplanet").strip().lower()
  if topic not in ALLOWED_GALLERY_TOPICS:
    topic = "exoplanet"
  items = fetch_nasa_image_topic(topic)
  return jsonify({
      "topic": topic,
      "label": ALLOWED_GALLERY_TOPICS[topic],
      "items": items,
  })


@app.route("/api/exoplanet-search")
def api_exoplanet_search():
  q = request.args.get("q", "").strip()
  if len(q) < 2:
    return jsonify({"results": [], "query": q})
  try:
    results = search_exoplanets(q)
    return jsonify({"results": results, "query": q})
  except Exception:
    return jsonify({"results": [], "query": q, "error": "Search unavailable"})


@app.route("/guestbook/post", methods=["POST"])
def guestbook_post():
  name = request.form.get("gb_name", "").strip()[:40]
  location = request.form.get("gb_location", "").strip()[:40]
  message = request.form.get("gb_message", "").strip()[:320]
  if name and message:
    entries = load_guestbook()
    entry_id = f"GB-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    entries.insert(
        0,
        {
            "id": entry_id,
            "name": name,
            "location": location or "Earth Station",
            "message": message,
            "reply": "",
            "created_utc": datetime.now(timezone.utc).strftime(
                "%Y-%m-%d %H:%M UTC"
            ),
        },
    )
    save_guestbook(entries[:30])
  return redirect(url_for("index") + "#mission-guestbook")


@app.route("/guestbook/reply/<entry_id>", methods=["POST"])
@team_required
def guestbook_reply(entry_id):
  reply_txt = request.form.get("gb_reply", "").strip()[:320]
  entries = load_guestbook()
  for e in entries:
    if e.get("id") == entry_id:
      e["reply"] = reply_txt
      e["reply_by"] = session.get("operator", "VGA1")
      break
  save_guestbook(entries)
  return redirect(url_for("index") + "#mission-guestbook")


@app.route("/guestbook/delete/<entry_id>", methods=["POST"])
@team_required
def guestbook_delete(entry_id):
  entries = [e for e in load_guestbook() if e.get("id") != entry_id]
  save_guestbook(entries)
  return redirect(url_for("index") + "#mission-guestbook")


@app.route("/export/missions.csv")
def export_missions_csv():
  missions = load_missions()
  buf = io.StringIO()
  writer = csv.writer(buf)
  writer.writerow([
      "id",
      "title",
      "status",
      "platform",
      "author",
      "updated_utc",
      "objectives",
      "notes",
      "takeaways",
  ])
  for m in missions:
    writer.writerow([
        m.get("id", ""),
        m.get("title", ""),
        m.get("status", ""),
        m.get("platform", ""),
        m.get("author", ""),
        m.get("updated_utc", ""),
        m.get("objectives", ""),
        m.get("notes", ""),
        m.get("takeaways", ""),
    ])
  return Response(
      buf.getvalue(),
      mimetype="text/csv",
      headers={
          "Content-Disposition": "attachment; filename=vortex-ghost-missions.csv"
      },
  )


@app.route("/team/banner", methods=["POST"])
@team_required
def update_banner():
  msg = request.form.get("banner_message", "").strip()
  level = request.form.get("banner_level", "INFO").strip().upper()
  if level not in {"INFO", "LIVE", "ALERT"}:
    level = "INFO"

  if not msg:
    save_banner(
        {"message": "", "level": "INFO", "updated_utc": "", "author": ""}
    )
  else:
    save_banner({
        "message": msg,
        "level": level,
        "updated_utc": datetime.now(timezone.utc).strftime(
            "%Y-%m-%d %H:%M UTC"
        ),
        "author": session.get("operator", "VGA1"),
    })
  return redirect(url_for("index"))


@app.route("/team/login", methods=["POST"])
def team_login():
  operator = request.form.get("operator", "").strip().upper()
  passcode = request.form.get("passcode", "").strip()

  expected_callsign = os.environ.get("TEAM_CALLSIGN", "VGA1").strip().upper()
  expected_pass = os.environ.get("TEAM_PASS", "Vortex").strip()

  if operator == expected_callsign and passcode == expected_pass:
    session.clear()
    session["team_auth"] = True
    session["operator"] = expected_callsign
    session.modified = True
    return redirect(url_for("index") + "#dispatch-panel")

  return redirect(
      url_for("index", auth_msg="Invalid Team Callsign or Password.")
      + "#team-access"
  )


@app.route("/team/logout", methods=["POST"])
def team_logout():
  session.clear()
  return redirect(url_for("index"))


@app.route("/")
def index():
  status_filter = request.args.get("status", "ALL").upper()
  valid_statuses = {"ALL", "ACTIVE", "IN DEVELOPMENT", "COMPLETED"}
  if status_filter not in valid_statuses:
    status_filter = "ALL"

  all_missions = load_missions()
  if status_filter == "ALL":
    filtered_missions = all_missions
  else:
    filtered_missions = [
        m for m in all_missions if m.get("status", "").upper() == status_filter
    ]

  planet_data = get_planetary_positions()
  nasa_feed = get_daily_nasa_feed()
  initial_gallery = nasa_feed.get("galleries", {}).get("exoplanet", [])
  day_num = datetime.now(timezone.utc).timetuple().tm_yday
  word_of_day = SPACE_GLOSSARY[day_num % len(SPACE_GLOSSARY)]

  return render_template(
      "index.html",
      missions=filtered_missions,
      total_missions=len(all_missions),
      active_filter=status_filter,
      banner=load_banner(),
      guestbook=load_guestbook(),
      sky_photos=load_sky_photos(),
      us_states=US_STATES_COORDS,
      sky_scorecard=get_nws_sky_scorecard("AL"),
      probes=DEEP_SPACE_PROBES,
      payloads=PAYLOAD_MANIFEST,
      briefings=BRIEFING_LINKS,
      glossary=SPACE_GLOSSARY,
      word_of_day=word_of_day,
      geoscience_topics=GEOSCIENCE_TOPICS,
      earthquakes=get_usgs_earthquakes(min_mag="2.5", region="global"),
      space_wx=get_space_weather(),
      donki_wx=get_donki_space_weather(),
      sat_wx=get_satellite_telemetry(),
      nasa_feed=nasa_feed,
      initial_gallery=initial_gallery,
      gallery_topics=ALLOWED_GALLERY_TOPICS,
      planet_data=planet_data,
      obs_lat=DEFAULT_OBS_LAT,
      obs_lon=DEFAULT_OBS_LON,
      is_team=is_team_authenticated(),
      operator=session.get("operator", "PUBLIC VIEW"),
      auth_msg=request.args.get("auth_msg", ""),
  )


@app.route("/mission/<mission_id>")
def mission_detail(mission_id):
  missions = load_missions()
  for m in missions:
    if m.get("id", "").upper() == mission_id.upper():
      return render_template(
          "mission_detail.html",
          mission=m,
          space_wx=get_space_weather(),
          is_team=is_team_authenticated(),
      )
  abort(404)


@app.route("/add-log", methods=["POST"])
@team_required
def add_log():
  mission_id = request.form.get("mission_id", "").strip().upper()
  title = request.form.get("title", "").strip()
  platform = request.form.get("platform", "").strip()
  status = request.form.get("status", "ACTIVE").strip().upper()
  objectives = request.form.get("objectives", "").strip()
  notes = request.form.get("notes", "").strip()
  takeaways = request.form.get("takeaways", "").strip()
  author = session.get("operator", "VGA1")

  if status not in {"ACTIVE", "IN DEVELOPMENT", "COMPLETED"}:
    status = "ACTIVE"

  if mission_id and title and platform and notes:
    missions = load_missions()
    if any(m.get("id", "").upper() == mission_id for m in missions):
      mission_id = (
          f"{mission_id}-{datetime.now(timezone.utc).strftime('%H%M%S')}"
      )

    utc_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    missions.insert(
        0,
        {
            "id": mission_id,
            "title": title,
            "status": status,
            "platform": platform,
            "objectives": objectives,
            "notes": f"[{utc_stamp} // {author}] {notes}",
            "takeaways": takeaways,
            "updated_utc": utc_stamp,
            "author": author,
        },
    )
    save_missions(missions)

  return redirect(url_for("index"))


@app.route("/mission/<mission_id>/edit", methods=["GET", "POST"])
@team_required
def edit_mission(mission_id):
  missions = load_missions()
  target_idx = None
  for idx, m in enumerate(missions):
    if m.get("id", "").upper() == mission_id.upper():
      target_idx = idx
      break

  if target_idx is None:
    abort(404)

  if request.method == "POST":
    title = request.form.get("title", "").strip()
    platform = request.form.get("platform", "").strip()
    status = request.form.get("status", "ACTIVE").strip().upper()
    objectives = request.form.get("objectives", "").strip()
    notes = request.form.get("notes", "").strip()
    takeaways = request.form.get("takeaways", "").strip()
    author = session.get("operator", "VGA1")

    if status not in {"ACTIVE", "IN DEVELOPMENT", "COMPLETED"}:
      status = "ACTIVE"

    if title and platform and notes:
      utc_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
      missions[target_idx].update({
          "title": title,
          "platform": platform,
          "status": status,
          "objectives": objectives,
          "notes": notes,
          "takeaways": takeaways,
          "updated_utc": utc_stamp,
          "author": author,
      })
      save_missions(missions)
      return redirect(
          url_for("mission_detail", mission_id=missions[target_idx]["id"])
      )

  return render_template(
      "edit_mission.html",
      mission=missions[target_idx],
      operator=session.get("operator", "VGA1"),
  )


@app.route("/mission/<mission_id>/delete", methods=["POST"])
@team_required
def delete_mission(mission_id):
  missions = load_missions()
  remaining = [
      m for m in missions if m.get("id", "").upper() != mission_id.upper()
  ]
  save_missions(remaining)
  return redirect(url_for("index"))


@app.route("/admin")
@team_required
def admin_panel():
  return redirect(url_for("index") + "#dispatch-panel")


@app.route("/sky-photos/upload", methods=["POST"])
@team_required
def upload_sky_photo():
  file = request.files.get("sky_photo")
  caption = request.form.get("photo_caption", "").strip()[:140]
  subject = request.form.get("photo_subject", "Moon").strip()[:40]
  location = request.form.get("photo_location", "Sylacauga, AL").strip()[:50]

  if not file or not file.filename:
    return redirect(url_for("index") + "#moon-sky-photos")

  ext = os.path.splitext(secure_filename(file.filename))[1].lower()
  if ext not in ALLOWED_IMAGE_EXTS:
    return redirect(url_for("index") + "#moon-sky-photos")

  stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
  safe_name = f"sky_{stamp}{ext}"
  dest_path = os.path.join(UPLOAD_FOLDER, safe_name)
  file.save(dest_path)

  photo_id = f"SKY-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
  photos = load_sky_photos()
  photos.insert(
      0,
      {
          "id": photo_id,
          "filename": safe_name,
          "image_url": url_for("static", filename=f"sky_uploads/{safe_name}"),
          "subject": subject or "Moon / Night Sky",
          "caption": caption or "Field sky observation capture",
          "location": location or "Sylacauga, AL",
          "author": session.get("operator", "VGA1"),
          "uploaded_utc": datetime.now(timezone.utc).strftime(
              "%Y-%m-%d %H:%M UTC"
          ),
      },
  )
  save_sky_photos(photos[:30])
  return redirect(url_for("index") + "#moon-sky-photos")


@app.route("/sky-photos/delete/<photo_id>", methods=["POST"])
@team_required
def delete_sky_photo(photo_id):
  photos = load_sky_photos()
  remaining = []
  for p in photos:
    if p.get("id") == photo_id:
      fname = p.get("filename", "")
      if fname:
        fpath = os.path.join(UPLOAD_FOLDER, secure_filename(fname))
        if os.path.exists(fpath):
          try:
            os.remove(fpath)
          except Exception:
            pass
    else:
      remaining.append(p)
  save_sky_photos(remaining)
  return redirect(url_for("index") + "#moon-sky-photos")


if __name__ == "__main__":
  app.run(host="0.0.0.0", port=5000, debug=True)
