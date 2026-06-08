
import json
import requests

payload = {
    "message": (
        "I am 178cm, 82kg, intermediate, surfing 2 to 4 foot beach breaks around Torquay. "
        "I want more paddle power but still want to turn. "
        "I ride a 6 foot shortboard but it feels hard to catch waves on."
    ),
    "region": "Australia",
    "page_context": "quivrr.surf landing page",
    "conversation": [],
}

response = requests.post(
    "http://127.0.0.1:8090/api/board-guide/chat",
    headers={"Content-Type": "application/json"},
    data=json.dumps(payload),
    timeout=60,
)

response.raise_for_status()
print(json.dumps(response.json(), indent=2))
