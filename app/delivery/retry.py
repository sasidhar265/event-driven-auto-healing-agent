"""Webhook retry timing policy."""


def retry_delay(attempts: int, base_seconds: float, maximum_seconds: int) -> float:
    """Return a capped exponential delay for the completed attempt count."""
    return min(base_seconds ** attempts, maximum_seconds)
