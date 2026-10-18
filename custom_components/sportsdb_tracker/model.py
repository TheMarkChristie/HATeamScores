"""The pure model: TheSportsDB records, what the integration remembers for a team, and the sensor it shows.

Nothing here imports Home Assistant, so tests/ runs it on plain Python. The coordinator only sequences the API calls
around these functions:

  needs_lookup / absorb_lookup   a fixture whose kick-off has passed is looked up by id until it is finished
  needs_next / absorb_next       the team's next fixture is read, and re-read now and then in case it moved
  absorb_last                    on first run, the latest result TheSportsDB lists (a home game on the free key)
  present                        the sensor's state (PRE, IN, POST, NOT_FOUND) and attributes: the game shown, both
                                 sides with badges, and the fixtures and results lists the Team Scores card reads
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .const import (
    ATTRIBUTION,
    CANCELLED_STATUSES,
    DEFAULT_GAME_MINUTES,
    FINISHED_STATUSES,
    GAME_MINUTES,
    HIGHLIGHTS_DAYS,
    HIGHLIGHTS_RECHECK_HOURS,
    LOOKUP_GRACE_HOURS,
    NEXT_CHECK_MINUTES,
    RESULT_WAIT_MINUTES,
    SPORT_PREFIX,
    STATE_IN,
    STATE_NOT_FOUND,
    STATE_POST,
    STATE_PRE,
)

UTC = timezone.utc
EVENT_URL = "https://www.thesportsdb.com/event/{id}"
TEAM_URL = "https://www.thesportsdb.com/team/{id}"
ToLocal = Callable[[datetime], datetime]


def _str(value: Any) -> str | None:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return None


def _int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _when(timestamp: str | None, date: str | None, time: str | None) -> tuple[datetime | None, bool]:
    """A game's start in UTC, and whether the time of day is known. strTimestamp is UTC without an offset."""
    if timestamp:
        try:
            d = datetime.fromisoformat(timestamp)
            return (d if d.tzinfo else d.replace(tzinfo=UTC)).astimezone(UTC), True
        except ValueError:
            pass
    if date:
        try:
            if time:
                d = datetime.fromisoformat(f"{date}T{time}")
                return (d if d.tzinfo else d.replace(tzinfo=UTC)).astimezone(UTC), True
            return datetime.fromisoformat(date).replace(hour=12, tzinfo=UTC), False
        except ValueError:
            pass
    return None, False


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        d = datetime.fromisoformat(value)
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=UTC)).astimezone(UTC)


def game_minutes(sport: str | None) -> int:
    return GAME_MINUTES.get(sport or "", DEFAULT_GAME_MINUTES)


def prefix_for_sport(sport: str | None) -> str:
    if sport in SPORT_PREFIX:
        return SPORT_PREFIX[sport]
    return re.sub(r"[^a-z0-9]+", "_", (sport or "sports").lower()).strip("_") or "sports"


_SKIP_WORDS = {"fc", "cf", "sc", "afc", "bc", "bk", "il", "the", "club", "basket", "ishockey", "hc", "ihc"}


def abbreviation(name: str) -> str:
    """A short label for a team without one: initials of a multi-word name, else its first three letters."""
    words = [w for w in re.split(r"[\s\-./]+", name) if w and w[0].isalpha() and w.lower() not in _SKIP_WORDS]
    if len(words) >= 2:
        return "".join(w[0] for w in words[:3]).upper()
    return (words[0] if words else name)[:3].upper()


