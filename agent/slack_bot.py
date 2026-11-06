import os
import time

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from agent import audit
from agent.actions import ALLOWED_ACTIONS, execute
from agent.agent_groq import MODEL, diagnose, parse_action

load_dotenv()

CHANNEL = os.getenv("SLACK_CHANNEL", "incidents")

app = App(token=os.environ["SLACK_BOT_TOKEN"])


def post_incident(alert: str) -> None:
    """Diagnose an alert, log it, and post the result to Slack for human approval."""
    diagnosis = diagnose(alert)
    action = parse_action(diagnosis)

    if action in ALLOWED_ACTIONS:
        status = "pending"
    elif action == "error":
        status = "agent_error"
    else:
        status = "no_action"
    incident_id = audit.record_incident(alert, MODEL, diagnosis, action, status)

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Incident #{incident_id}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Alert:* {alert}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": diagnosis[:2800]}},
    ]

    if status == "pending":
        value = f"{action}:{incident_id}"
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": f"Approve {action}"},
                        "style": "primary",
                        "action_id": "approve_action",
                        "value": value,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Reject"},
                        "style": "danger",
                        "action_id": "reject_action",
                        "value": value,
                    },
                ],
            }
        )
    else:
        if status == "agent_error":
            note = ":warning: The agent could not finish. A human needs to investigate."
        else:
            note = "No action proposed. Nothing was changed."
        blocks.append(
            {"type": "context", "elements": [{"type": "mrkdwn", "text": note}]}
        )

    app.client.chat_postMessage(
        channel=CHANNEL, text=f"Incident #{incident_id}", blocks=blocks
    )


def _replace_buttons(body, status_text: str) -> None:
    """Swap the buttons for a status line so they cannot be clicked twice."""
    message = body["message"]
    blocks = [b for b in message["blocks"] if b["type"] != "actions"]
    blocks.append(
        {"type": "section", "text": {"type": "mrkdwn", "text": status_text}}
    )
    app.client.chat_update(
        channel=body["channel"]["id"],
        ts=message["ts"],
        text="Incident update",
        blocks=blocks,
    )


def _parse_value(body) -> tuple[str, int]:
    action, incident_id = body["actions"][0]["value"].split(":")
    return action, int(incident_id)


@app.action("approve_action")
def on_approve(ack, body):
    ack()
    user = body["user"]["id"]
    action, incident_id = _parse_value(body)
    # Claim the decision first so a double click can never run the action twice.
    if not audit.record_decision(incident_id, "approved", user):
        _replace_buttons(body, ":information_source: This incident was already decided.")
        return
    result = execute(action)  # execute() refuses anything outside the whitelist
    audit.record_decision_result(incident_id, result)
    _replace_buttons(body, f":white_check_mark: Approved by <@{user}>\n`{result}`")


@app.action("reject_action")
def on_reject(ack, body):
    ack()
    user = body["user"]["id"]
    _, incident_id = _parse_value(body)
    if not audit.record_decision(incident_id, "rejected", user):
        _replace_buttons(body, ":information_source: This incident was already decided.")
        return
    _replace_buttons(body, f":no_entry: Rejected by <@{user}>. No changes made.")


if __name__ == "__main__":
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    handler.connect()  # listen for button clicks in the background
    post_incident("ALERT: /checkout is returning HTTP 500 errors.")
    print("Posted to Slack. Waiting for button clicks. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)  # short sleeps let Ctrl+C interrupt on Windows
    except KeyboardInterrupt:
        handler.close()
        print("Stopped.")