import requests

URL = "http://127.0.0.1:8000/api/whatsapp"

# TEST 2: Complex Query with Budget
payload = {
    "Body": "I need a place in East Legon under 5000", 
    "From": "whatsapp:+233555555555"
}

print(f"📡 Sending Message: '{payload['Body']}'...")

try:
    response = requests.post(URL, data=payload)
    if response.status_code == 200:
        print("\n✅ SUCCESS: Asta replied!")
        print("-" * 40)
        print(response.text)
        print("-" * 40)
    else:
        print(f"\n❌ ERROR: {response.status_code}")
except Exception as e:
    print(f"\n❌ FAILED: {e}")