@dataclass
class Team:
    """A team as TheSportsDB describes it (lookupteam / searchteams)."""

    id: str
    name: str
    sport: str = ""
    short: str | None = None
    league: str | None = None
    league_id: str | None = None
    league2: str | None = None
    stadium: str | None = None
    city: str | None = None
    country: str | None = None
    badge: str | None = None
    logo: str | None = None
    website: str | None = None
    colour1: str | None = None
    colour2: str | None = None
    gender: str | None = None
    alternate: str | None = None       # strTeamAlternate: other names, comma separated (helps find the team in TV guides)

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> Team:
        g = lambda k: _str(raw.get(k))  # noqa: E731
        return cls(id=str(raw.get("idTeam") or ""), name=g("strTeam") or "", sport=g("strSport") or "", short=g("strTeamShort"),
                   league=g("strLeague"), league_id=g("idLeague"), league2=g("strLeague2"), stadium=g("strStadium"),
                   city=g("strLocation"), country=g("strCountry"), badge=g("strBadge"), logo=g("strLogo"),
                   website=g("strWebsite"), colour1=g("strColour1"), colour2=g("strColour2"), gender=g("strGender"),
                   alternate=g("strTeamAlternate"))

    @property
    def abbr(self) -> str:
        """Always derived from the name, the same way as an opponent's, so the two sensors of one game carry the
        same pair of abbreviations."""
        return abbreviation(self.name)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Team:
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in allowed})


@dataclass
class Event:
    """A game as TheSportsDB describes it (eventsnext / eventslast / lookupevent)."""

    id: str
    name: str = ""
    sport: str = ""
    league: str = ""
    league_id: str | None = None
    league_badge: str | None = None
    season: str | None = None
    round: str | None = None
    start: datetime | None = None
    time_known: bool = True
    home_id: str | None = None
    home_name: str = ""
    home_badge: str | None = None
    away_id: str | None = None
    away_name: str = ""
    away_badge: str | None = None
    home_score: int | None = None
    away_score: int | None = None
    venue: str | None = None
    city: str | None = None
    country: str | None = None
    status: str | None = None
    postponed: bool = False
    video: str | None = None
    thumb: str | None = None
    finished_at: datetime | None = None     # when the integration first saw it finished (capped at its expected end)

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> Event:
        g = lambda k: _str(raw.get(k))  # noqa: E731
        start, known = _when(g("strTimestamp"), g("dateEvent"), g("strTime"))
        return cls(id=str(raw.get("idEvent") or ""), name=g("strEvent") or "", sport=g("strSport") or "", league=g("strLeague") or "",
                   league_id=g("idLeague"), league_badge=g("strLeagueBadge"), season=g("strSeason"), round=g("intRound"),
                   start=start, time_known=known, home_id=g("idHomeTeam"), home_name=g("strHomeTeam") or "",
                   home_badge=g("strHomeTeamBadge"), away_id=g("idAwayTeam"), away_name=g("strAwayTeam") or "",
                   away_badge=g("strAwayTeamBadge"), home_score=_int(raw.get("intHomeScore")), away_score=_int(raw.get("intAwayScore")),
                   venue=g("strVenue"), city=g("strCity"), country=g("strCountry"), status=g("strStatus"),
                   postponed=(g("strPostponed") or "").lower() == "yes", video=g("strVideo"), thumb=g("strThumb"))

    @property
    def expected_end(self) -> datetime | None:
        return self.start + timedelta(minutes=game_minutes(self.sport)) if self.start else None

    @property
    def cancelled(self) -> bool:
        return self.postponed or (self.status or "").strip().upper() in CANCELLED_STATUSES

    def finished(self, now: datetime) -> bool:
        """Finished: TheSportsDB says so, or both scores are in and the game ended over an hour ago."""
        if (self.status or "").strip().upper() in FINISHED_STATUSES:
            return True
        end = self.expected_end
        return self.home_score is not None and self.away_score is not None and end is not None and now >= end + timedelta(hours=1)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["start"], d["finished_at"] = _iso(self.start), _iso(self.finished_at)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        allowed = {f.name for f in fields(cls)}
        kw = {k: v for k, v in data.items() if k in allowed}
        kw["start"], kw["finished_at"] = _parse_iso(data.get("start")), _parse_iso(data.get("finished_at"))
        return cls(**kw)


