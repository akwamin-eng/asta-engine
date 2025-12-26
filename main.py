from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import services

app = FastAPI()

# 🔒 STRICT SECURITY SETTINGS
# Only allow requests from these specific origins
origins = [
    "http://localhost:5173",      # Vite Local Dev
    "http://127.0.0.1:5173",      # Vite Local Dev (Alternative IP)
    "https://asta.homes",         # ✅ Your Production Domain
    "https://www.asta.homes",     # ✅ WWW Version
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,        # Enforce the list above
    allow_credentials=True,
    allow_methods=["GET", "POST"], # Only allow reading/writing data
    allow_headers=["*"],
)

# --- REQUEST MODELS ---
class TextRequest(BaseModel):
    text: str

# --- ENDPOINTS ---

@app.get("/")
def home():
    return {"status": "ASTA Engine Secure & Online"}

@app.post("/process")
async def process_listing(request: TextRequest):
    """
    1. AI extracts data from text.
    2. Saves structured data to Supabase.
    """
    if not request.text:
        raise HTTPException(status_code=400, detail="No text provided")
    
    # 1. AI Extraction
    data = await services.process_text_to_property(request.text)
    
    if not data:
        raise HTTPException(status_code=500, detail="AI Extraction Failed")

    # 2. Save to DB
    saved_record = await services.save_to_db(data)
    
    return {"message": "Success", "data": saved_record}

@app.get("/api/trends")
async def get_trends():
    """
    Analyzes all listings to find trending tags.
    """
    try:
        response = services.supabase.table('properties').select("vibe_features").execute()
        
        # Flatten list of tags: "Pool, Gym" -> ["Pool", "Gym"]
        all_tags = []
        for row in response.data:
            if row['vibe_features']:
                # Clean up the string format
                clean_row = row['vibe_features'].replace('"', '').replace('[', '').replace(']', '')
                tags = [t.strip() for t in clean_row.split(',')]
                all_tags.extend(tags)

        # Count frequency
        from collections import Counter
        counts = Counter(all_tags)
        
        # Return top 5 most common
        top_tags = [tag for tag, count in counts.most_common(5) if tag]
        
        return {"trending_tags": top_tags}
    except Exception as e:
        print(f"Trend Error: {e}")
        return {"trending_tags": []}
