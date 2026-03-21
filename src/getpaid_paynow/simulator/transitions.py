"""PayNow simulator state transitions."""

PAYNOW_TRANSITIONS: dict[str, set[str]] = {
    "NEW": {"PENDING", "ABANDONED"},
    "PENDING": {
        "CONFIRMED",
        "REJECTED",
        "ERROR",
        "EXPIRED",
        "ABANDONED",
    },
    "CONFIRMED": set(),
    "REJECTED": set(),
    "ERROR": set(),
    "EXPIRED": set(),
    "ABANDONED": set(),
}