@dataclass
class Memory:
    """What the integration keeps for a team between updates, and across restarts."""

    tracked: Event | None = None        # the fixture being watched: next, in play, or awaiting its result
    last: Event | None = None           # the latest finished game it knows
    checked_next: datetime | None = None
    seeded: bool = False                # the first-run read of eventslast has been done
    upcoming: list[Event] = field(default_factory=list)   # every coming fixture the API listed, soonest first
    recent: list[Event] = field(default_factory=list)     # finished games it has seen, latest first (at most KEEP_RECENT)
    tv: dict[str, list[dict[str, str]]] = field(default_factory=dict)   # event id -> [{channel, country, source}]
    tv_checked: dict[str, str] = field(default_factory=dict)            # event id -> when TheSportsDB was last asked
    scorers: dict[str, dict[str, Any]] = field(default_factory=dict)    # event id -> {goals, final, complete, source, checked}
    highlights: dict[str, dict[str, str]] = field(default_factory=dict)  # event id -> {url, checked}: a recent game's video

    def to_dict(self) -> dict[str, Any]:
        return {"tracked": self.tracked.to_dict() if self.tracked else None, "last": self.last.to_dict() if self.last else None,
                "checked_next": _iso(self.checked_next), "seeded": self.seeded,
                "upcoming": [e.to_dict() for e in self.upcoming], "recent": [e.to_dict() for e in self.recent],
                "tv": self.tv, "tv_checked": self.tv_checked, "scorers": self.scorers, "highlights": self.highlights}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Memory:
        mem = cls(tracked=Event.from_dict(data["tracked"]) if data.get("tracked") else None,
                  last=Event.from_dict(data["last"]) if data.get("last") else None,
                  checked_next=_parse_iso(data.get("checked_next")), seeded=bool(data.get("seeded")),
                  upcoming=[Event.from_dict(e) for e in data.get("upcoming") or []],
                  recent=[Event.from_dict(e) for e in data.get("recent") or []],
                  tv={str(k): [dict(i) for i in v] for k, v in (data.get("tv") or {}).items() if isinstance(v, list)},
                  tv_checked={str(k): str(v) for k, v in (data.get("tv_checked") or {}).items()},
                  scorers={str(k): dict(v) for k, v in (data.get("scorers") or {}).items() if isinstance(v, dict)},
                  highlights={str(k): {str(a): str(b) for a, b in v.items()}
                              for k, v in (data.get("highlights") or {}).items() if isinstance(v, dict)})
        # memory saved by a version without the lists: the games it knew go into them
        if mem.tracked is not None and not any(e.id == mem.tracked.id for e in mem.upcoming):
            mem.upcoming.insert(0, mem.tracked)
        if mem.last is not None and not any(e.id == mem.last.id for e in mem.recent):
            if mem.last.finished_at is None:
                mem.last.finished_at = mem.last.expected_end or mem.last.start
            mem.recent.insert(0, mem.last)
        return mem


KEEP_RECENT = 10

_VIDEO = re.compile(r"^https?://\S+$", re.I)


def video_url(value: str | None) -> str | None:
    """A highlights link worth showing: a web address, nothing else."""
    value = (value or "").strip()
    return value if _VIDEO.match(value) else None


def game_video(game: Event, highlights: dict[str, dict[str, str]] | None) -> str | None:
    """The game's highlights: on the game as first read, or found by asking again since."""
    return video_url(game.video) or video_url(((highlights or {}).get(game.id) or {}).get("url"))


def highlights_due(mem: Memory, now: datetime) -> list[Event]:
    """Finished games of the last HIGHLIGHTS_DAYS without highlights yet and not asked in the last
    HIGHLIGHTS_RECHECK_HOURS."""
    due = []
    for e in mem.recent:
        if e.start is None or now - e.start > timedelta(days=HIGHLIGHTS_DAYS) or game_video(e, mem.highlights):
            continue
        checked = _parse_iso((mem.highlights.get(e.id) or {}).get("checked"))
        if checked is None or now - checked >= timedelta(hours=HIGHLIGHTS_RECHECK_HOURS):
            due.append(e)
    return due


