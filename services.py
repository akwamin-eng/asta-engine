import os
import json
import random
import google.generativeai as genai
from supabase import create_client, Client
from dotenv import load_dotenv

# 1. Load Keys
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
PRIMARY_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash") 

# 2. Configure Services
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GOOGLE_API_KEY)

# 3. Resilience Strategy
FALLBACK_MODELS = [
    PRIMARY_MODEL,
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash-exp",
    "gemini-1.0-pro"
]

# 4. 🇬🇭 GEOGRAPHIC BOUNDARIES (Approximate Box around Ghana)
GHANA_BOUNDS = {
    'min_lat': 4.5,  'max_lat': 11.2,
    'min_long': -3.3, 'max_long': 1.2
}
ACCRA_DEFAULT = {'lat': 5.6037, 'long': -0.1870}

async def get_ai_response(prompt: str):
    """
    Tries to get a response from Google AI, cycling through models if one fails.
    """
    models_to_try = list(dict.fromkeys(FALLBACK_MODELS))
    
    for model_name in models_to_try:
        try:
            print(f"🤖 Attempting with model: {model_name}...")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return response
        except Exception as e:
            print(f"⚠️ Model {model_name} failed: {e}")
            continue 
            
    raise Exception("All AI models failed to respond.")

def validate_coordinates(data):
    """
    Checks if coordinates are within Ghana. 
    If they are 0,0 (Ocean) or way off, force them to Accra.
    """
    lat = data.get('lat', 0)
    long = data.get('long', 0)
    
    # Check if null, zero, or outside bounds
    if (lat == 0 and long == 0) or \
       not (GHANA_BOUNDS['min_lat'] <= lat <= GHANA_BOUNDS['max_lat']) or \
       not (GHANA_BOUNDS['min_long'] <= long <= GHANA_BOUNDS['max_long']):
        
        print(f"⚠️ Coordinates {lat},{long} are invalid/outside Ghana. Defaulting to Accra.")
        # We set it to Accra, but rely on the jitter later to separate them
        data['lat'] = ACCRA_DEFAULT['lat']
        data['long'] = ACCRA_DEFAULT['long']
    
    return data

async def process_text_to_property(raw_text: str):
    print(f"🧠 Processing: {raw_text[:50]}...")

    prompt = f"""
    Extract real estate data from this text into JSON.
    For 'lat' and 'long', provide the ACTUAL coordinates for the specific neighborhood mentioned.
    DO NOT use generic Accra center if possible.
    
    Fields:
    - title: Short summary.
    - price: Numeric price in GHS (Assume 1 USD = 15 GHS).
    - location_name: The specific neighborhood.
    - type: 'rent' or 'sale'.
    - lat: Specific latitude.
    - long: Specific longitude.
    - vibe_features: Keywords.

    Text: "{raw_text}"
    Return ONLY valid JSON.
    """

    try:
        # 1. Get AI Response (Resilient)
        response = await get_ai_response(prompt)
        cleaned_response = response.text.replace('```json', '').replace('```', '').strip()
        data = json.loads(cleaned_response)
        
        # 2. 🛡️ Validate Location (The Shield)
        data = validate_coordinates(data)
        
        # 3. Add Random Jitter (So pins don't stack perfectly on top of each other)
        data['lat'] += random.uniform(-0.002, 0.002)
        data['long'] += random.uniform(-0.002, 0.002)
        
        data['status'] = 'active'
        
        print(f"✅ Extracted: {data['location_name']} @ {data['lat']:.4f}, {data['long']:.4f}")
        return data

    except Exception as e:
        print(f"❌ Extraction Error: {e}")
        return None

async def save_to_db(property_data: dict):
    try:
        response = supabase.table('properties').insert(property_data).execute()
        print("💾 Saved to Database!")
        return response.data
    except Exception as e:
        print(f"❌ Database Error: {e}")
        return None
