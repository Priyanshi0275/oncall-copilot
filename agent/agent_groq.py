import json
import os
import time

from dotenv import load_dotenv
from groq import APIStatusError, BadRequestError, Groq, RateLimitError

from agent.actions import ALLOWED_ACTIONS, execute
from agent.approval import ask_approval
from agent.rag import search_runbooks
from agent.tools import current_time, get_recent_deploys, read_logs

load_dotenv()

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
MAX_ROUNDS = 10
MAX_TOOL_CHARS = 3000  # cap every tool result so one big log cannot blow the token budget
FAILED_PREFIX = "AGENT_FAILED"

SYSTEM_PROMPT = """You are an on-call engineer's assistant.
When given an alert, investigate using the tools provided.
Call current_time, read_logs and get_recent_deploys together in your first step, then search the runbooks.
Base your suggested fix on the runbook, not on your own guesses.
Only treat errors from the last 10 minutes as an active incident.
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
            "description": "Return the current local time.",
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


def _approx_tokens(messages) -> int:
    return len(json.dumps(messages)) // 4


def _chat(messages):
    """Call the model, retrying on malformed output and rate limits."""
    last_error = None
    for attempt in range(4):
        try:
            return client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=2000,
                extra_body={"reasoning_effort": "low"},
            )
        except RateLimitError as exc:
            last_error = exc
            print(f"    rate limited, waiting 15s: {exc}")
            time.sleep(15)
        except BadRequestError as exc:
            last_error = exc
            if attempt == 3:
                raise
        except APIStatusError as exc:
            if exc.status_code == 413:
                print(f"    request too large, about {_approx_tokens(messages)} tokens by my estimate")
            raise
    raise RuntimeError(f"Model call failed after retries: {last_error}")


def _run_tool(name: str, raw_arguments: str) -> str:
    """Run one tool call safely and always return a string."""
    func = FUNCTIONS.get(name)
    if func is None:
        return f"Unknown tool: {name}"
    try:
        args = json.loads(raw_arguments or "{}")
        args = {k: v for k, v in args.items() if v is not None}
        return str(func(**args))[:MAX_TOOL_CHARS]
    # Report the failure to the model instead of crashing the agent.
    except Exception as exc:  # noqa: BLE001
        return f"Tool {name} failed: {exc}"


def diagnose(alert: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": alert},
    ]
    for _ in range(MAX_ROUNDS):
        response = _chat(messages)
        msg = response.choices[0].message
        if not msg.tool_calls:
            return msg.content or f"{FAILED_PREFIX}: the model returned an empty answer."
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
    return f"{FAILED_PREFIX}: too many tool-call rounds, no diagnosis produced."


def parse_action(text: str) -> str:
    """Return rollback, none, or error when the agent itself failed."""
    if text.startswith(FAILED_PREFIX):
        return "error"
    for line in text.splitlines():
        cleaned = line.replace("*", "").strip()
        if cleaned.upper().startswith("ACTION:"):
            return cleaned.split(":", 1)[1].strip().lower()
    return "error"  # no ACTION line means the answer is malformed


if __name__ == "__main__":
    diagnosis = diagnose("ALERT: /checkout is returning HTTP 500 errors.")
    print(diagnosis)

    action = parse_action(diagnosis)
    if action == "error":
        print("\nAgent could not finish the diagnosis. Human investigation needed.")
    elif action not in ALLOWED_ACTIONS:
        print("\nNo action proposed. Nothing was changed.")
    elif ask_approval(action):
        print(execute(action))
    else:
        print("Rejected. No changes made.")