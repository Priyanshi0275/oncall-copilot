import json
import os

from dotenv import load_dotenv
from groq import BadRequestError, Groq

from agent.actions import ALLOWED_ACTIONS, execute
from agent.approval import ask_approval
from agent.rag import search_runbooks
from agent.tools import current_time, get_recent_deploys, read_logs

load_dotenv()

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

SYSTEM_PROMPT = """You are an on-call engineer's assistant.
When given an alert, investigate using the tools provided.
Always check the logs and the recent deploys first, then search the runbooks.
Base your suggested fix on the runbook, not on your own guesses.
Call current_time first. Only treat errors from the last 10 minutes as an active incident.
If the recent logs show no errors, report that the service looks healthy and use ACTION: none.
Never propose rollback based on old errors that are followed by a rollback or by successful requests.
Reply in this format:
ROOT CAUSE: one or two sentences.
EVIDENCE: the exact log lines that support it.
RUNBOOK: the name of the runbook you used.
SUGGESTED FIX: the fix from that runbook.
ACTION: exactly one word, either rollback or none.
CONFIDENCE: low, medium or high.
Use ACTION: rollback only when the runbook says to roll back. Otherwise use ACTION: none.
Only use facts from the tools. If no runbook matches, say so, do not guess a fix, and use ACTION: none."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "current_time",
            "description": "Return the current local time. Call this first.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_logs",
            "description": "Return application log lines from the last N minutes. Both arguments are optional.",
            "parameters": {
                "type": "object",
                "properties": {
                    "last_n": {"type": ["integer", "null"]},
                    "minutes": {"type": ["integer", "null"]},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_deploys",
            "description": "Return deploy and rollback events from the log.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_runbooks",
            "description": "Search the team runbooks for the recommended diagnosis and fix for a problem. Pass a short description of the problem.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
]

FUNCTIONS = {
    "current_time": current_time,
    "read_logs": read_logs,
    "get_recent_deploys": get_recent_deploys,
    "search_runbooks": search_runbooks,
}

client = Groq(api_key=os.environ["GROQ_API_KEY"])


def _chat(messages):
    """Call the model, retrying when it produces a malformed tool call."""
    for attempt in range(3):
        try:
            return client.chat.completions.create(
                model=MODEL, messages=messages, tools=TOOLS, tool_choice="auto"
            )
        except BadRequestError:
            if attempt == 2:
                raise


def _run_tool(name: str, raw_arguments: str) -> str:
    """Run one tool call safely and always return a string."""
    func = FUNCTIONS.get(name)
    if func is None:
        return f"Unknown tool: {name}"
    try:
        args = json.loads(raw_arguments or "{}")
        args = {k: v for k, v in args.items() if v is not None}
        return func(**args)
    except Exception as exc:  # report the failure to the model instead of crashing
        return f"Tool {name} failed: {exc}"


def diagnose(alert: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": alert},
    ]
    for _ in range(6):  # safety cap on tool-call rounds
        response = _chat(messages)
        msg = response.choices[0].message
        if not msg.tool_calls:
            return msg.content
        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        )
        for tc in msg.tool_calls:
            result = _run_tool(tc.function.name, tc.function.arguments)
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": result}
            )
    return "Agent stopped: too many tool-call rounds."


def parse_action(text: str) -> str:
    for line in text.splitlines():
        cleaned = line.replace("*", "").strip()
        if cleaned.upper().startswith("ACTION:"):
            return cleaned.split(":", 1)[1].strip().lower()
    return "none"


if __name__ == "__main__":
    diagnosis = diagnose("ALERT: /checkout is returning HTTP 500 errors.")
    print(diagnosis)

    action = parse_action(diagnosis)
    if action not in ALLOWED_ACTIONS:
        print("\nNo action proposed. Nothing was changed.")
    elif ask_approval(action):
        print(execute(action))
    else:
        print("Rejected. No changes made.")