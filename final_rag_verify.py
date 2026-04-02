import requests
import json

queries = ['in jaipur', 'in bangalore']

for query in queries:
    data = {
        'query': query,
        'conversation_id': 'final-verify-v5',
        'session_id': 'sess-v5'
    }
    try:
        resp = requests.post('http://127.0.0.1:8000/chat', json=data, timeout=60)
        print(f"QUERY: {query}")
        print(f"STATUS: {resp.status_code}")
        reply = resp.json().get('reply', '')
        print(f"REPLY: {reply[:150]}...")
        print("-" * 20)
    except Exception as e:
        print(f"ERROR for {query}: {e}")
