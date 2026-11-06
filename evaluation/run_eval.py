import argparse
import json
import time
from pathlib import Path

import requests

from agent.agent_groq import diagnose, parse_action

BASE_URL = "http://localhost:8000"
LOG_FILE = Path("app.log")
RESULTS_FILE = Path("evaluation/results.json")
KNOWN_RUNBOOKS = ["bad_deploy", "db_pool_exhausted", "memory_leak", "high_latency"]

CASES = [
    {
        "name": "bad_deploy",
        "setup": "/break",
        "alert": "ALERT: /checkout is returning HTTP 500 errors.",
        "expected_action": "rollback",
        "expected_runbooks": {"db_pool_exhausted", "bad_deploy"},
    },
    {
        "name": "memory_leak",
        "setup": "/break/memory",
        "alert": "ALERT: the service keeps restarting and /checkout is returning errors.",
        "expected_action": "none",
        "expected_runbooks": {"memory_leak"},
    },
    {
        "name": "high_latency",
        "setup": "/break/latency",
        "alert": "ALERT: /checkout response time is far above normal.",
        "expected_action": "none",
        "expected_runbooks": {"high_latency"},
    },
    {
        "name": "healthy_false_alarm",
        "setup": None,
        "alert": "ALERT: a user reported that /checkout might be failing.",
        "expected_action": "none",
        "expected_runbooks": set(),
    },
]


def prepare(case: dict) -> None:
    """Put the sample app into the case's state with a clean log file."""
    requests.post(f"{BASE_URL}/fix", timeout=10)
    LOG_FILE.write_text("")
    if case["setup"]:
        requests.post(BASE_URL + case["setup"], timeout=10)
    for _ in range(3):
        requests.get(f"{BASE_URL}/checkout", timeout=10)
    time.sleep(1)


def run_diagnosis(alert: str):
    """Call the agent, retrying on rate limits or other API errors."""
    for attempt in range(3):
        try:
            return diagnose(alert)
        except Exception as exc:  # noqa: BLE001
            print(f"    API error: {exc}")
            time.sleep(10 * (attempt + 1))
    return None


def cited_runbooks(text: str) -> set:
    for line in text.splitlines():
        cleaned = line.replace("*", "").strip()
        if cleaned.upper().startswith("RUNBOOK:"):
            value = cleaned.split(":", 1)[1].lower()
            return {name for name in KNOWN_RUNBOOKS if name in value}
    return set()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()

    rows = []
    raw = []
    for case in CASES:
        action_ok = runbook_ok = wrong_rollbacks = errors = 0
        seconds = []
        for i in range(args.runs):
            prepare(case)
            start = time.time()
            text = run_diagnosis(case["alert"])
            elapsed = time.time() - start
            if text is None:
                errors += 1
                print(f"  {case['name']} run {i + 1}: ERROR")
                continue
            seconds.append(elapsed)
            action = parse_action(text)
            if action == "error":
                errors += 1
                print(f"  {case['name']} run {i + 1}: AGENT ERROR")
                continue
            runbooks = cited_runbooks(text)
            good_action = action == case["expected_action"]
            if case["expected_runbooks"]:
                good_runbook = bool(runbooks & case["expected_runbooks"])
            else:
                good_runbook = not runbooks
            action_ok += good_action
            runbook_ok += good_runbook
            if action == "rollback" and case["expected_action"] != "rollback":
                wrong_rollbacks += 1
            raw.append({"case": case["name"], "run": i + 1, "action": action,
                        "runbooks": sorted(runbooks), "seconds": round(elapsed, 1),
                        "diagnosis": text})
            print(f"  {case['name']} run {i + 1}: action={action} "
                  f"runbooks={sorted(runbooks)} ({elapsed:.1f}s)")
            time.sleep(20)  # stay under the free tier rate limit
        rows.append((case["name"], args.runs, action_ok, runbook_ok,
                     wrong_rollbacks, errors,
                     sum(seconds) / len(seconds) if seconds else 0.0))

    requests.post(f"{BASE_URL}/fix", timeout=10)

    print("\n{:<22}{:>6}{:>10}{:>10}{:>16}{:>8}{:>9}".format(
        "case", "runs", "action", "runbook", "wrong rollback", "errors", "avg sec"))
    for name, runs, a, r, w, e, s in rows:
        print("{:<22}{:>6}{:>10}{:>10}{:>16}{:>8}{:>9.1f}".format(
            name, runs, f"{a}/{runs}", f"{r}/{runs}", w, e, s))

    total = sum(r[1] for r in rows)
    correct = sum(r[2] for r in rows)
    wrong = sum(r[4] for r in rows)
    print(f"\nOverall action accuracy: {correct}/{total} ({100 * correct / total:.0f}%)")
    print(f"Wrong rollbacks proposed: {wrong}")

    RESULTS_FILE.write_text(json.dumps(raw, indent=2))
    print(f"Raw results saved to {RESULTS_FILE}")


if __name__ == "__main__":
    main()