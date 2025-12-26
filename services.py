import json
import os
import google.generativeai as genai
from supabase import create_client, Client
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Optional
from pathlib import Path

# 1. BULLETPROOF ENV LOADING
BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / '.env'

if env_path.exists():
    print(f"✅ Found .env file at: {env_path}")
    load_dotenv(dotenv_path=env_path)
else:
    print(f"❌ ERROR: .env file NOT found at: {env_path}")

# 2. LOAD KEYS (Smart Check)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")

# Check both common names for the AI key
GEMINI_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

if not SUPABASE_KEY:
    print("❌ CRITICAL: SUPABASE_KEY is missing from .env")
if not GEMINI_KEY:
    print("❌ CRITICAL: GOOGLE_API_KEY is missing from .env")
else:
    print("✅ AI Key Found.")

# 3. SETUP CLIENTS
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    genai.configure(api_key=GEMINI_KEY)
except Exception as e:
    print(f"⚠️ Client Setup Warning: {e}")

# --- DATA MODELS ---
class Property(BaseModel):
    title: str
    price: float
    location_name: str
    lat: float
    long: float
    type: str
    vibe_features: str
    description: str  
    image_url: Optional[str] = None

# --- CORE SERVICE ---
async def process_text_to_property(raw_text: str) -> dict:
    # Use the model that works
    model = genai.GenerativeModel('gemini-2.0-flash-exp')
    
    prompt = f"""
    You are Asta, an expert Real Estate AI.
    Extract the listing into this EXACT JSON structure.
    
    {{
      "title": "Short catchy title",
      "price": 12345 (Number only, convert to GHS),
      "location_name": "Neighborhood Name",
      "lat": 5.123,
      "long": -0.123,
      "type": "rent" or "sale",
      "vibe_features": "TAG1, TAG2, TAG3",
      "description": "Write a 2-sentence marketing summary here. Make it professional."
    }}
    
    RAW TEXT:
    {raw_text}
    """
    
    try:
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        
        data = json.loads(response.text)

        # Handle List vs Dict
        if isinstance(data, list):
            if len(data) > 0:
                data = data[0]
            else:
                return None

        print("------------------------------------------------")
        print("🤖 AI DESCRIPTION:", data.get("description"))
        print("------------------------------------------------")
        
        return data

    except Exception as e:
        print(f"❌ AI Error: {e}")
        # Fallback to older model
        try:
             print("⚠️ Retrying with gemini-1.5-flash...")
             model_backup = genai.GenerativeModel('gemini-1.5-flash')
             response = model_backup.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
             data = json.loads(response.text)
             if isinstance(data, list): data = data[0]
             return data
        except Exception as e2:
             print(f"❌ Backup failed: {e2}")
             return None

async def save_to_db(property_data: dict):
    try:
        print(f"💾 Saving: {property_data.get('title')}")
        response = supabase.table('properties').insert(property_data).execute()
        return response.data
    except Exception as e:
        print(f"❌ DB Error: {e}")
        return None
