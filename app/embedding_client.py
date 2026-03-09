import requests
import os
import time




EMBEDDING_URL = os.getenv("EMBEDDING_URL")

def get_embedding(text, retries=3):
    payload = {
        "input": text
    }

    headers = {
        "Content-Type": "application/json"
    }

    for attempt in range(retries):
        try:
            response = requests.post(
                EMBEDDING_URL,
                json=payload,
                headers=headers,
                timeout=30
            )

            if response.status_code != 200:
                print("HTTP Error:", response.text)
                continue

            data = response.json()

            # Your proxy format
            if "vectors" in data:
                return data["vectors"][0]

            else:
                print("Unexpected response:", data)

        except Exception as e:
            print(f"Retry {attempt+1} failed:", e)
            time.sleep(1)

    raise Exception("Embedding request failed")

