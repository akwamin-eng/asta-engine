import os
import requests
import xml.etree.ElementTree as ET
from supabase import create_client, Client
from dateutil import parser

# --- CONFIG ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
GOOGLE_NEWS_URL = "https://news.google.com/rss/search?q=Ghana+Real+Estate+Economy+Infrastructure&hl=en-GH&gl=GH&ceid=GH:en"

def get_sentiment(text):
    text = text.lower()
    score = 0
    if any(w in text for w in ['surge', 'boost', 'growth', 'rise', 'profit']): score += 0.2
    if any(w in text for w in ['crash', 'drop', 'loss', 'delay', 'debt']): score -= 0.2
    return max(min(score, 1.0), -1.0)

def fetch_and_store():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ Error: Supabase credentials missing.")
        return

    print(f"📡 Connecting to Supabase...")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    print(f"📰 Fetching News from Google...")
    try:
        response = requests.get(GOOGLE_NEWS_URL, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"❌ Network Error: {e}")
        return

    try:
        root = ET.fromstring(response.content)
        items = root.findall('./channel/item')
    except Exception as e:
        print(f"❌ XML Parse Error: {e}")
        return

    new_count = 0
    
    for item in items[:15]:
        try:
            title = item.find('title').text
            link = item.find('link').text
            pub_date_str = item.find('pubDate').text
            source = item.find('source').text if item.find('source') is not None else "Google News"
            
            published_at = parser.parse(pub_date_str).isoformat()
            sentiment = get_sentiment(title)
            
            data = {
                "title": title,
                "summary": title,
                "url": link,
                "source": source,
                "published_at": published_at,
                "sentiment_score": sentiment,
                "category": "Real Estate"
            }

            existing = supabase.table('market_news').select('id').eq('url', link).execute()
            
            if not existing.data:
                supabase.table('market_news').insert(data).execute()
                print(f"🔹 Saved: {title[:50]}...")
                new_count += 1
            else:
                print(f"🔸 Skipped: {title[:30]}...")

        except Exception as e:
            continue

    print(f"🚀 Google News Job Complete. {new_count} new stories.")

if __name__ == "__main__":
    fetch_and_store()
