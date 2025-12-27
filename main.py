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

class FeedbackRequest(BaseModel):
    property_id: int
    vote_type: str  # 'confirmed', 'sus', 'scam'
    device_id: str  # Unique ID for the user/browser

# --- HELPER: NLP LITE (REGEX PARSER) ---
def parse_intent(text: str):
    """
    Extracts structured search data from natural language.
    Example: "Looking for 2 bed in East Legon under 5000"
    Returns: {'location': 'East Legon', 'max_price': 5000, 'type': 'rent'}
    """
    text = text.lower()
    intent = {
        "location": None,
        "max_price": None,
        "type": "rent" # Default to rent for now
    }

    # 1. Detect Location (from Atlas/Knowledge Base)
    known_locations = ["east legon", "cantonments", "osu", "labone", "airport", "oyarifa", "adenta", "dzorwulu", "abelemkpe", "tema"]
    for loc in known_locations:
        if loc in text:
            intent["location"] = loc
            break
    
    # 2. Detect Price (Robust)
    # Matches: "under 5000", "max 5k", "budget 5,000", "less than 2000"
    # The regex allows for whitespace (\s*) and optional commas in numbers
    price_pattern = r'(?:under|max|budget|below|less than|limit)\s*[:]?\s*(\d+(?:,\d{3})*(?:k|000)?)'
    price_match = re.search(price_pattern, text)
    
    if price_match:
        # Clean the string: remove commas, replace 'k' with '000'
        raw_val = price_match.group(1).replace(',', '').replace('k', '000')
        try:
            intent["max_price"] = int(raw_val)
        except:
            pass # Keep as None if parsing fails
    
    # 3. Detect Sale vs Rent
    if any(x in text for x in ["buy", "sale", "purchase"]):
        intent["type"] = "sale"

    print(f"🧠 PARSED INTENT: {intent}") # DEBUG LOG
    return intent

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

@app.post("/api/feedback")
async def submit_feedback(feedback: FeedbackRequest):
    """
    1. Records the specific vote in 'trust_votes' (The Ballot)
    2. Updates the aggregate count in 'properties' (The Scoreboard)
    """
    
    # Map frontend vote types to DB columns
    column_map = {
        "confirmed": "votes_good", # 'Good' on frontend -> 'votes_good' in DB
        "sus": "votes_bad",        # 'Sus' on frontend -> 'votes_bad' in DB
        "scam": "votes_scam"       # 'Scam' on frontend -> 'votes_scam' in DB
    }
    
    target_column = column_map.get(feedback.vote_type)
    if not target_column:
        raise HTTPException(status_code=400, detail="Invalid vote type")

    try:
        # STEP 1: Check if this device already voted on this property
        # (Prevents ballot stuffing)
        existing_vote = services.supabase.table('trust_votes')\
            .select('*')\
            .eq('property_id', feedback.property_id)\
            .eq('device_id', feedback.device_id)\
            .execute()
            
        if existing_vote.data and len(existing_vote.data) > 0:
            # OPTIONAL: Allow vote changing? For now, we block duplicates.
            return {"message": "Vote already recorded", "status": "duplicate"}

        # STEP 2: Insert the Ballot (trust_votes)
        vote_payload = {
            "property_id": feedback.property_id,
            "device_id": feedback.device_id,
            "vote_type": feedback.vote_type
        }
        services.supabase.table('trust_votes').insert(vote_payload).execute()

        # STEP 3: Update the Scoreboard (properties)
        # Get current count first
        response = services.supabase.table('properties')\
            .select(target_column)\
            .eq('id', feedback.property_id)\
            .execute()
        
        if not response.data:
             raise HTTPException(status_code=404, detail="Property not found")

        current_count = response.data[0].get(target_column, 0) or 0
        
        # Increment
        services.supabase.table('properties')\
            .update({target_column: current_count + 1})\
            .eq('id', feedback.property_id)\
            .execute()
            
        return {"message": "Vote recorded", "new_count": current_count + 1}
        
    except Exception as e:
        print(f"Vote Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- WHATSAPP BRIDGE (INTELLIGENT) ---
@app.post("/api/whatsapp")
async def whatsapp_webhook(Body: str = Form(...), From: str = Form(...)):
    """
    The Asta Concierge V2:
    Now supports price filtering and robust location detection via parse_intent.
    """
    incoming_msg = Body.strip()
    intent = parse_intent(incoming_msg)
    response_text = ""

    if intent["location"]:
        # We have a target. Let's query Supabase.
        try:
            # Base Query
            query = services.supabase.table('properties')\
                .select('title, price, currency, location_name')\
                .ilike('location_name', f'%{intent["location"]}%')\
                .eq('status', 'active')
            
            # Apply Price Filter if detected
            if intent["max_price"]:
                query = query.lte('price', intent["max_price"]) # lte = Less Than or Equal

            # Execute
            results = query.limit(3).execute()
            listings = results.data
            
            if listings:
                loc_title = intent["location"].title()
                price_msg = f" under ₵{intent['max_price']:,}" if intent["max_price"] else ""
                
                response_text = f"🔎 *Found {len(listings)} listings in {loc_title}{price_msg}:*\n\n"
                for item in listings:
                    price = f"{item['currency']} {item['price']:,}"
                    response_text += f"🏡 *{item['title']}*\n💰 {price}\n📍 {item['location_name']}\n\n"
                
                response_text += "Reply *'More'* to see others or try a different budget."
            else:
                # Intelligent Fallback
                price_msg = f" under ₵{intent['max_price']:,}" if intent["max_price"] else ""
                response_text = f"🚫 I found listings in *{intent['location'].title()}*, but none matched your budget of{price_msg}. \n\nTry increasing your budget?"
                
        except Exception as e:
            print(f"DB Error: {e}")
            response_text = "⚠️ My database is syncing. Please try again in a moment."
            
    elif "help" in incoming_msg.lower():
        response_text = "👋 *Asta Scout Commands:*\n\nTry sending details like:\n• _'East Legon under 5000'_\n• _'Buy in Cantonments max 500k'_\n• _'Rent in Osu'_"
    
    else:
        # Default fallback
        response_text = "I'm listening. Try saying something like *'East Legon under 4000'*."

    # Format Response (TwiML)
    twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Message>{response_text}</Message>
    </Response>"""
    
    return Response(content=twiml_response, media_type="application/xml")
