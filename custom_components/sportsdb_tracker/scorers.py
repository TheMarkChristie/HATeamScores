"""Who scored: pure functions, no Home Assistant, tested in tests/test_scorers.py.

The free TheSportsDB key returns only the first five events of a game's timeline (goals, cards and substitutions
mixed), so goals go missing. ESPN's public scores service lists every goal for the competitions it covers, with the
minute, the scorer and the assist, so it is the first source: the game is found on ESPN's scoreboard for its date by
both team names, then its summary is read. For a game ESPN does not cover, TheSportsDB's timeline is used and marked
incomplete when it holds fewer goals than the score.

  football       ESPN keyEvents marked as scoring plays: minute, scorer, assist, penalty or own goal
  ice hockey     ESPN plays marked as scoring plays: period and clock, scorer, assists
  NFL            ESPN scoringPlays: quarter and clock, the play as ESPN words it
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .tv import fold, names_team, team_needles

UTC = timezone.utc
SCORER_SPORTS = {"Soccer", "Ice Hockey", "American Football"}

# TheSportsDB competitions and their ESPN codes, by TheSportsDB league id where known, else by name
ESPN_LEAGUES: list[dict[str, Any]] = [
    {"slug": "soccer/eng.1", "ids": {"4328"}, "names": {"english premier league"}},
    {"slug": "soccer/eng.league_cup", "ids": {"4570"}, "names": {"efl cup", "english league cup", "carabao cup"}},
    {"slug": "soccer/eng.fa", "ids": set(), "names": {"fa cup", "english fa cup"}},
    {"slug": "soccer/sco.1", "ids": {"4330"}, "names": {"scottish premier league", "scottish premiership"}},
    {"slug": "soccer/sco.cis", "ids": set(), "names": {"scottish league cup"}},
    {"slug": "soccer/sco.tennents", "ids": {"4723"}, "names": {"scottish fa cup", "scottish cup"}},
    {"slug": "soccer/uefa.champions", "ids": {"4480"}, "names": {"uefa champions league"}},
    {"slug": "soccer/uefa.europa", "ids": set(), "names": {"uefa europa league"}},
    {"slug": "soccer/uefa.europa.conf", "ids": {"5071"}, "names": {"uefa conference league", "uefa europa conference league"}},
    {"slug": "soccer/uefa.nations", "ids": set(), "names": {"uefa nations league"}},
    {"slug": "soccer/fifa.worldq.uefa", "ids": set(), "names": {"fifa world cup qualifying uefa", "world cup qualifying uefa"}},
    {"slug": "soccer/fifa.friendly", "ids": set(), "names": {"international friendlies", "international friendly"}},
    {"slug": "soccer/nor.1", "ids": {"4358"}, "names": {"norwegian eliteserien"}},
    {"slug": "soccer/usa.1", "ids": {"4346"}, "names": {"american major league soccer", "mls"}},
    {"slug": "football/nfl", "ids": set(), "names": {"nfl"}},
    {"slug": "hockey/nhl", "ids": set(), "names": {"nhl"}},
]


def espn_slug(league_id: str | None, league: str | None) -> str | None:
    name = (league or "").strip().lower()
    for row in ESPN_LEAGUES:
        if (league_id and str(league_id) in row["ids"]) or (name and name in row["names"]):
            return row["slug"]
    return None


def scoreboard_dates(start: datetime) -> list[str]:
    """ESPN files a game under its date in US Eastern time; ask for that date and, if different, the UTC date."""
    utc_day = start.astimezone(UTC).strftime("%Y%m%d")
    eastern = (start.astimezone(UTC) - timedelta(hours=5)).strftime("%Y%m%d")
    return [eastern] if eastern == utc_day else [eastern, utc_day]


def _names(team: dict[str, Any]) -> str:
    return fold(" ".join(str(team.get(k) or "") for k in ("displayName", "shortDisplayName", "name", "location", "abbreviation")))


def find_espn_event(scoreboard: dict[str, Any], start: datetime, home: str, away: str, sport: str | None = None) -> str | None:
    """The ESPN event id of the game: on the scoreboard, within six hours of kick-off, with both teams on it."""
    hn, an = team_needles(home, sport), team_needles(away, sport)
    for ev in scoreboard.get("events") or []:
        try:
            when = datetime.fromisoformat(str(ev.get("date")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if abs((when - start).total_seconds()) > 6 * 3600:
            continue
        teams = [c.get("team") or {} for comp in ev.get("competitions") or [] for c in comp.get("competitors") or []]
        text = " ".join(_names(t) for t in teams)
        if names_team(text, hn) and names_team(text, an):
            return str(ev.get("id"))
    return None


def _sides(summary: dict[str, Any]) -> dict[str, str]:
    """ESPN team id -> home or away, from the summary's header."""
    out: dict[str, str] = {}
    for comp in (summary.get("header") or {}).get("competitions") or []:
        for c in comp.get("competitors") or []:
            tid = str((c.get("team") or {}).get("id") or c.get("id") or "")
            if tid:
                out[tid] = c.get("homeAway") or ""
    return out


