import json
import urllib.request as r
with open("tokens.txt") as f:
    token = f.read().split("PARTNER:")[1].split("\n")[0].strip()

req = r.Request('http://127.0.0.1:8001/partner', data=b'{"query": "show my bookings", "session_id": "test6", "conversation_id": "testconv6"}', headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
try:
    resp = r.urlopen(req)
    print(resp.read().decode('utf-8'))
except Exception as e:
    print(e)
