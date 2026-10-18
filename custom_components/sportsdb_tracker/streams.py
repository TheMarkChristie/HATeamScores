"""Club streams that carry games TheSportsDB does not have: their own schedules read as games of the day for On TV today.
Pure functions, no Home Assistant (today.py reads the feeds), tested in tests/test_streams.py.

Glasgow Clan's Clan TV (on Premier Sports' platform) streams the club's games, the Challenge Cup ones included, which
TheSportsDB does not list (Mark, 18 Oct 2026: "Glasgow still need to appear in the sports list if they are away from home
(fife tonight)"; that night's Challenge Cup game against Fife was on Clan TV and nowhere in TheSportsDB). The stream's
now-next-later feed lists its coming games with UTC times; each becomes a game in TheSportsDB's shape, with the stream's
own end time, and is left out when TheSportsDB already has the same match that day.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable

TITLE = re.compile(r"^\s*(.+?)\s+(?:v|vs)\.?\s+(.+?)\s*$", re.I)


def _utc(text: Any) -> datetime | None:
    try:
        when = datetime.fromisoformat(str(text).strip().replace(" ", "T"))
    except (TypeError, ValueError):
        return None
    return (when if when.tzinfo else when.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _plain(name: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(name or "").casefold()).strip()


def same_team(a: Any, b: Any) -> bool:
    x, y = _plain(a), _plain(b)
    return bool(x) and bool(y) and (x == y or x in y or y in x)


def stream_games(feed: dict[str, Any] | None, stream: dict[str, Any]) -> list[dict[str, Any]]:
    """The games in a stream's now-next-later feed, as TheSportsDB events of the day, each with the stream's end time
    (strEndTimestamp) and the stream's team id on its side."""
    out: list[dict[str, Any]] = []
    for channel in (feed or {}).get("data") or []:
        if not isinstance(channel, dict):
            continue
        for p in channel.get("programmes") or []:
            if not isinstance(p, dict):
                continue
            m = TITLE.match(str(p.get("title") or ""))
            start, end = _utc(p.get("starttime_utc")), _utc(p.get("endtime_utc"))
            if not m or start is None:
                continue
            home, away = m.group(1).strip(), m.group(2).strip()
            ident = p.get("programmeId") or p.get("slug") or start.strftime("%Y%m%d%H%M")
            out.append({
                "idEvent": f"{stream['key']}-{ident}",
                "strTimestamp": start.isoformat(),
                "strEndTimestamp": end.isoformat() if end and end > start else None,
                "strHomeTeam": home,
                "strAwayTeam": away,
                "strSport": stream["sport"],
                "strLeague": str(p.get("leagueTitle") or "").strip() or None,
                "idLeague": None,
                "idHomeTeam": stream["team_id"] if same_team(home, stream["team"]) else None,
                "idAwayTeam": stream["team_id"] if same_team(away, stream["team"]) else None,
                "strStream": stream["channel"],
            })
    return out


def missing_from(games: Iterable[dict[str, Any]], events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """The stream's games TheSportsDB does not already have: the same two teams, either way round, on the same UTC day."""
    known: list[tuple[str, str, str]] = []
    for e in events:
        start = _utc(e.get("strTimestamp"))
        if start is not None:
            known.append((start.date().isoformat(), str(e.get("strHomeTeam") or ""), str(e.get("strAwayTeam") or "")))
    out = []
    for g in games:
        start = _utc(g.get("strTimestamp"))
        if start is None:
            continue
        day, home, away = start.date().isoformat(), g["strHomeTeam"], g["strAwayTeam"]
        if any(d == day and ((same_team(home, h) and same_team(away, a)) or (same_team(home, a) and same_team(away, h)))
               for d, h, a in known):
            continue
        out.append(g)
    return out