def _final(summary: dict[str, Any]) -> bool:
    for comp in (summary.get("header") or {}).get("competitions") or []:
        if ((comp.get("status") or {}).get("type") or {}).get("completed"):
            return True
    return False


def _period(sport: str, number: Any) -> str:
    try:
        n = int(number)
    except (TypeError, ValueError):
        return ""
    if sport == "Ice Hockey":
        return {4: "OT", 5: "SO"}.get(n, f"P{n}")
    return f"Q{n}" if n <= 4 else "OT"


def parse_espn_summary(summary: dict[str, Any], sport: str | None) -> tuple[list[dict[str, str]], bool]:
    """The goals (or scoring plays) of an ESPN game summary, in order, and whether the game is over."""
    sides = _sides(summary)
    goals: list[dict[str, str]] = []
    if sport == "Soccer":
        for k in summary.get("keyEvents") or []:
            kind = str((k.get("type") or {}).get("text") or "")
            if not k.get("scoringPlay") and not kind.lower().startswith(("goal", "penalty - scored", "own goal")):
                continue
            people = [(p.get("athlete") or {}).get("displayName", "") for p in k.get("participants") or []]
            note = "pen" if "penalty" in kind.lower() else "og" if "own goal" in kind.lower() else ""
            goals.append({"time": str((k.get("clock") or {}).get("displayValue") or ""),
                          "side": sides.get(str((k.get("team") or {}).get("id") or ""), ""),
                          "player": people[0] if people else "", "assist": people[1] if len(people) > 1 and not note else "", "note": note})
    elif sport == "Ice Hockey":
        for p in summary.get("plays") or []:
            if not p.get("scoringPlay"):
                continue
            people = [(x.get("athlete") or {}).get("displayName", "") for x in p.get("participants") or []]
            clock = (p.get("clock") or {}).get("displayValue") or ""
            goals.append({"time": f"{_period(sport, (p.get('period') or {}).get('number'))} {clock}".strip(),
                          "side": sides.get(str((p.get("team") or {}).get("id") or ""), ""),
                          "player": people[0] if people else "", "assist": ", ".join(people[1:]), "note": ""})
    elif sport == "American Football":
        for p in summary.get("scoringPlays") or []:
            clock = (p.get("clock") or {}).get("displayValue") or ""
            goals.append({"time": f"{_period(sport, (p.get('period') or {}).get('number'))} {clock}".strip(),
                          "side": sides.get(str((p.get("team") or {}).get("id") or ""), ""),
                          "player": str(p.get("text") or ""), "assist": "", "note": ""})
    return goals, _final(summary)


def timeline_goals(rows: Iterable[dict[str, Any]], home_score: int | None, away_score: int | None) -> tuple[list[dict[str, str]], bool]:
    """Goals from TheSportsDB's timeline, and whether they account for the whole score (the free key returns only the
    first five events of a game, so often they do not)."""
    goals: list[dict[str, str]] = []
    for r in rows or []:
        if str(r.get("strTimeline") or "").lower() != "goal":
            continue
        detail = str(r.get("strTimelineDetail") or "").lower()
        note = "pen" if "penalty" in detail else "og" if "own" in detail else ""
        goals.append({"time": f"{r.get('intTime')}'" if r.get("intTime") else "", "side": "home" if r.get("strHome") == "Yes" else "away",
                      "player": str(r.get("strPlayer") or ""), "assist": "" if note else str(r.get("strAssist") or ""), "note": note})
    total = (home_score or 0) + (away_score or 0)
    return goals, len(goals) >= total
