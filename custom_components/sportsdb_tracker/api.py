"""TheSportsDB v1 client: one shared instance per Home Assistant, paced to the key's rate limit, with a short cache.

The free key allows 30 requests a minute across everything that uses it, so every team's coordinator goes through
this one client and waits its turn. Responses are cached for a minute, so a team added twice or a flow searching the
same name does not spend a second request.
"""
from __future__ import annotations

import asyncio
import logging
from time import monotonic
from typing import Any
from urllib.parse import quote

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import API_BASE, DEFAULT_API_KEY, DOMAIN, FREE_MIN_INTERVAL, PREMIUM_MIN_INTERVAL

_LOGGER = logging.getLogger(__name__)
TIMEOUT = aiohttp.ClientTimeout(total=25)
CACHE_SECONDS = 60
BACKOFF_SECONDS = 30                      # after a 429, nothing is sent for this long, then the call is tried once more


class SportsDBError(Exception):
    """TheSportsDB did not answer, answered with an error, or sent something that is not JSON."""


def get_client(hass: HomeAssistant) -> "SportsDBClient":
    """The one client for this Home Assistant: every team and every setup flow goes through it, so the key's
    rate limit is shared."""
    shared = hass.data.setdefault(DOMAIN, {})
    if "client" not in shared:
        shared["client"] = SportsDBClient(async_get_clientsession(hass))
    return shared["client"]


class SportsDBClient:
    """Paced GET calls to TheSportsDB v1."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._lock = asyncio.Lock()
        self._next_at = 0.0
        self._cache: dict[str, tuple[float, Any]] = {}

    async def _get(self, key: str, call: str) -> dict[str, Any]:
        key = key.strip() or DEFAULT_API_KEY
        cache_key = f"{key}:{call}"
        hit = self._cache.get(cache_key)
        if hit and monotonic() < hit[0]:
            return hit[1]
        url = f"{API_BASE}/{quote(key, safe='')}/{call}"
        interval = FREE_MIN_INTERVAL if key == DEFAULT_API_KEY else PREMIUM_MIN_INTERVAL
        async with self._lock:
            hit = self._cache.get(cache_key)            # an identical request queued ahead of this one may have answered it
            if hit and monotonic() < hit[0]:
                return hit[1]
            data: Any = None
            for attempt in (1, 2):
                wait = self._next_at - monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                try:
                    async with self._session.get(url, timeout=TIMEOUT, headers={"Accept": "application/json"}) as resp:
                        if resp.status == 429:
                            self._next_at = monotonic() + BACKOFF_SECONDS
                            if attempt == 1:
                                _LOGGER.debug("TheSportsDB rate limit reached; waiting %s s before %s", BACKOFF_SECONDS, call)
                                continue
                            raise SportsDBError("rate limit reached (HTTP 429) twice")
                        if resp.status != 200:
                            raise SportsDBError(f"HTTP {resp.status} for {call}")
                        data = await resp.json(content_type=None)
                        break
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
                    # ValueError: a body that is not JSON (an HTML or PHP warning page sent with 200)
                    raise SportsDBError(f"{type(err).__name__}: {err}") from err
                finally:
                    if monotonic() + interval > self._next_at:
                        self._next_at = monotonic() + interval
        if not isinstance(data, dict):
            raise SportsDBError(f"unexpected answer for {call}")
        if len(self._cache) > 300:                      # most calls are asked once (one game, one date): drop the expired
            now = monotonic()
            self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
        self._cache[cache_key] = (monotonic() + CACHE_SECONDS, data)
        return data

    async def search_teams(self, key: str, name: str) -> list[dict[str, Any]]:
        """Teams whose name matches, in every sport."""
        data = await self._get(key, f"searchteams.php?t={quote(name)}")
        return data.get("teams") or []

    async def lookup_team(self, key: str, team_id: str) -> dict[str, Any] | None:
        data = await self._get(key, f"lookupteam.php?id={quote(team_id)}")
        teams = data.get("teams") or []
        return teams[0] if teams else None

    async def next_events(self, key: str, team_id: str) -> list[dict[str, Any]]:
        """The team's next fixtures, home or away (the free key gives one)."""
        data = await self._get(key, f"eventsnext.php?id={quote(team_id)}")
        return data.get("events") or []

    async def last_events(self, key: str, team_id: str) -> list[dict[str, Any]]:
        """The team's latest results (the free key gives the last home game only)."""
        data = await self._get(key, f"eventslast.php?id={quote(team_id)}")
        return data.get("results") or []

    async def lookup_event(self, key: str, event_id: str) -> dict[str, Any] | None:
        """One game by id: this is how an away result is read on the free key."""
        data = await self._get(key, f"lookupevent.php?id={quote(event_id)}")
        events = data.get("events") or []
        return events[0] if events else None

    async def lookup_tv(self, key: str, event_id: str) -> list[dict[str, Any]]:
        """Who broadcasts a game, in every country TheSportsDB knows (the free key returns two)."""
        data = await self._get(key, f"lookuptv.php?id={quote(event_id)}")
        return data.get("tvevent") or data.get("tvevents") or []

    async def lookup_timeline(self, key: str, event_id: str) -> list[dict[str, Any]]:
        """A game's events: goals, cards, substitutions (the free key returns the first five)."""
        data = await self._get(key, f"lookuptimeline.php?id={quote(event_id)}")
        return data.get("timeline") or []

    async def events_day(self, key: str, day: str, sport: str) -> list[dict[str, Any]]:
        """Every game of a sport on a date (YYYY-MM-DD): a premium key returns all of them, the free key a few."""
        data = await self._get(key, f"eventsday.php?d={quote(day)}&s={quote(sport)}")
        return data.get("events") or []