def _remember_finished(mem: Memory, events: list[Event]) -> None:
    """Finished games into mem.recent (newest first, no duplicates) and out of mem.upcoming; mem.last is the newest."""
    by_id = {e.id: e for e in mem.recent}
    for e in events:
        if e.finished_at is None:
            e.finished_at = e.expected_end or e.start
        by_id[e.id] = e
    mem.recent = sorted(by_id.values(), key=lambda e: e.start or e.finished_at, reverse=True)[:KEEP_RECENT]
    done = {e.id for e in mem.recent}
    mem.upcoming = [e for e in mem.upcoming if e.id not in done]
    if mem.recent and (mem.last is None or mem.last.id not in done or mem.last.id != mem.recent[0].id):
        mem.last = mem.recent[0]


def _live(mem: Memory, now: datetime) -> bool:
    return mem.tracked is not None and mem.tracked.start is not None and now >= mem.tracked.start


def needs_lookup(mem: Memory, now: datetime) -> bool:
    """The tracked fixture has kicked off: read it by id until it is finished."""
    return _live(mem, now)


def absorb_lookup(mem: Memory, event: Event | None, now: datetime) -> None:
    tracked = mem.tracked
    if tracked is None:
        return
    if event is None:
        end = tracked.expected_end
        if end is not None and now > end + timedelta(hours=LOOKUP_GRACE_HOURS):
            mem.tracked = None               # the API lost it: stop asking
        return
    if event.cancelled:
        mem.tracked = None
        mem.upcoming = [e for e in mem.upcoming if e.id != event.id]
        return
    if event.finished(now):
        end = event.expected_end
        event.finished_at = min(now, end) if end else now
        _remember_finished(mem, [event])
        mem.last = event
        mem.tracked = None
    else:
        event.finished_at = None
        mem.tracked = event                  # keeps a moved kick-off, a status, premium live scores
        mem.upcoming = [event if e.id == event.id else e for e in mem.upcoming] or [event]


def needs_next(mem: Memory, now: datetime) -> bool:
    """No fixture is tracked, or the one tracked was read a while ago (it may have moved). Not during a game."""
    if _live(mem, now):
        return False
    if mem.tracked is None or mem.checked_next is None:
        return True
    return now - mem.checked_next >= timedelta(minutes=NEXT_CHECK_MINUTES)


def absorb_next(mem: Memory, events: list[Event], now: datetime) -> None:
    mem.checked_next = now
    done = {e.id for e in mem.recent} | ({mem.last.id} if mem.last else set())
    upcoming = sorted((e for e in events if e.start is not None and not e.cancelled and e.id not in done), key=lambda e: e.start)
    if _live(mem, now):                      # the game in play stays first; the list behind it may still refresh
        mem.upcoming = [mem.tracked] + [e for e in upcoming if e.id != mem.tracked.id]
        return
    mem.upcoming = upcoming
    mem.tracked = upcoming[0] if upcoming else None


def absorb_last(mem: Memory, events: list[Event], now: datetime) -> None:
    """First run: the finished games TheSportsDB lists (home games on the free key), so the sensor has results from
    the start."""
    mem.seeded = True
    done = [e for e in events if e.start is not None and e.finished(now)]
    if done:
        _remember_finished(mem, done)
        if mem.tracked is not None and mem.tracked.id in {e.id for e in done}:
            mem.tracked = None


