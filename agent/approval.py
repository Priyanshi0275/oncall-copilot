def ask_approval(action: str) -> bool:
    """Block until a human approves or rejects the proposed action."""
    answer = input(f"\nProposed action: {action}. Approve? [y/N] ")
    return answer.strip().lower() == "y"