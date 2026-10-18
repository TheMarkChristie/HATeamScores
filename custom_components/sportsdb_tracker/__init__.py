"""TheSportsDB Tracker: a team's next fixture and full-time result from TheSportsDB, one sensor per team, and the
Team Scores card that lays every team's games out by day."""
from __future__ import annotations

import hashlib
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .api import get_client
from .card_resource import async_remove_card_resource, async_schedule_card_resource
from .const import CARD_FILE, DOMAIN, STORAGE_VERSION, URL_BASE
from .coordinator import SportsDBCoordinator
from .guide import get_guide

PLATFORMS = [Platform.SENSOR]
_STATIC_REGISTERED = f"{DOMAIN}_static_registered"
_CARD_URL = f"{DOMAIN}_card_url"

type SportsDBConfigEntry = ConfigEntry[SportsDBCoordinator]


def _card_hash() -> str:
    try:
        return hashlib.sha256((Path(__file__).parent / "www" / CARD_FILE).read_bytes()).hexdigest()[:10]
    except OSError:
        return "0"


async def _card_url(hass: HomeAssistant) -> str:
    """The card's URL with a version and a hash of the file, so a changed card is never served from a browser cache."""
    if url := hass.data.get(_CARD_URL):
        return url
    integration = await async_get_integration(hass, DOMAIN)
    digest = await hass.async_add_executor_job(_card_hash)
    url = f"{URL_BASE}/{CARD_FILE}?v={integration.version}-{digest}"
    hass.data[_CARD_URL] = url
    return url


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the card and put it in front of every dashboard; once per run."""
    if not hass.data.get(_STATIC_REGISTERED):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(URL_BASE, str(Path(__file__).parent / "www"), cache_headers=False)])
        hass.data[_STATIC_REGISTERED] = True
    url = await _card_url(hass)
    frontend.add_extra_js_url(hass, url)
    async_schedule_card_resource(hass, url)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SportsDBConfigEntry) -> bool:
    coordinator = SportsDBCoordinator(hass, entry, get_client(hass))
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_changed))
    entry.async_on_unload(get_guide(hass).add_listener(coordinator))      # new channels as soon as a guide download lands
    return True


async def _async_options_changed(hass: HomeAssistant, entry: SportsDBConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SportsDBConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """The team was removed: drop its stored fixtures; with the last team, the card's dashboard resource too."""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()
    if not [e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id]:
        frontend.remove_extra_js_url(hass, await _card_url(hass))
        await async_remove_card_resource(hass)