def next_transition(mem: Memory, now: datetime, results_hours: int, pre_hours: int) -> datetime | None:
    """The next moment the sensor changes on its own: kick-off, the pre-match switch, or a result expiring."""
    cands: list[datetime] = []
    if mem.tracked is not None and mem.tracked.start is not None:
        cands += [mem.tracked.start, mem.tracked.start - timedelta(hours=pre_hours), mem.tracked.expected_end + timedelta(minutes=RESULT_WAIT_MINUTES)]
    if mem.last is not None and mem.last.finished_at is not None:
        cands.append(mem.last.finished_at + timedelta(hours=results_hours))
    future = [c for c in cands if c > now]
    return min(future) if future else None


def kickoff_text(local: datetime, today: datetime, time_known: bool = True) -> str:
    """When a game starts, for people: Today 15:00, Tomorrow 19:30, Sat 18 Oct 15:00."""
    day, ref = local.date(), today.date()
    when = "Today" if day == ref else "Tomorrow" if day == ref + timedelta(days=1) else f"{local:%a} {local.day} {local:%b}"
    return f"{when} {local:%H:%M}" if time_known else when


def _is_home(team: Team, game: Event) -> bool:
    if game.home_id and team.id:
        return game.home_id == team.id
    return game.home_name.strip().lower() == team.name.strip().lower()


def _brief(game: Event | None, now: datetime, to_local: ToLocal, tv: dict[str, list[dict[str, str]]] | None = None,
           scorers: dict[str, dict[str, Any]] | None = None,
           highlights: dict[str, dict[str, str]] | None = None) -> dict[str, Any] | None:
    """One game for the card: both sides with badges, where and when, the score once it is in."""
    if game is None:
        return None
    local = to_local(game.start) if game.start else None
    end = game.expected_end
    finished = game.finished_at is not None or game.finished(now)
    return {"event_id": game.id, "name": game.name, "date": _iso(game.start), "day": local.date().isoformat() if local else None,
            "time": f"{local:%H:%M}" if local and game.time_known else None,
            "when": kickoff_text(local, to_local(now), game.time_known) if local else None,
            "venue": game.venue, "country": game.country, "league": game.league, "league_logo": game.league_badge,
            "sport": game.sport, "home_id": game.home_id, "home": game.home_name, "home_badge": game.home_badge,
            "away_id": game.away_id, "away": game.away_name, "away_badge": game.away_badge,
            "home_score": game.home_score, "away_score": game.away_score, "status": game.status, "finished": finished,
            "live": bool(game.start and not finished and now >= game.start and (end is None or now < end + timedelta(minutes=RESULT_WAIT_MINUTES))),
            "tv": [] if finished else list((tv or {}).get(game.id) or []),
            "goals": list(((scorers or {}).get(game.id) or {}).get("goals") or []),
            "goals_complete": bool(((scorers or {}).get(game.id) or {}).get("complete", True)),
            "video": game_video(game, highlights) if finished else None}


