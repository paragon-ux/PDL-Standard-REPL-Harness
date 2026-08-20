def prompt_artifact(body: str) -> str:
    return f"Prompt Pseudocode\n\n{body}\n\nConfirm or correct this interpretation."


def plan_artifact(body: str) -> str:
    return f"Response Plan Pseudocode\n\n{body}\n\nConfirm or correct this response approach."


def deferred_substantive() -> str:
    return "I’ll address that substantive task question after the current confirmations are complete."


def review_clarification() -> str:
    return "Please clarify how that message should affect the current review."


def cancelled() -> str:
    return "Cancelled."
