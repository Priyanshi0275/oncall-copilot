from datetime import datetime, timedelta
from pathlib import Path

LOG_FILE = Path("app.log")
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def _lines() -> list[str]:
    if not LOG_FILE.exists():
        return []
    return LOG_FILE.read_text().splitlines()


def _timestamp(line: str):
    try:
        return datetime.strptime(line[:19], TIME_FORMAT)
    except ValueError:
        return None


def current_time() -> str:
    """Return the current local time."""
    return datetime.now().strftime(TIME_FORMAT)


def read_logs(last_n: int = 50, minutes: int = 10) -> str:
    """Return log lines from the last N minutes (at most last_n lines)."""
    cutoff = datetime.now() - timedelta(minutes=minutes)
    recent = [
        line for line in _lines()
        if (ts := _timestamp(line)) is not None and ts >= cutoff
    ]
    if not recent:
        return f"No log lines in the last {minutes} minutes."
    return "\n".join(recent[-last_n:])


def get_recent_deploys() -> str:
    """Return deploy and rollback events from the log, oldest first."""
    events = [
        line for line in _lines()
        if "deployed new version" in line or "rolled back" in line
    ]
    return "\n".join(events[-10:]) if events else "No deploy events found."