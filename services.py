import json
import os
import google.generativeai as genai
import googlemaps
from supabase import create_client, Client
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Optional
from pathlib import Path

# 1. BULLETPROOF ENV LOADING
BASE_DIR = Path(__file__).resolve().parent.parent # Go up one level to find root .env if needed
env_path = BASE_DIR / '.env'
load_dotenv(dotenv_path=env_path)

# 2. LOAD KEYS
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GOOGLE_MAPS_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

# 3. SETUP CLIENTS
try:
    if not all([SUPABASE_URL, SUPABASE_KEY, GEMINI_KEY, GOOGLE_MAPS_KEY]):
        print("⚠️ WARNING: One or more keys are missing. Check .env")

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    genai.configure(api_key=GEMINI_KEY)
    gmaps = googlemaps.Client(key=GOOGLE_MAPS_KEY)
    print("✅ Asta Engine: All Systems Go (AI + Maps + DB)")
except Exception as e:
    print(f"❌ Client Setup Error: {e}")

# --- CORE SERVICE ---
async def process_text_to_property(raw_text: str) -> dict:
    """
    The Brain:
    1. AI extracts clean location name + features.
    2. Google Maps converts location name to Lat/Long.
    """
    model = genai.GenerativeModel('gemini-2.0-flash-exp')
    
    # 🧠 STEP 1: AI PARSING (No coords, just text)
    prompt = f"""
    You are Asta, an expert Real Estate AI.
    Analyze this raw text from a WhatsApp user.
    
    Tasks:
    1. Extract the specific Neighborhood/Suburb (e.g., "East Legon", "Teshie-Nungua").
    2. Extract price (Number only).
    3. Extract features as a list of tags.
    4. Write a professional 2-sentence description.

    Return EXACT JSON:
    {{
      "title": "Short catchy title (e.g. Modern 2-Bed in Osu)",
      "price": 0,
      "location_name_clean": "Neighborhood Name",
      "type": "rent" or "sale",
      "vibe_features": ["Tag1", "Tag2"],
      "description": "Professional summary."
    }}
    
    RAW TEXT:
    {raw_text}
    """
    
    try:
        # Ask Gemini
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        data = json.loads(response.text)
        if isinstance(data, list): data = data[0]

        clean_loc = data.get("location_name_clean", "Accra")
        print(f"📍 AI Identified: {clean_loc}")

        # 🌍 STEP 2: GEOCODING (The Anchor)
        lat, lng, address = 0.0, 0.0, clean_loc
        try:
            # We append 'Ghana' to constrain results
            geocode_res = gmaps.geocode(f"{clean_loc}, Accra, Ghana")
            if geocode_res:
                loc_obj = geocode_res[0]['geometry']['location']
                lat = loc_obj['lat']
                lng = loc_obj['lng']
                address = geocode_res[0]['formatted_address']
                print(f"🌍 Geocoded to: {lat}, {lng} ({address})")
            else:
                print("⚠️ Geocoding returned no results. Defaulting to 0,0")
        except Exception as map_err:
            print(f"❌ Maps Error: {map_err}")

        # Merge Data
        final_property = {
            "title": data.get("title"),
            "price": data.get("price"),
            "location_name": clean_loc,
            "location_address": address,
            "lat": lat,
            "long": lng,
            "type": data.get("type", "rent"),
            "vibe_features": json.dumps(data.get("vibe_features", [])), # Store as JSON string
            "description_enriched": data.get("description"),
            "description": data.get("description"), # Legacy field
            "location_accuracy": "high" if lat != 0 else "low"
        }
        
        return final_property

    except Exception as e:
        print(f"❌ AI Parsing Error: {e}")
        return None

async def save_to_db(property_data: dict):
    try:
        # Ensure we don't insert None
        if not property_data: return None

        print(f"💾 Saving to Vault: {property_data.get('title')}")
        response = supabase.table('properties').insert(property_data).execute()
        return response.data
    except Exception as e:
        print(f"❌ DB Save Error: {e}")
        return None
