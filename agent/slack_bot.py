import os
import time

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from agent.actions import ALLOWED_ACTIONS, execute
from agent.agent_groq import diagnose, parse_action

load_dotenv()

CHANNEL = os.getenv("SLACK_CHANNEL", "incidents")

app = App(token=os.environ["SLACK_BOT_TOKEN"])


def post_incident(alert: str) -> None:
    """Diagnose an alert and post the result to Slack for human approval."""
    diagnosis = diagnose(alert)
    action = parse_action(diagnosis)
    text = diagnosis[:2800]

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "Incident detected"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Alert:* {alert}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
    ]

    if action in ALLOWED_ACTIONS:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": f"Approve {action}"},
                        "style": "primary",
                        "action_id": "approve_action",
                        "value": action,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Reject"},
                        "style": "danger",
                        "action_id": "reject_action",
                        "value": action,
                    },
                ],
            }
        )
    else:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": "No action proposed. Nothing was changed."}
                ],
            }
        )

    app.client.chat_postMessage(channel=CHANNEL, text="Incident detected", blocks=blocks)


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


@app.action("approve_action")
def on_approve(ack, body):
    ack()
    user = body["user"]["id"]
    action = body["actions"][0]["value"]
    result = execute(action)  # execute() refuses anything outside the whitelist
    _replace_buttons(body, f":white_check_mark: Approved by <@{user}>\n`{result}`")


@app.action("reject_action")
def on_reject(ack, body):
    ack()
    user = body["user"]["id"]
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