def present(team: Team, mem: Memory, now: datetime, results_hours: int, pre_hours: int,
            to_local: ToLocal | None = None) -> tuple[str, dict[str, Any]]:
    """The sensor's state and attributes."""
    loc: ToLocal = to_local or (lambda d: d)
    tracked, last = mem.tracked, mem.last
    live = _live(mem, now)
    waiting = live and tracked.expected_end is not None and now >= tracked.expected_end + timedelta(minutes=RESULT_WAIT_MINUTES)
    soon = (tracked is not None and tracked.start is not None and not live
            and tracked.start - now <= timedelta(hours=pre_hours))
    recent = last is not None and last.finished_at is not None and now < last.finished_at + timedelta(hours=results_hours)
    if live and not waiting:
        state, game = STATE_IN, tracked
    elif live:
        state, game = STATE_POST, tracked        # over by the clock, TheSportsDB has not posted the result yet
    elif recent and not soon:
        state, game = STATE_POST, last
    elif tracked is not None:
        state, game = STATE_PRE, tracked
    elif last is not None:
        state, game = STATE_POST, last           # nothing coming up: the last result stays, dated
    else:
        state, game = STATE_NOT_FOUND, None

    attrs: dict[str, Any] = {
        "sport": team.sport, "sport_prefix": prefix_for_sport(team.sport),
        "league": game.league if game and game.league else team.league, "league_logo": game.league_badge if game else None,
        "season": game.season if game else None, "round": game.round if game else None,
        "team_id": team.id, "team_name": team.name, "team_long_name": team.name, "team_abbr": team.abbr,
        "team_logo": team.badge, "team_colors": [c for c in (team.colour1, team.colour2) if c], "team_record": None,
        "team_url": TEAM_URL.format(id=team.id) if team.id else None,
        "team_homeaway": None, "team_score": None, "team_winner": None,
        "opponent_id": None, "opponent_name": None, "opponent_long_name": None, "opponent_abbr": None, "opponent_logo": None,
        "opponent_homeaway": None, "opponent_score": None, "opponent_winner": None, "opponent_record": None,
        "event_id": None, "event_name": None, "event_url": None, "date": None, "kickoff_in": None,
        "venue": None, "location": None, "country": None, "clock": None, "video": None,
        "tv_network": None, "tv": [], "last_play": None, "odds": None, "series_summary": None,
    }
    if game is not None:
        home = _is_home(team, game)
        us_badge, us_score = (game.home_badge, game.home_score) if home else (game.away_badge, game.away_score)
        them_id, them_name, them_badge, them_score = ((game.away_id, game.away_name, game.away_badge, game.away_score) if home
                                                     else (game.home_id, game.home_name, game.home_badge, game.home_score))
        settled = state == STATE_POST and game.home_score is not None and game.away_score is not None
        local = loc(game.start) if game.start else None
        clock = None
        if state == STATE_IN:
            clock = "In play"
        elif state == STATE_POST:
            if game is tracked:
                clock = "Awaiting result"
            elif recent or local is None:
                clock = "FT"
            else:
                clock = f"FT {local.day} {local:%b}"
        attrs.update({
            "league_logo": game.league_badge, "team_logo": team.badge or us_badge,
            "team_homeaway": "home" if home else "away", "team_score": us_score,
            "team_winner": settled and us_score > them_score if settled else None,
            "opponent_id": them_id, "opponent_name": them_name, "opponent_long_name": them_name,
            "opponent_abbr": abbreviation(them_name) if them_name else None, "opponent_logo": them_badge,
            "opponent_homeaway": "away" if home else "home", "opponent_score": them_score,
            "opponent_winner": settled and them_score > us_score if settled else None,
            "event_id": game.id, "event_name": game.name, "event_url": EVENT_URL.format(id=game.id) if game.id else None,
            "date": _iso(game.start),
            "kickoff_in": kickoff_text(local, loc(now), game.time_known) if state == STATE_PRE and local else None,
            "venue": game.venue, "location": ", ".join(p for p in (game.venue, game.country) if p) or None,
            "country": game.country, "clock": clock, "video": game_video(game, mem.highlights),
            "tv_network": ", ".join(i["channel"] for i in mem.tv.get(game.id) or []) or None,
            "tv": list(mem.tv.get(game.id) or []),
        })
    attrs["next_game"] = _brief(tracked, now, loc, mem.tv, mem.scorers, mem.highlights) if state in (STATE_POST, STATE_NOT_FOUND) and tracked is not None and game is not tracked else None
    attrs["last_game"] = _brief(last, now, loc, mem.tv, mem.scorers, mem.highlights) if state in (STATE_PRE, STATE_IN, STATE_NOT_FOUND) and last is not None else None
    # every game the integration knows, for a card that lays them out by day
    attrs["fixtures"] = [_brief(e, now, loc, mem.tv, mem.scorers, mem.highlights) for e in mem.upcoming if e.start is not None]
    attrs["results"] = [_brief(e, now, loc, mem.tv, mem.scorers, mem.highlights) for e in mem.recent]
    attrs["last_update"] = now.isoformat()
    attrs["attribution"] = ATTRIBUTION
    return state, attrs
