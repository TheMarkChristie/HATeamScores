"""Today on TV: every game of the day, in any league, that a UK or Norwegian channel shows live, for the card's
"On TV today" button. Asked for by the card over Home Assistant's websocket (sportsdb_tracker/tv_today), worked out
from the TV guides already downloaded for the fixtures and TheSportsDB's games of the day (cached for two hours).

The games of the day need a premium TheSportsDB key for the full list (the free key returns a handful); the key is
taken from any team that has one."""
from __future__ import annotations

import logging
from datetime import timedelta
from time import monotonic
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .api import SportsDBError, get_client
from .const import CONF_API_KEY, DEFAULT_API_KEY, DOMAIN, TODAY_CACHE_HOURS, TODAY_SPORTS
from .guide import get_guide
from .tv import today_on_tv

_LOGGER = logging.getLogger(__name__)


def _key(hass: HomeAssistant) -> str:
    for entry in hass.config_entries.async_entries(DOMAIN):
        key = str(entry.options.get(CONF_API_KEY) or entry.data.get(CONF_API_KEY) or "").strip()
        if key and key != DEFAULT_API_KEY:
            return key
    return DEFAULT_API_KEY


class TodayStore:
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._days: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}

    async def _events(self, key: str, days: list[str]) -> list[dict[str, Any]]:
        client = get_client(self._hass)
        out: list[dict[str, Any]] = []
        for day in days:
            for sport in TODAY_SPORTS:
                hit = self._days.get((day, sport))
                if hit and monotonic() < hit[0]:
                    out += hit[1]
                    continue
                try:
                    got = await client.events_day(key, day, sport)
                except SportsDBError as err:
                    _LOGGER.debug("games of %s (%s) not read: %s", day, sport, err)
                    got = hit[1] if hit else []
                self._days[(day, sport)] = (monotonic() + TODAY_CACHE_HOURS * 3600, got)
                out += got
        return out

    async def listing(self) -> dict[str, Any]:
        tz = dt_util.get_default_time_zone()
        today = dt_util.now().date()
        programmes = get_guide(self._hass).programmes()
        if not programmes:
            return {"day": today.isoformat(), "games": [], "status": "guides_loading"}
        key = _key(self._hass)
        # a local day spans two UTC dates (TheSportsDB files games by UTC date)
        events = await self._events(key, [(today - timedelta(days=1)).isoformat(), today.isoformat()])
        games = await self._hass.async_add_executor_job(today_on_tv, events, programmes, today, tz)
        return {"day": today.isoformat(), "games": games, "status": "ok", "premium": key != DEFAULT_API_KEY}


def get_today(hass: HomeAssistant) -> TodayStore:
    shared = hass.data.setdefault(DOMAIN, {})
    if "today" not in shared:
        shared["today"] = TodayStore(hass)
    return shared["today"]


@websocket_api.websocket_command({vol.Required("type"): "sportsdb_tracker/tv_today"})
@websocket_api.async_response
async def ws_tv_today(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    connection.send_result(msg["id"], await get_today(hass).listing())


@callback
def async_register(hass: HomeAssistant) -> None:
    if not hass.data.setdefault(DOMAIN, {}).get("ws_today"):
        websocket_api.async_register_command(hass, ws_tv_today)
        hass.data[DOMAIN]["ws_today"] = True
