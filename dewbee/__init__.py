"""Dewbee library."""

import json
import os


__version__ = "0.1.2"


def _development_state_file():
    appdata = os.getenv("APPDATA")
    if not appdata:
        return None
    return os.path.join(
        appdata,
        "ladybug_tools",
        "dewbee",
        "dev_mode",
        "active.json",
    )


def is_dev_mode():
    """Return True when DB Development Mode has an active state marker."""
    state_file = _development_state_file()
    if not state_file or not os.path.isfile(state_file):
        return False

    try:
        with open(state_file, "r") as stream:
            state = json.load(stream)
        return state.get("active") is True and bool(state.get("repo"))
    except Exception:
        return False


def component_message():
    """Return the message displayed by Dewbee Grasshopper components."""
    return "DEV" if is_dev_mode() else __version__
