"""The UK and Norwegian TV guides, shared by every team: downloaded in the background every few hours, read once in the
executor, kept as the programmes that look like games. One copy per Home Assistant, so twenty teams cost one round of
downloads, and nothing waits for them: a team reads whatever copy is there, and the channels a refresh finds reach the
sensors on each team's next update.

  UK      epgshare01's XMLTV file (one download)
  Norway  Allente's guide, one JSON file per day for the next ALLENTE_DAYS days
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from time import monotonic

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import ALLENTE_DAYS, ALLENTE_URL, DOMAIN, GUIDE_REFRESH_HOURS, GUIDE_RETRY_MINUTES, GUIDE_UK_URL
from .tv import Programme, parse_allente, parse_xmltv

_LOGGER = logging.getLogger(__name__)
TIMEOUT = aiohttp.ClientTimeout(total=90)
HEADERS = {"User-Agent": "HATeamScores (Home Assistant; github.com/TheMarkChristie/HATeamScores)"}


def get_guide(hass: HomeAssistant) -> "GuideStore":
    shared = hass.data.setdefault(DOMAIN, {})
    if "guide" not in shared:
        shared["guide"] = GuideStore(hass)
    return shared["guide"]


class GuideStore:
    """The guides' game-like programmes, by country; a failed download keeps that country's last good copy."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._by_country: dict[str, list[Programme]] = {}
        self._next_at = 0.0
        self._running = False

    def programmes(self) -> list[Programme]:
        """What is loaded now; starts a refresh in the background when the copy is due one."""
        if not self._running and monotonic() >= self._next_at:
            self._running = True
            self._hass.async_create_background_task(self._refresh(), name="sportsdb_tracker TV guides")
        return [p for lst in self._by_country.values() for p in lst]

    async def _get(self, url: str) -> bytes:
        session = async_get_clientsession(self._hass)
        async with session.get(url, timeout=TIMEOUT, headers=HEADERS) as resp:
            if resp.status != 200:
                raise aiohttp.ClientResponseError(resp.request_info, resp.history, status=resp.status)
            return await resp.read()

    async def _refresh(self) -> None:
        failed = False
        now = dt_util.utcnow()
        try:
            try:
                data = await self._get(GUIDE_UK_URL)
                self._by_country["UK"] = await self._hass.async_add_executor_job(parse_xmltv, data, "UK", now)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, SyntaxError, OSError) as err:
                _LOGGER.warning("UK TV guide not read (%s); keeping the last copy", err)
                failed = True
            days: list[bytes] = []
            try:
                for i in range(ALLENTE_DAYS):
                    day = (dt_util.as_local(now) + timedelta(days=i)).date().isoformat()
                    days.append(await self._get(ALLENTE_URL.format(day=day)))
                self._by_country["NO"] = await self._hass.async_add_executor_job(parse_allente, days, now)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, OSError) as err:
                _LOGGER.warning("Norwegian TV guide not read (%s); keeping the last copy", err)
                failed = True
            _LOGGER.debug("TV guides: %s", {k: len(v) for k, v in self._by_country.items()})
        finally:
            wait = GUIDE_RETRY_MINUTES * 60 if failed else GUIDE_REFRESH_HOURS * 3600
            self._next_at = monotonic() + wait
            self._running = False
