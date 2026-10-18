"""One coordinator per team: reads TheSportsDB on a schedule and keeps the team's fixture memory on disk."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import SportsDBClient, SportsDBError
from .espn import EspnClient, EspnError, get_espn
from .guide import get_guide
from .const import (
    CONF_API_KEY,
    CONF_LEAGUE,
    CONF_PRE_HOURS,
    CONF_RESULTS_HOURS,
    CONF_SPORT,
    CONF_TEAM_ID,
    CONF_TEAM_NAME,
    DEFAULT_API_KEY,
    DEFAULT_PRE_HOURS,
    DEFAULT_RESULTS_HOURS,
    DEFAULT_TV,
    SCORERS_DAYS,
    SCORERS_RECHECK_MINUTES,
    DOMAIN,
    STORAGE_VERSION,
    SPORTSDB_TV_HOURS,
    TV_DAYS_AHEAD,
    UPDATE_MINUTES_IDLE,
    UPDATE_MINUTES_LIVE,
)
from .model import (
    Event,
    Memory,
    Team,
    absorb_last,
    absorb_lookup,
    absorb_next,
    highlights_due,
    needs_lookup,
    needs_next,
    next_transition,
    video_url,
)
from .scorers import SCORER_SPORTS, espn_slug, find_espn_event, parse_espn_summary, scoreboard_dates, timeline_goals
from .tv import guide_listings, merge, pair_needles, sportsdb_listings, with_defaults

_LOGGER = logging.getLogger(__name__)
RETRY_MINUTES = 3


class SportsDBCoordinator(DataUpdateCoordinator[Memory]):
    """Keeps one team's next fixture and latest result current."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: SportsDBClient) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=f"{DOMAIN} {entry.title}",
                         update_interval=timedelta(minutes=UPDATE_MINUTES_IDLE))
        self.client = client
        self.entry = entry
        self.team = Team(id=str(entry.data[CONF_TEAM_ID]), name=entry.data.get(CONF_TEAM_NAME) or entry.title,
                         sport=entry.data.get(CONF_SPORT) or "", league=entry.data.get(CONF_LEAGUE))
        self.memory = Memory()
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self._team_fresh = False
        self._saved: dict[str, Any] | None = None

    def _setting(self, key: str, default: Any) -> Any:
        if key in self.entry.options:
            return self.entry.options[key]
        return self.entry.data.get(key, default)

    @property
    def api_key(self) -> str:
        return str(self._setting(CONF_API_KEY, DEFAULT_API_KEY) or DEFAULT_API_KEY)

    @property
    def results_hours(self) -> int:
        return int(self._setting(CONF_RESULTS_HOURS, DEFAULT_RESULTS_HOURS))

    @property
    def pre_hours(self) -> int:
        return int(self._setting(CONF_PRE_HOURS, DEFAULT_PRE_HOURS))

    async def async_load(self) -> None:
        """What was saved last time, so a restart shows the fixture and result at once and keeps an away game's id."""
        data = await self._store.async_load()
        if not isinstance(data, dict):
            return
        try:
            self.memory = Memory.from_dict(data.get("memory") or {})
            if data.get("team"):
                self.team = Team.from_dict(data["team"])
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.warning("%s: stored fixtures could not be read (%s); starting afresh", self.name, err)
            self.memory = Memory()
        self._saved = data

    async def _async_update_data(self) -> Memory:
        now = dt_util.utcnow()
        mem, key = self.memory, self.api_key
        failed = False
        try:
            if not self._team_fresh:
                raw = await self.client.lookup_team(key, self.team.id)
                if raw:
                    self.team = Team.parse(raw)
                self._team_fresh = True
            if needs_lookup(mem, now) and mem.tracked is not None:
                raw = await self.client.lookup_event(key, mem.tracked.id)
                absorb_lookup(mem, Event.parse(raw) if raw else None, now)
            if needs_next(mem, now):
                raws = await self.client.next_events(key, self.team.id)
                absorb_next(mem, [Event.parse(r) for r in raws], now)
                if not mem.seeded:
                    raws = await self.client.last_events(key, self.team.id)
                    absorb_last(mem, [Event.parse(r) for r in raws], now)
        except SportsDBError as err:
            if mem.tracked is None and mem.last is None and not self._team_fresh:
                raise UpdateFailed(f"TheSportsDB: {err}") from err
            _LOGGER.warning("%s: TheSportsDB: %s (keeping the last known fixtures)", self.name, err)
            failed = True
        await self._update_tv(mem, now, key)
        await self._update_scorers(mem, now, key)
        await self._update_highlights(mem, now, key)
        data = {"memory": mem.to_dict(), "team": self.team.to_dict()}
        if data != self._saved:
            await self._store.async_save(data)
            self._saved = data
        self.update_interval = self._interval(mem, now)
        if failed:                                   # a refused read is tried again soon, not in half an hour
            self.update_interval = min(self.update_interval, timedelta(minutes=RETRY_MINUTES))
        return mem

    def _extra_names(self, team_id: str | None) -> list[str]:
        """Other names for this team (TheSportsDB's short name and alternates) to find it in the TV guides."""
        if not team_id or team_id != self.team.id:
            return []
        alt = [a.strip() for a in (self.team.alternate or "").split(",")]
        return [n for n in [self.team.short, *alt] if n]

    async def _update_tv(self, mem: Memory, now: datetime, key: str) -> None:
        """The UK and Norwegian channels of every fixture in the next fortnight: the TV guides each update, TheSportsDB's
        broadcaster list twice a day per game (not on the refresh at start-up, so Home Assistant is not held up). A guide
        that has rotated past a game, or failed to download, keeps what was found earlier."""
        horizon = now + timedelta(days=TV_DAYS_AHEAD)
        programmes = get_guide(self.hass).programmes()      # never waits: the guides download in the background
        first = self.data is None
        for e in mem.upcoming:
            if e.start is None or not (now - timedelta(hours=4) <= e.start <= horizon):
                continue
            before = mem.tv.get(e.id) or []
            home, away = pair_needles(e.home_name, e.away_name, e.sport, self._extra_names(e.home_id), self._extra_names(e.away_id))
            found = guide_listings(e.start, home, away, programmes) or [i for i in before if i.get("source") == "guide"]
            sportsdb = [i for i in before if i.get("source") == "thesportsdb"]
            asked = mem.tv_checked.get(e.id)
            stale = asked is None or now - datetime.fromisoformat(asked) >= timedelta(hours=SPORTSDB_TV_HOURS)
            if stale and e.start > now and not first:
                try:
                    sportsdb = sportsdb_listings(await self.client.lookup_tv(key, e.id))
                    mem.tv_checked[e.id] = now.isoformat()
                except SportsDBError as err:
                    _LOGGER.debug("%s: broadcasters of %s not read: %s", self.name, e.id, err)
            mem.tv[e.id] = with_defaults(merge(found, sportsdb), e.league_id, e.league, DEFAULT_TV)
        keep = {e.id for e in mem.upcoming}
        mem.tv = {k: v for k, v in mem.tv.items() if k in keep}
        mem.tv_checked = {k: v for k, v in mem.tv_checked.items() if k in keep}

    async def _update_scorers(self, mem: Memory, now: datetime, key: str) -> None:
        """Who scored in the team's games of the last few days and in the game in play: ESPN first, TheSportsDB's
        timeline for a football game ESPN does not cover. A game is asked again while its goals are not final (every
        update while it is on, every SCORERS_RECHECK_MINUTES after), and never during Home Assistant's start-up."""
        if self.data is None:
            return
        live_id = mem.tracked.id if mem.tracked is not None and mem.tracked.start is not None and now >= mem.tracked.start else None
        games = [e for e in mem.recent if e.start is not None and now - e.start <= timedelta(days=SCORERS_DAYS)]
        if live_id:
            games.append(mem.tracked)
        espn = get_espn(self.hass)
        for e in games:
            if e.sport not in SCORER_SPORTS:
                continue
            have = mem.scorers.get(e.id)
            if have:
                settled = have.get("final") and (have.get("complete", True) or now - e.start > timedelta(hours=12))
                if settled and e.id != live_id:
                    continue
                checked = datetime.fromisoformat(have["checked"]) if have.get("checked") else None
                if e.id != live_id and checked and now - checked < timedelta(minutes=SCORERS_RECHECK_MINUTES):
                    continue
            got = await self._espn_goals(espn, e, now)
            if got is None and e.sport == "Soccer" and e.id != live_id:
                try:
                    goals, complete = timeline_goals(await self.client.lookup_timeline(key, e.id), e.home_score, e.away_score)
                    got = {"goals": goals, "final": True, "complete": complete, "source": "thesportsdb"}
                except SportsDBError as err:
                    _LOGGER.debug("%s: timeline of %s not read: %s", self.name, e.id, err)
            if got is None:
                got = {"goals": (have or {}).get("goals") or [], "final": now - e.start > timedelta(hours=12),
                       "complete": (have or {}).get("complete", True), "source": (have or {}).get("source", "none")}
            got["checked"] = now.isoformat()
            mem.scorers[e.id] = got
        keep = {e.id for e in mem.recent} | {e.id for e in mem.upcoming}
        mem.scorers = {k: v for k, v in mem.scorers.items() if k in keep}

    async def _update_highlights(self, mem: Memory, now: datetime, key: str) -> None:
        """The highlights video of the team's finished games of the last few days. TheSportsDB adds it to a game some
        hours after the final whistle (for most top leagues; a YouTube link), so a game without one is read again every
        HIGHLIGHTS_RECHECK_HOURS until it has one. Not on the refresh at start-up."""
        if self.data is not None:
            for e in highlights_due(mem, now):
                try:
                    raw = await self.client.lookup_event(key, e.id)
                except SportsDBError as err:
                    _LOGGER.debug("%s: highlights of %s not read: %s", self.name, e.id, err)
                    continue
                mem.highlights[e.id] = {"url": video_url((raw or {}).get("strVideo")) or "", "checked": now.isoformat()}
        keep = {e.id for e in mem.recent}
        mem.highlights = {k: v for k, v in mem.highlights.items() if k in keep}

    async def _espn_goals(self, espn: EspnClient, e: Event, now: datetime) -> dict | None:
        slug = espn_slug(e.league_id, e.league)
        if not slug or e.start is None:
            return None
        try:
            event_id = None
            for day in scoreboard_dates(e.start):
                event_id = find_espn_event(await espn.scoreboard(slug, day), e.start, e.home_name, e.away_name, e.sport)
                if event_id:
                    break
            if not event_id:
                return None
            goals, final = parse_espn_summary(await espn.summary(slug, event_id, e.finished(now)), e.sport)
        except EspnError as err:
            _LOGGER.debug("%s: ESPN has no scorers for %s: %s", self.name, e.id, err)
            return None
        return {"goals": goals, "final": final, "complete": True, "source": "espn"}

    def _interval(self, mem: Memory, now) -> timedelta:
        tracked = mem.tracked
        live_soon = tracked is not None and tracked.start is not None and tracked.start - now <= timedelta(minutes=15)
        base = timedelta(minutes=UPDATE_MINUTES_LIVE if live_soon else UPDATE_MINUTES_IDLE)
        change = next_transition(mem, now, self.results_hours, self.pre_hours)
        if change is not None:
            base = min(base, max(timedelta(minutes=1), change - now + timedelta(seconds=5)))
        return base

    async def async_remove_store(self) -> None:
        await self._store.async_remove()
