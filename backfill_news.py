import requests
import json
import time

# --- CONFIGURATION ---
SUPABASE_URL = "https://tjwwymongjrdsgoxfbtn.supabase.co"
FUNCTION_URL = f"{SUPABASE_URL}/functions/v1/enrich-news"
ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InRqd3d5bW9uZ2pyZHNnb3hmYnRuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTExOTI4ODksImV4cCI6MjA2Njc2ODg4OX0.op3TuNq3zIi6vaKNXDiGZzVIgpYNOWrpTu7ssCrUx0E"

HEADERS = {
    "apikey": ANON_KEY,
    "Authorization": f"Bearer {ANON_KEY}",
    "Content-Type": "application/json"
}

def run_backfill():
    print("🚀 Starting News Enrichment Backfill...")

    # 1. Fetch all pending news
    # We use the REST API to get rows that are NOT enriched yet
    fetch_url = f"{SUPABASE_URL}/rest/v1/market_news?status=neq.enriched&select=*"
    
    try:
        response = requests.get(fetch_url, headers=HEADERS)
        response.raise_for_status()
        articles = response.json()
    except Exception as e:
        print(f"❌ Error fetching articles: {e}")
        return

    count = len(articles)
    if count == 0:
        print("✅ No pending articles found. All news is already enriched!")
        return

    print(f"Found {count} articles waiting for analysis.")

    # 2. Loop and Process
    for i, article in enumerate(articles):
        print(f"[{i+1}/{count}] Sending: {article.get('title', 'Unknown')}...")
        
        # Prepare the payload exactly how the Edge Function expects it
        payload = {
            "record": article
        }

        try:
            # Call the Edge Function
            func_response = requests.post(FUNCTION_URL, headers=HEADERS, json=payload)
            
            if func_response.status_code == 200:
                print("   ✅ Enriched!")
            else:
                print(f"   ⚠️ Failed: {func_response.text}")

        except Exception as e:
            print(f"   ❌ Network Error: {e}")
            
        # Sleep 2 seconds to be gentle on the Gemini API rate limit
        time.sleep(2)

    print("\n🎉 Backfill Complete! Check your Dashboard.")

if __name__ == "__main__":
    run_backfill()
