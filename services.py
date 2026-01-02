import json
import os
import re
import googlemaps
import google.generativeai as genai
from supabase import create_client, Client
from dotenv import load_dotenv
from pathlib import Path

# 1. BULLETPROOF ENV LOADING
BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / '.env'
load_dotenv(dotenv_path=env_path)

print(f"🔍 Looking for .env at: {env_path}")

# 2. LOAD KEYS
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_MAPS_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

# Initialize globals
supabase = None
gmaps = None

# 3. SETUP CLIENTS
try:
    if not all([SUPABASE_URL, SUPABASE_KEY, GEMINI_KEY, GOOGLE_MAPS_KEY]):
        print("⚠️ CRITICAL WARNING: Keys are missing. Check .env")
    else:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        genai.configure(api_key=GEMINI_KEY)
        gmaps = googlemaps.Client(key=GOOGLE_MAPS_KEY)
        print("✅ Asta Engine: All Systems Go (Hybrid AI + Maps + DB)")

except Exception as e:
    print(f"❌ Client Setup Error: {e}")

# --- CORE SERVICE ---
async def process_text_to_property(raw_text: str) -> dict:
    
    clean_loc = "Accra"
    data = {}
    ai_success = False

    # 🧠 STEP 1: TRY AI (The "Smart" Way)
    try:
        # Using the alias 'gemini-flash-latest' which is safer for free tiers
        model = genai.GenerativeModel('gemini-flash-latest')
        
        prompt = f"""
        You are Asta, an expert Real Estate AI.
        Extract data from the user's text into strict JSON format.
        
        Output Schema:
        {{
          "title": "Short catchy title (e.g. Modern 2-Bed in Osu)",
          "price": 0,
          "currency": "GHS",
          "location_name_clean": "Neighborhood Name",
          "type": "rent" or "sale",
          "features": ["Tag1", "Tag2"],
          "description": "Professional 2-sentence summary."
        }}
        
        RAW TEXT:
        {raw_text}
        """
        
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        
        # Strip Markdown if present
        cleaned_text = re.sub(r"```json|```", "", response.text).strip()
        data = json.loads(cleaned_text)
        
        if isinstance(data, list): data = data[0]
        
        clean_loc = data.get("location_name_clean", "Accra")
        ai_success = True
        print(f"📍 AI Identified: {clean_loc}")

    except Exception as e:
        print(f"⚠️ AI Parsing Failed (Quota/Error). Switching to Manual Logic.")
        print(f"   Reason: {e}")

    # 🔧 STEP 1.5: MANUAL FALLBACK (The "Reliable" Way)
    if not ai_success:
        print("🤖 ENGAGING MANUAL PARSER")
        lower_text = raw_text.lower()
        
        # Simple extraction logic
        if "east legon" in lower_text: clean_loc = "East Legon"
        elif "osu" in lower_text: clean_loc = "Osu"
        elif "cantonments" in lower_text: clean_loc = "Cantonments"
        elif "airport" in lower_text: clean_loc = "Airport Residential"
        elif "tema" in lower_text: clean_loc = "Tema"
        
        # Price extraction regex
        price_match = re.search(r'(\d{1,3}(?:,\d{3})*)', raw_text)
        price = int(price_match.group(1).replace(',', '')) if price_match else 0
        
        data = {
            "title": f"New Listing in {clean_loc}",
            "price": price,
            "currency": "GHS",
            "type": "sale" if "buy" in lower_text or "sale" in lower_text else "rent",
            "features": ["Manual Entry", "Verified"],
            "description": f"Automated listing detected in {clean_loc}. {raw_text[:50]}..."
        }
        print(f"📍 Manual Parser Identified: {clean_loc}")

    # 🌍 STEP 2: GEOCODING (This relies on Maps Key, which works!)
    lat, lng, address = 0.0, 0.0, clean_loc
    is_mapped = False
    
    try:
        # We append 'Ghana' to constrain results
        geocode_res = gmaps.geocode(f"{clean_loc}, Accra, Ghana")
        if geocode_res:
            loc_obj = geocode_res[0]['geometry']['location']
            lat = loc_obj['lat']
            lng = loc_obj['lng']
            address = geocode_res[0]['formatted_address']
            is_mapped = True
            print(f"🌍 Geocoded to: {lat}, {lng} ({address})")
        else:
            print("⚠️ Geocoding returned no results.")
    except Exception as map_err:
        print(f"❌ Maps Error: {map_err}")

    # Merge Data
    final_property = {
        "title": data.get("title"),
        "price": data.get("price"),
        "currency": "GHS",
        "location_name": clean_loc,
        "location_address": address,
        "lat": lat if is_mapped else None,
        "long": lng if is_mapped else None,
        "type": data.get("type", "rent"),
        "features": data.get("features", []),
        "description": data.get("description"),
        "location_accuracy": "high" if is_mapped else "low",
        "status": "active" if is_mapped else "draft"
    }
    
    return final_property

async def save_to_db(property_data: dict):
    if not property_data: return None
    print(f"💾 Saving to Vault: {property_data.get('title')}")
    response = supabase.table('properties').insert(property_data).execute()
    return response.data
