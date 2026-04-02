import os
import requests
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("CF_API_TOKEN")
gateway_url = os.getenv("CF_GATEWAY_URL")
model = os.getenv("CF_MODEL", "@cf/meta/llama-3.3-70b-instruct-fp8-fast")

print(f"Testing Cloudflare with Token: {token[:10]}...")
print(f"Gateway URL: {gateway_url}")

# Attempt 1: Gateway + /chat/completions
url1 = f"{gateway_url.rstrip('/')}/chat/completions"
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}
data = {
    "model": model,
    "messages": [{"role": "user", "content": "Hello"}]
}

print("\n--- Attempt 1: Gateway + /chat/completions ---")
try:
    resp = requests.post(url1, headers=headers, json=data)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
except Exception as e:
    print(f"Error: {e}")

# Attempt 2: Gateway + /v1/chat/completions
url2 = f"{gateway_url.rstrip('/')}/v1/chat/completions"
print("\n--- Attempt 2: Gateway + /v1/chat/completions ---")
try:
    resp = requests.post(url2, headers=headers, json=data)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")
except Exception as e:
    print(f"Error: {e}")
