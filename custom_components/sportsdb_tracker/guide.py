"""The UK and Norwegian TV guides, shared by every team: downloaded in the background every few hours, read once in the
executor, kept as the programmes that look like games. One copy per Home Assistant, so twenty teams cost two
downloads, and nothing waits for them: a team reads whatever copy is there, and the channels a refresh finds reach the
sensors on each team's next update."""
from __future__ import annotations

import asyncio
import logging
from time import monotonic

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import DOMAIN, GUIDE_REFRESH_HOURS, GUIDE_RETRY_MINUTES, GUIDE_URLS
from .tv import Programme, parse_guide

_LOGGER = logging.getLogger(__name__)
TIMEOUT = aiohttp.ClientTimeout(total=90)


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

    async def _refresh(self) -> None:
        session = async_get_clientsession(self._hass)
        failed = False
        try:
            for country, url in GUIDE_URLS.items():
                try:
                    async with session.get(url, timeout=TIMEOUT) as resp:
                        if resp.status != 200:
                            raise aiohttp.ClientResponseError(resp.request_info, resp.history, status=resp.status)
                        data = await resp.read()
                    got = await self._hass.async_add_executor_job(parse_guide, data, country, dt_util.utcnow())
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, SyntaxError, OSError) as err:
                    _LOGGER.warning("TV guide for %s not read (%s); keeping the last copy", country, err)
                    failed = True
                    continue
                self._by_country[country] = got
                _LOGGER.debug("TV guide for %s: %d programmes that look like games", country, len(got))
        finally:
            wait = GUIDE_RETRY_MINUTES * 60 if failed else GUIDE_REFRESH_HOURS * 3600
            self._next_at = monotonic() + wait
            self._running = False
