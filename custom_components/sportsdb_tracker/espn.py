"""ESPN's public scores service, for who scored: one shared, paced client per Home Assistant, with a short cache.

Only two calls are used: a competition's scoreboard for a date (to find the game) and the game's summary (its goals).
A finished game's summary never changes, so it is kept for a day; a live one for two minutes.
"""
from __future__ import annotations

import asyncio
import logging
from time import monotonic
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
BASE = "https://site.api.espn.com/apis/site/v2/sports"
TIMEOUT = aiohttp.ClientTimeout(total=25)
INTERVAL = 1.0                       # seconds between requests: ESPN states no limit; this keeps it polite
HEADERS = {"User-Agent": "HATeamScores (Home Assistant; github.com/TheMarkChristie/HATeamScores)", "Accept": "application/json"}


class EspnError(Exception):
    """ESPN did not answer, or answered with something that is not a scores document."""


def get_espn(hass: HomeAssistant) -> "EspnClient":
    shared = hass.data.setdefault(DOMAIN, {})
    if "espn" not in shared:
        shared["espn"] = EspnClient(async_get_clientsession(hass))
    return shared["espn"]


class EspnClient:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._lock = asyncio.Lock()
        self._next_at = 0.0
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    async def _get(self, path: str, keep_seconds: float) -> dict[str, Any]:
        hit = self._cache.get(path)
        if hit and monotonic() < hit[0]:
            return hit[1]
        async with self._lock:
            hit = self._cache.get(path)                 # an identical request queued ahead of this one may have answered it
            if hit and monotonic() < hit[0]:
                return hit[1]
            wait = self._next_at - monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                async with self._session.get(f"{BASE}/{path}", timeout=TIMEOUT, headers=HEADERS) as resp:
                    if resp.status != 200:
                        raise EspnError(f"HTTP {resp.status} for {path}")
                    data = await resp.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
                raise EspnError(f"{type(err).__name__}: {err}") from err
            finally:
                self._next_at = monotonic() + INTERVAL
        if not isinstance(data, dict):
            raise EspnError(f"unexpected answer for {path}")
        if len(self._cache) > 200:                      # drop the expired, not everything
            now = monotonic()
            self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
        self._cache[path] = (monotonic() + keep_seconds, data)
        return data

    async def scoreboard(self, slug: str, day: str) -> dict[str, Any]:
        """A competition's games on a date (YYYYMMDD, US Eastern)."""
        return await self._get(f"{slug}/scoreboard?dates={day}", 600)

    async def summary(self, slug: str, event_id: str, final: bool) -> dict[str, Any]:
        return await self._get(f"{slug}/summary?event={event_id}", 86400 if final else 120)
