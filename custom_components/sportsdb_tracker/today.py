"""Today on TV: every game of the day, in any league, that a UK or Norwegian channel shows live, for the card's
"On TV today" button. Asked for by the card over Home Assistant's websocket (sportsdb_tracker/tv_today), worked out
from the TV guides already downloaded for the fixtures and TheSportsDB's games of the day (cached for two hours).

The day is the viewer's: the card sends its date and time zone, so the list and the card's TODAY panel are the same day
on a phone in Scotland and a tablet in Norway. The games of the day need a premium TheSportsDB key for the full list
(the free key returns a handful); the key is taken from any team that has one. A sport that could not be read is
asked again after five minutes, the last good list is used meanwhile, and the answer names it."""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from time import monotonic
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .api import SportsDBError, get_client
from .const import CONF_API_KEY, DEFAULT_API_KEY, DEFAULT_TV, DOMAIN, STREAMS, TODAY_CACHE_HOURS, TODAY_SPORTS
from .guide import get_guide
from .streams import missing_from, stream_games
from .tv import today_on_tv, utc_dates

_LOGGER = logging.getLogger(__name__)
FAILED_RETRY_SECONDS = 300
STREAM_CACHE_SECONDS = 900
STREAM_HEADERS = {"Accept": "application/json", "User-Agent": "Mozilla/5.0 (Home Assistant; Team Scores)"}


def _key(hass: HomeAssistant) -> str:
    for entry in hass.config_entries.async_entries(DOMAIN):
        key = str(entry.options.get(CONF_API_KEY) or entry.data.get(CONF_API_KEY) or "").strip()
        if key and key != DEFAULT_API_KEY:
            return key
    return DEFAULT_API_KEY


class TodayStore:
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        # (UTC date, sport) -> (good until, games, read cleanly)
        self._days: dict[tuple[str, str], tuple[float, list[dict[str, Any]], bool]] = {}
        # stream key -> (good until, its games)
        self._streams: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    async def _stream_games(self) -> list[dict[str, Any]]:
        """The club streams' games (streams.py), each feed read at most every 15 minutes; one that cannot be read keeps
        its last games and is asked again in five."""
        out: list[dict[str, Any]] = []
        for stream in STREAMS:
            hit = self._streams.get(stream["key"])
            if hit and monotonic() < hit[0]:
                out += hit[1]
                continue
            try:
                async with async_get_clientsession(self._hass).get(
                        stream["url"], headers=STREAM_HEADERS, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    resp.raise_for_status()
                    feed = await resp.json(content_type=None)
                games = stream_games(feed if isinstance(feed, dict) else None, stream)
                self._streams[stream["key"]] = (monotonic() + STREAM_CACHE_SECONDS, games)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
                _LOGGER.info("%s's schedule not read (%s); asking again in five minutes", stream["channel"], err)
                games = hit[1] if hit else []
                self._streams[stream["key"]] = (monotonic() + FAILED_RETRY_SECONDS, games)
            out += games
        return out

    async def _events(self, key: str, days: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
        client = get_client(self._hass)
        out: list[dict[str, Any]] = []
        failed: list[str] = []
        for stale in [k for k in self._days if k[0] not in days]:       # only the dates of the current listing are kept
            self._days.pop(stale, None)
        for day in days:
            for sport in TODAY_SPORTS:
                hit = self._days.get((day, sport))
                if hit and monotonic() < hit[0]:
                    got, clean = hit[1], hit[2]
                else:
                    try:
                        got, clean = await client.events_day(key, day, sport), True
                        self._days[(day, sport)] = (monotonic() + TODAY_CACHE_HOURS * 3600, got, True)
                    except SportsDBError as err:
                        _LOGGER.info("On TV today: %s on %s not read (%s); asking again in five minutes", sport, day, err)
                        got, clean = (hit[1] if hit else []), False            # the last good list, when there is one
                        self._days[(day, sport)] = (monotonic() + FAILED_RETRY_SECONDS, got, False)
                if not clean and sport not in failed:
                    failed.append(sport)
                out += got
        return out, failed

    async def listing(self, day: date | None = None, tz_name: str | None = None) -> dict[str, Any]:
        tz = (dt_util.get_time_zone(tz_name) if tz_name else None) or dt_util.get_default_time_zone()
        today = day or dt_util.now(tz).date()
        programmes = get_guide(self._hass).programmes()
        if not programmes:
            return {"day": today.isoformat(), "games": [], "status": "guides_loading"}
        key = _key(self._hass)
        events, failed = await self._events(key, utc_dates(today, tz))
        # and the club streams' games TheSportsDB does not have (Glasgow Clan's Challenge Cup games on Clan TV)
        events = events + missing_from(await self._stream_games(), events)
        games = await self._hass.async_add_executor_job(today_on_tv, events, programmes, today, tz, DEFAULT_TV, dt_util.utcnow())
        return {"day": today.isoformat(), "games": games, "status": "ok", "premium": key != DEFAULT_API_KEY,
                "failed": failed}


def get_today(hass: HomeAssistant) -> TodayStore:
    shared = hass.data.setdefault(DOMAIN, {})
    if "today" not in shared:
        shared["today"] = TodayStore(hass)
    return shared["today"]


@websocket_api.websocket_command({
    vol.Required("type"): "sportsdb_tracker/tv_today",
    vol.Optional("day"): vol.All(str, vol.Match(r"^\d{4}-\d{2}-\d{2}$")),
    vol.Optional("time_zone"): vol.All(str, vol.Length(max=64)),
})
@websocket_api.async_response
async def ws_tv_today(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    day = None
    if msg.get("day"):
        try:
            day = date.fromisoformat(msg["day"])
        except ValueError:
            day = None
    connection.send_result(msg["id"], await get_today(hass).listing(day, msg.get("time_zone")))


@callback
def async_register(hass: HomeAssistant) -> None:
    if not hass.data.setdefault(DOMAIN, {}).get("ws_today"):
        websocket_api.async_register_command(hass, ws_tv_today)
        hass.data[DOMAIN]["ws_today"] = True
