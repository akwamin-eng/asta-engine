import os
import requests
import sys
from supabase import create_client, Client
from datetime import datetime

# --- Configuration ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
API_KEY = os.environ.get("EXCHANGE_RATE_API_KEY")

# Fallback if key is missing
if not API_KEY:
    API_KEY = "05951d1e4b50bce1dd0b51cc" 

BASE_URL = f"https://v6.exchangerate-api.com/v6/{API_KEY}/latest/USD"

def update_rates():
    print("💱 [Currency Sync] Starting...")
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Error: Supabase credentials missing.")
        sys.exit(1)

    try:
        # Fetch Data
        response = requests.get(BASE_URL)
        data = response.json()
        
        if data.get("result") != "success":
            raise Exception(f"API Error: {data.get('error-type', 'Unknown error')}")
            
        ghs_rate = data["conversion_rates"]["GHS"]
        print(f"✅ Rate Acquired: 1 USD = {ghs_rate} GHS")
        
        # Sync to Supabase
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        current_time = datetime.utcnow().isoformat()
        
        payload = {
            "key": "usd_exchange_rate", 
            "value": {
                "rate": ghs_rate, 
                "source": "ExchangeRate-API",
                "fetched_at": current_time
            }, 
            "description": "Live USD to GHS exchange rate",
            "last_updated": current_time
        }
        
        supabase.table("system_config").upsert(payload, on_conflict="key").execute()
        print("💾 Database Updated: 'system_config' table synced.")
        
    except Exception as e:
        print(f"❌ Failed to update currency: {e}")
        sys.exit(1)

if __name__ == "__main__":
    update_rates()
