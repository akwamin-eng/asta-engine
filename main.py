from fastapi import FastAPI, Form, HTTPException
from pydantic import BaseModel
from services import process_text_to_property, save_to_db

app = FastAPI()

# 1. JSON Schema (For your manual testing)
class MessageInput(BaseModel):
    text: str

@app.get("/")
async def root():
    return {"status": "Asta Engine Online", "brain": "Gemini Resilient"}

# 2. The JSON Endpoint (Keep this for testing)
@app.post("/process")
async def process_manual(input: MessageInput):
    extracted_data = await process_text_to_property(input.text)
    if not extracted_data:
        raise HTTPException(status_code=500, detail="AI Extraction Failed")
    saved_record = await save_to_db(extracted_data)
    if not saved_record:
        raise HTTPException(status_code=500, detail="Database Save Failed")
    return {"status": "success", "data": saved_record}

# 3. 🆕 The WhatsApp Endpoint (Twilio Webhook)
@app.post("/whatsapp")
async def process_whatsapp(Body: str = Form(...), From: str = Form(...)):
    """
    Twilio sends data as Form fields. 
    'Body' is the message text.
    'From' is the sender's phone number.
    """
    print(f"📩 WhatsApp from {From}: {Body}")
    
    # Process exactly like before
    extracted_data = await process_text_to_property(Body)
    
    if extracted_data:
        await save_to_db(extracted_data)
        return {"status": "Message received and processed"}
    else:
        return {"status": "Could not extract property data"}
