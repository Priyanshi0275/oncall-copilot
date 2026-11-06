import os

import requests

BASE_URL = os.getenv("TARGET_APP_URL", "http://localhost:8000")

# The only actions the agent can ever trigger. Anything else is refused.
ALLOWED_ACTIONS = {
    "rollback": ("POST", "/fix"),
}


def execute(action: str) -> str:
    if action not in ALLOWED_ACTIONS:
        return f"Refused: '{action}' is not an allowed action."
    method, path = ALLOWED_ACTIONS[action]
    response = requests.request(method, BASE_URL + path, timeout=10)
    return f"{action} executed: HTTP {response.status_code} {response.text}"