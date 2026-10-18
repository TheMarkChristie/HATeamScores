"""One sensor per team: PRE with the next fixture, IN while the game is on, POST with the full-time result."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util, slugify

from .const import ATTRIBUTION, CONF_PREFIX, CONF_TEAM_ID, CONF_TEAM_NAME, DEFAULT_ICON, DOMAIN, SPORT_ICON
from .coordinator import SportsDBCoordinator
from .model import TEAM_URL, present


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator: SportsDBCoordinator = entry.runtime_data
    async_add_entities([TeamSensor(coordinator, entry)])


class TeamSensor(CoordinatorEntity[SportsDBCoordinator], SensorEntity):
    """The team's game, in the shape the scoreboard card reads."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = False
    _unrecorded_attributes = frozenset({"fixtures", "results", "last_update", "next_game", "last_game", "tv"})  # not history

    def __init__(self, coordinator: SportsDBCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        team = coordinator.team
        team_id = str(entry.data[CONF_TEAM_ID])
        object_id = f"{entry.data.get(CONF_PREFIX) or 'sports'}_{slugify(entry.data.get(CONF_TEAM_NAME) or entry.title)}"
        self._attr_unique_id = f"{DOMAIN}_{team_id}"
        self._attr_name = entry.title
        self._attr_suggested_object_id = object_id
        self.entity_id = f"sensor.{object_id}"
        self._attr_icon = SPORT_ICON.get(team.sport, DEFAULT_ICON)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, team_id)}, name=team.name, manufacturer="TheSportsDB",
            model=team.league or team.sport or None, entry_type=DeviceEntryType.SERVICE,
            configuration_url=TEAM_URL.format(id=team_id))

    def _present(self) -> tuple[str, dict[str, Any]]:
        c = self.coordinator
        return present(c.team, c.data or c.memory, dt_util.utcnow(), c.results_hours, c.pre_hours, dt_util.as_local)

    @property
    def native_value(self) -> str:
        return self._present()[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._present()[1]

    @property
    def entity_picture(self) -> str | None:
        return self.coordinator.team.badge
