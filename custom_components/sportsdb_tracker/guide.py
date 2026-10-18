"""The UK and Norwegian TV guides, shared by every team: downloaded in the background every few hours, read once in the
executor, kept as the programmes that look like games. One copy per Home Assistant, so twenty teams cost one round of
downloads, and nothing waits for them: a team reads whatever copy is there, and the channels a refresh finds reach the
sensors on each team's next update.

  UK      epgshare01's XMLTV file (one download; asked with If-None-Match / If-Modified-Since, so an unchanged file is
          not sent again)
  Norway  Allente's guide, one JSON file per day for the next ALLENTE_DAYS days: today and tomorrow on every refresh,
          the later days once a day

The programmes are kept sorted by start, so a fixture's channels are matched against the few programmes around its
kick-off (window), not the whole guide.
"""
from __future__ import annotations

import asyncio
import logging
from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta
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
LATER_DAYS_HOURS = 24          # Allente's days after tomorrow are fetched again after this long


def get_guide(hass: HomeAssistant) -> "GuideStore":
    shared = hass.data.setdefault(DOMAIN, {})
    if "guide" not in shared:
        shared["guide"] = GuideStore(hass)
    return shared["guide"]


class GuideStore:
    """The guides' game-like programmes, by country; a failed download keeps that country's last good copy."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._uk: list[Programme] = []
        self._uk_validators: dict[str, str] = {}
        self._no_days: dict[str, tuple[float, list[Programme]]] = {}    # day -> (fetched at, its programmes)
        self._sorted: list[Programme] = []
        self._starts: list[datetime] = []
        self._next_at = 0.0
        self._running = False
        self._listeners: set = set()

    def add_listener(self, coordinator) -> callable:
        """A team to refresh as soon as a download finishes, so new channels show without waiting for its next update."""
        self._listeners.add(coordinator)
        return lambda: self._listeners.discard(coordinator)

    def _due(self) -> None:
        if not self._running and monotonic() >= self._next_at:
            self._running = True
            self._hass.async_create_background_task(self._refresh(), name="sportsdb_tracker TV guides")

    def programmes(self) -> list[Programme]:
        """What is loaded now, sorted by start; starts a refresh in the background when the copy is due one."""
        self._due()
        return self._sorted

    def window(self, start_from: datetime, start_by: datetime) -> list[Programme]:
        """The programmes starting between the two times (both included), from the sorted copy."""
        self._due()
        return self._sorted[bisect_left(self._starts, start_from):bisect_right(self._starts, start_by)]

    def _rebuild(self) -> None:
        seen: set[tuple[str, str]] = set()
        merged: list[Programme] = list(self._uk)
        for _at, progs in sorted(self._no_days.values(), key=lambda v: v[0]):
            for p in progs:
                k = (p.channel, p.start.isoformat())             # a programme on a day's edge comes in both files
                if k not in seen:
                    seen.add(k)
                    merged.append(p)
        merged.sort(key=lambda p: p.start)
        self._sorted = merged
        self._starts = [p.start for p in merged]

    async def _uk_refresh(self, now: datetime) -> None:
        session = async_get_clientsession(self._hass)
        headers = dict(HEADERS)
        if self._uk and (etag := self._uk_validators.get("etag")):
            headers["If-None-Match"] = etag
        if self._uk and (modified := self._uk_validators.get("last_modified")):
            headers["If-Modified-Since"] = modified
        async with session.get(GUIDE_UK_URL, timeout=TIMEOUT, headers=headers) as resp:
            if resp.status == 304:
                _LOGGER.debug("UK TV guide unchanged")
                return
            if resp.status != 200:
                raise aiohttp.ClientResponseError(resp.request_info, resp.history, status=resp.status)
            data = await resp.read()
            self._uk_validators = {k: v for k, v in (("etag", resp.headers.get("ETag")),
                                                     ("last_modified", resp.headers.get("Last-Modified"))) if v}
        self._uk = await self._hass.async_add_executor_job(parse_xmltv, data, "UK", now)

    async def _no_refresh(self, now: datetime) -> None:
        session = async_get_clientsession(self._hass)
        local = dt_util.as_local(now)
        wanted = [(local + timedelta(days=i)).date().isoformat() for i in range(ALLENTE_DAYS)]
        for i, day in enumerate(wanted):
            hit = self._no_days.get(day)
            if i >= 2 and hit and monotonic() - hit[0] < LATER_DAYS_HOURS * 3600:
                continue                                         # a later day changes little; once a day is enough
            async with session.get(ALLENTE_URL.format(day=day), timeout=TIMEOUT, headers=HEADERS) as resp:
                if resp.status != 200:
                    raise aiohttp.ClientResponseError(resp.request_info, resp.history, status=resp.status)
                data = await resp.read()
            self._no_days[day] = (monotonic(), await self._hass.async_add_executor_job(parse_allente, [data], now))
        for day in [d for d in self._no_days if d not in wanted]:
            self._no_days.pop(day, None)

    async def _refresh(self) -> None:
        failed = False
        now = dt_util.utcnow()
        try:
            try:
                await self._uk_refresh(now)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, SyntaxError, OSError, EOFError) as err:
                _LOGGER.warning("UK TV guide not read (%s); keeping the last copy", err)
                failed = True
            try:
                await self._no_refresh(now)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, OSError) as err:
                _LOGGER.warning("Norwegian TV guide not read (%s); keeping the last copy", err)
                failed = True
            self._rebuild()
            _LOGGER.debug("TV guides: UK %d, NO %d programmes", len(self._uk), sum(len(v[1]) for v in self._no_days.values()))
        finally:
            wait = GUIDE_RETRY_MINUTES * 60 if failed else GUIDE_REFRESH_HOURS * 3600
            self._next_at = monotonic() + wait
            self._running = False
        for coordinator in list(self._listeners):
            self._hass.async_create_task(coordinator.async_request_refresh())
