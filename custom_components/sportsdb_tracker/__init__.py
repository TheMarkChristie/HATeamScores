"""TheSportsDB Tracker: a team's next fixture and full-time result from TheSportsDB, one sensor per team."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .api import get_client
from .const import DOMAIN, STORAGE_VERSION
from .coordinator import SportsDBCoordinator

PLATFORMS = [Platform.SENSOR]

type SportsDBConfigEntry = ConfigEntry[SportsDBCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SportsDBConfigEntry) -> bool:
    coordinator = SportsDBCoordinator(hass, entry, get_client(hass))
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_changed))
    return True


async def _async_options_changed(hass: HomeAssistant, entry: SportsDBConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: SportsDBConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """The team was removed: drop its stored fixtures too."""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()
