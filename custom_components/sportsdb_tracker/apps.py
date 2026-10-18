"""Opening a channel's app on an Android TV box, without Home Assistant: which shell commands open an app, and whether
the box's reply says it opened. Used by launch.py through the Android Debug Bridge (androidtv.adb_command).

An app is an Android package name (no.tv2.sumo) or a deep link (https://..., nrktv://...). Both are checked strictly:
they end up on the box's command line."""
from __future__ import annotations

import re

PACKAGE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")
LINK = re.compile(r"^[a-z][a-z0-9+.-]*://[^\s'\"`;|&$<>\\(){}]+$")
WAKE = "input keyevent KEYCODE_WAKEUP"


def valid_app(app: str) -> bool:
    return bool(PACKAGE.match(app or "") or LINK.match(app or ""))


def open_commands(app: str, package: str | None = None) -> list[str]:
    """The commands to try in turn: a package through the TV launcher's entry, then the phone launcher's (an app that
    only has the latter still opens); a link as a view intent, pinned to `package` when given (a YouTube link would
    otherwise ask which app to use, YouTube or the TV browser)."""
    if PACKAGE.match(app or ""):
        return [f"monkey -p {app} -c android.intent.category.LEANBACK_LAUNCHER 1",
                f"monkey -p {app} -c android.intent.category.LAUNCHER 1"]
    if LINK.match(app or ""):
        pin = f" -p {package}" if package and PACKAGE.match(package) else ""
        return [f"am start -a android.intent.action.VIEW -d '{app}'{pin}"]
    raise ValueError(f"not a package name or link: {app!r}")


def opened(reply: str | None) -> bool:
    """The box's reply to one of open_commands says the app came up."""
    text = reply or ""
    if "No activities found" in text or "Error" in text or "aborted" in text:
        return False
    return "Events injected: 1" in text or "Starting: Intent" in text


def not_installed(reply: str | None) -> bool:
    return "No activities found" in (reply or "")
