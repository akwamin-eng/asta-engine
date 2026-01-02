from fastapi import FastAPI, HTTPException, Request, Form, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import services
import re

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
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# --- MODELS ---
class TextRequest(BaseModel):
    text: str
    user_id: Optional[str] = None  # <--- GENTLE UPDATE: Accepts User ID

class FeedbackRequest(BaseModel):
    property_id: int
    vote_type: str  # 'confirmed', 'sus', 'scam'
    device_id: str  # Unique ID for the user/browser

# --- HELPER: NLP LITE (REGEX PARSER) ---
def parse_intent(text: str):
    """
    Extracts structured search data from natural language.
    """
    text = text.lower()
    intent = {
        "location": None,
        "max_price": None,
        "type": "rent" # Default to rent for now
    }

    known_locations = ["east legon", "cantonments", "osu", "labone", "airport", "oyarifa", "adenta", "dzorwulu", "abelemkpe", "tema"]
    for loc in known_locations:
        if loc in text:
            intent["location"] = loc
            break
    
    # Regex to handle "under 5k", "max 5000", "budget 5,000"
    price_pattern = r'(?:under|max|budget|below|less than|limit)\s*[:]?\s*(\d+(?:,\d{3})*(?:k|000)?)'
    price_match = re.search(price_pattern, text)
    
    if price_match:
        raw_val = price_match.group(1).replace(',', '').replace('k', '000')
        try:
            intent["max_price"] = int(raw_val)
        except:
            pass 
    
    if any(x in text for x in ["buy", "sale", "purchase"]):
        intent["type"] = "sale"

    print(f"🧠 PARSED INTENT: {intent}")
    return intent

# --- ENDPOINTS ---

@app.get("/")
def home():
    return {"status": "ASTA Engine Secure & Online"}

@app.get("/api/trends")
def get_trends():
    """
    Returns trending location tags for the frontend dashboard.
    """
    return {
        "trending_tags": ["East Legon", "Cantonments", "Osu", "Airport Residential", "Oyarifa", "Spintex"]
    }

@app.post("/process")
async def process_listing(request: TextRequest):
    """
    Ingests raw text, uses AI to extract data, and attempts to save to DB.
    Handles 'Ghost Listing' rejection gracefully.
    """
    if not request.text:
        raise HTTPException(status_code=400, detail="No text provided")
    
    # 1. AI Extraction
    try:
        data = await services.process_text_to_property(request.text)
    except Exception as e:
        print(f"❌ AI Extraction Error: {e}")
        raise HTTPException(status_code=500, detail="AI Service Interrupted")

    if not data:
        raise HTTPException(status_code=422, detail="AI could not extract valid property data")

    # 2. Attach Owner ID (The Critical Link)
    if request.user_id:
        print(f"👤 Linking Asset to Owner ID: {request.user_id}")
        data['owner_id'] = request.user_id

    # 3. Database Save (Protected by "The Shield" Constraints)
    try:
        saved_record = await services.save_to_db(data)
        return {"message": "Success", "data": saved_record}
    except Exception as e:
        # If the DB rejects it (missing lat/long, no title, etc.)
        error_msg = str(e)
        print(f"🛡️ DB REJECTED LISTING: {error_msg}")
        
        if "check_active_requirements" in error_msg:
            raise HTTPException(
                status_code=422, 
                detail="Listing Rejected: Missing critical data (Location, Price, or Title)."
            )
        
        raise HTTPException(status_code=500, detail=f"Database Error: {error_msg}")

@app.post("/api/feedback")
async def submit_feedback(feedback: FeedbackRequest):
    column_map = {
        "confirmed": "votes_good",
        "sus": "votes_bad", 
        "scam": "votes_scam"
    }
    
    target_column = column_map.get(feedback.vote_type)
    if not target_column:
        raise HTTPException(status_code=400, detail="Invalid vote type")

    try:
        # Check for duplicate vote from this device
        existing_vote = services.supabase.table('trust_votes')\
            .select('*')\
            .eq('property_id', feedback.property_id)\
            .eq('device_id', feedback.device_id)\
            .execute()
            
        if existing_vote.data and len(existing_vote.data) > 0:
            return {"message": "Vote already recorded", "status": "duplicate"}

        # Record the vote
        vote_payload = {
            "property_id": feedback.property_id,
            "device_id": feedback.device_id,
            "vote_type": feedback.vote_type
        }
        services.supabase.table('trust_votes').insert(vote_payload).execute()

        # Update the property counter
        response = services.supabase.table('properties')\
            .select(target_column)\
            .eq('id', feedback.property_id)\
            .execute()
        
        if not response.data:
             raise HTTPException(status_code=404, detail="Property not found")

        current_count = response.data[0].get(target_column, 0) or 0
        
        services.supabase.table('properties')\
            .update({target_column: current_count + 1})\
            .eq('id', feedback.property_id)\
            .execute()
            
        return {"message": "Vote recorded", "new_count": current_count + 1}
        
    except Exception as e:
        print(f"Vote Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/whatsapp")
async def whatsapp_webhook(Body: str = Form(...), From: str = Form(...)):
    incoming_msg = Body.strip()
    intent = parse_intent(incoming_msg)
    response_text = ""

    if intent["location"]:
        try:
            # Query the database
            query = services.supabase.table('properties')\
                .select('title, price, currency, location_name')\
                .ilike('location_name', f'%{intent["location"]}%')\
                .eq('status', 'active') # Only active, verified listings
            
            if intent["max_price"]:
                query = query.lte('price', intent["max_price"])

            results = query.limit(3).execute()
            listings = results.data
            
            if listings:
                loc_title = intent["location"].title()
                price_msg = f" under ₵{intent['max_price']:,}" if intent["max_price"] else ""
                
                response_text = f"🔎 *Found {len(listings)} listings in {loc_title}{price_msg}:*\n\n"
                for item in listings:
                    currency = item.get('currency', 'GHS')
                    price = f"{currency} {item['price']:,}"
                    response_text += f"🏡 *{item['title']}*\n💰 {price}\n📍 {item['location_name']}\n\n"
                response_text += "Reply *'More'* to see others."
            else:
                price_msg = f" under ₵{intent['max_price']:,}" if intent["max_price"] else ""
                response_text = f"🚫 I found listings in *{intent['location'].title()}*, but none matched your budget of{price_msg}. \n\nTry increasing your budget?"
                
        except Exception as e:
            print(f"DB Error: {e}")
            response_text = "⚠️ My database is syncing. Please try again in a moment."
            
    elif "help" in incoming_msg.lower():
        response_text = "👋 *Asta Scout Commands:*\n\nTry sending details like:\n• _'East Legon under 5000'_\n• _'Buy in Cantonments max 500k'_\n• _'Rent in Osu'_"
    
    else:
        response_text = "I'm listening. Try saying something like *'East Legon under 4000'*."

    twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Message>{response_text}</Message>
    </Response>"""
    
    return Response(content=twiml_response, media_type="application/xml")
