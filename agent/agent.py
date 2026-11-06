import os

from google import genai
from google.genai import types

from agent.tools import get_recent_deploys, read_logs

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

SYSTEM_PROMPT = """You are an on-call engineer's assistant.
When given an alert, investigate using the tools provided.
Always check the logs and the recent deploys before answering.
Reply in this format:
ROOT CAUSE: one or two sentences.
EVIDENCE: the exact log lines that support it.
SUGGESTED FIX: one concrete action.
CONFIDENCE: low, medium or high.
Only use facts from the tools. If the evidence is unclear, say so."""

client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"],
    http_options=types.HttpOptions(
        retry_options=types.HttpRetryOptions(attempts=5)
    ),
)


def diagnose(alert: str) -> str:
    response = client.models.generate_content(
        model=MODEL,
        contents=alert,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[read_logs, get_recent_deploys],
        ),
    )
    return response.text


if __name__ == "__main__":
    print(diagnose("ALERT: /checkout is returning HTTP 500 errors."))