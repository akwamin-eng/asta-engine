import os
import sys
import time
import requests 
import json

def run_asta_pipeline():
    print("🤖 Asta Autopilot: Starting Pipeline (Delegator Mode)...")

    # 1. Check Environment Variables
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") # Uses Admin key for backend ops

    if not all([SUPABASE_URL, SUPABASE_KEY]):
        print("❌ Error: Missing Supabase Credentials.")
        print(f"   - SUPABASE_URL: {'Found' if SUPABASE_URL else 'Missing'}")
        print(f"   - SUPABASE_KEY: {'Found' if SUPABASE_KEY else 'Missing'}")
        sys.exit(1)

    # 2. Configuration for Edge Function (The Central Brain)
    FUNCTION_URL = f"{SUPABASE_URL}/functions/v1/enrich-news"
    HEADERS = {
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }

    # 3. Initialize Supabase Client (For fetching lists)
    try:
        from supabase import create_client, Client
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase Client loaded.")
    except ImportError:
        print("❌ Critical: 'supabase' library not found.")
        sys.exit(1)

    # 4. Run Analysis Logic
    print("🔍 Checking for pending intelligence (Backlog)...")
    
    # Fetch Pending News (Items that the Trigger might have missed)
    response = supabase.table('market_news')\
        .select("*")\
        .eq('status', 'pending_enrichment')\
        .limit(20)\
        .execute()
    
    news_items = response.data
    
    if not news_items:
        print("💤 No pending items found. System Clean.")
        return

    print(f"⚡ Delegating {len(news_items)} assets to Asta Brain (Edge Function)...")

    for item in news_items:
        try:
            print(f"   ↳ Processing: {item.get('title', 'Unknown')[:40]}...")
            
            # We send the record to the Edge Function exactly as the DB Trigger would
            payload = { "record": item }
            
            # Call the Central Brain
            func_response = requests.post(FUNCTION_URL, headers=HEADERS, json=payload)
            
            if func_response.status_code == 200:
                print("      ✅ Enriched via Edge!")
            else:
                print(f"      ⚠️ Edge Error: {func_response.text}")
            
            # Polite Rate Limiting
            time.sleep(1)

        except Exception as e:
            print(f"      ❌ Transmission Failed: {e}")

    print("✅ Pipeline Step Complete.")

if __name__ == "__main__":
    run_asta_pipeline()
