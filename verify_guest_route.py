import requests
import json

url = "http://127.0.0.1:8002/chat/guest"
data = {
    "query": "in jaipur",
    "conversation_id": "test-guest-final-v1",
    "session_id": "sess-guest-final-v1"
}

try:
    print(f"Pinging {url}...")
    resp = requests.post(url, json=data, timeout=60)
    print(f"Status: {resp.status_code}")
    print(f"Reply: {resp.json().get('reply', '')[:200]}...")
except Exception as e:
    print(f"Error: {e}")
