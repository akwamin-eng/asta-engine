from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import services

app = FastAPI()

# 🔒 STRICT SECURITY SETTINGS
origins = [
    "http://localhost:5173",      # Vite Local Dev
    "http://127.0.0.1:5173",      # Vite Local Dev (Alternative IP)
    "https://asta.homes",         # Production
    "https://www.asta.homes",     # WWW
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# --- MODELS ---
class TextRequest(BaseModel):
    text: str

class FeedbackRequest(BaseModel):
    property_id: int
    vote_type: str  # 'good', 'bad', 'scam'

# --- ENDPOINTS ---

@app.get("/")
def home():
    return {"status": "ASTA Engine Secure & Online"}

@app.post("/process")
async def process_listing(request: TextRequest):
    if not request.text:
        raise HTTPException(status_code=400, detail="No text provided")
    
    data = await services.process_text_to_property(request.text)
    
    if not data:
        raise HTTPException(status_code=500, detail="AI Extraction Failed")

    saved_record = await services.save_to_db(data)
    
    return {"message": "Success", "data": saved_record}

@app.get("/api/trends")
async def get_trends():
    try:
        response = services.supabase.table('properties').select("vibe_features").execute()
        all_tags = []
        for row in response.data:
            if row['vibe_features']:
                # Clean up format ["TAG", "TAG"] -> TAG, TAG
                clean_row = row['vibe_features'].replace('"', '').replace('[', '').replace(']', '')
                tags = [t.strip() for t in clean_row.split(',')]
                all_tags.extend(tags)

        from collections import Counter
        counts = Counter(all_tags)
        top_tags = [tag for tag, count in counts.most_common(5) if tag]
        
        return {"trending_tags": top_tags}
    except Exception as e:
        print(f"Trend Error: {e}")
        return {"trending_tags": []}

# 🆕 FEEDBACK ENDPOINT
@app.post("/api/feedback")
async def submit_feedback(feedback: FeedbackRequest):
    """
    Receives community signals (Good/Bad/Scam).
    Updates the specific counter in Supabase.
    """
    column_map = {
        "good": "votes_good",
        "bad": "votes_bad",
        "scam": "votes_scam"
    }
    
    target_column = column_map.get(feedback.vote_type)
    
    if not target_column:
        raise HTTPException(status_code=400, detail="Invalid vote type")

    try:
        # 1. Get current count
        response = services.supabase.table('properties')\
            .select(target_column)\
            .eq('id', feedback.property_id)\
            .execute()
        
        if not response.data:
             raise HTTPException(status_code=404, detail="Property not found")

        current_count = response.data[0].get(target_column, 0) or 0
        
        # 2. Increment
        services.supabase.table('properties')\
            .update({target_column: current_count + 1})\
            .eq('id', feedback.property_id)\
            .execute()
            
        return {"message": "Vote recorded", "new_count": current_count + 1}
        
    except Exception as e:
        print(f"Vote Error: {e}")
        raise HTTPException(status_code=500, detail="Database Error")
