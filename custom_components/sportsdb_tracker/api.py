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

from .const import API_BASE, DEFAULT_API_KEY, FREE_MIN_INTERVAL, PREMIUM_MIN_INTERVAL

_LOGGER = logging.getLogger(__name__)
TIMEOUT = aiohttp.ClientTimeout(total=25)
CACHE_SECONDS = 60
BACKOFF_SECONDS = 30                      # after a 429, nothing is sent for this long


class SportsDBError(Exception):
    """TheSportsDB did not answer, answered with an error, or sent something that is not JSON."""


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
        async with self._lock:
            wait = self._next_at - monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            interval = FREE_MIN_INTERVAL if key == DEFAULT_API_KEY else PREMIUM_MIN_INTERVAL
            try:
                async with self._session.get(url, timeout=TIMEOUT, headers={"Accept": "application/json"}) as resp:
                    if resp.status == 429:
                        self._next_at = monotonic() + BACKOFF_SECONDS
                        raise SportsDBError("rate limit reached (HTTP 429)")
                    if resp.status != 200:
                        raise SportsDBError(f"HTTP {resp.status} for {call}")
                    data = await resp.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise SportsDBError(f"{type(err).__name__}: {err}") from err
            finally:
                if monotonic() + interval > self._next_at:
                    self._next_at = monotonic() + interval
        if not isinstance(data, dict):
            raise SportsDBError(f"unexpected answer for {call}")
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
