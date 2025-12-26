from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from services import process_text_to_property, save_to_db, supabase
from fastapi.middleware.cors import CORSMiddleware
from collections import Counter

app = FastAPI()

# Enable CORS for Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RawListing(BaseModel):
    text: str

@app.get("/")
def home():
    return {"status": "ASTA ENGINE ONLINE", "version": "1.0.0"}

@app.post("/process")
async def process_listing(listing: RawListing):
    if not listing.text:
        raise HTTPException(status_code=400, detail="Text is required")
    
    # 1. AI Extraction
    property_data = await process_text_to_property(listing.text)
    
    if not property_data:
        raise HTTPException(status_code=500, detail="AI Extraction Failed")
        
    # 2. Database Save
    saved_record = await save_to_db(property_data)
    
    if not saved_record:
        raise HTTPException(status_code=500, detail="Database Save Failed")
        
    return {"message": "Success", "data": saved_record}

# 🆕 MARKET PULSE API (Trending Tags)
@app.get("/api/trends")
async def get_market_trends():
    """
    Analyzes all active listings to find trending 'Vibes' and locations.
    Returns the top 5 most common tags.
    """
    try:
        # Fetch all features from Supabase
        response = supabase.table('properties').select('vibe_features').execute()
        data = response.data
        
        # Flatten the list (convert "Pool, Gym" -> ["Pool", "Gym"])
        all_tags = []
        for item in data:
            if item.get('vibe_features'):
                # Split by comma, strip whitespace, and uppercase
                tags = [t.strip().upper() for t in item['vibe_features'].split(',')]
                all_tags.extend(tags)
        
        # Count frequency
        counts = Counter(all_tags)
        top_tags = [tag for tag, count in counts.most_common(6)]
        
        return {"trending_tags": top_tags}
    except Exception as e:
        print(f"Error calculating trends: {e}")
        return {"trending_tags": []}
