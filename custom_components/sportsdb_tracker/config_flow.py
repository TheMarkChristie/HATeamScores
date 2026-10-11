"""Setup: search TheSportsDB for a team, pick it, name the sensor. Options: the key and the timing."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import SelectOptionDict, SelectSelector, SelectSelectorConfig, SelectSelectorMode
from homeassistant.util import slugify

from .api import SportsDBError, get_client
from .const import (
    CONF_API_KEY,
    CONF_LEAGUE,
    CONF_PRE_HOURS,
    CONF_PREFIX,
    CONF_RESULTS_HOURS,
    CONF_SPORT,
    CONF_TEAM_ID,
    CONF_TEAM_NAME,
    DEFAULT_API_KEY,
    DEFAULT_PRE_HOURS,
    DEFAULT_RESULTS_HOURS,
    DOMAIN,
    SPORT_LABEL,
)
from .model import Team, prefix_for_sport

ANY_SPORT = "any"
SPORTS = ["Soccer", "Ice Hockey", "American Football", "Basketball", "Rugby", "Baseball", "Cricket", "Australian Football",
          "Handball", "Volleyball", "Field Hockey", "Netball", "Lacrosse", "ESports"]


def _sport_options() -> list[SelectOptionDict]:
    return [SelectOptionDict(value=ANY_SPORT, label="Any sport")] + [
        SelectOptionDict(value=s, label=SPORT_LABEL.get(s, s)) for s in SPORTS]


class SportsDBConfigFlow(ConfigFlow, domain=DOMAIN):
    """Search, pick, name."""

    VERSION = 1

    def __init__(self) -> None:
        self._api_key = DEFAULT_API_KEY
        self._search = ""
        self._teams: dict[str, Team] = {}
        self._team: Team | None = None

    def _default_key(self) -> str:
        for entry in self._async_current_entries():
            key = entry.options.get(CONF_API_KEY) or entry.data.get(CONF_API_KEY)
            if key:
                return str(key)
        return DEFAULT_API_KEY

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._api_key = str(user_input.get(CONF_API_KEY) or DEFAULT_API_KEY).strip() or DEFAULT_API_KEY
            self._search = str(user_input.get("search") or "").strip()
            sport = user_input.get("sport") or ANY_SPORT
            if not self._search:
                errors["search"] = "no_teams"
            else:
                try:
                    raws = await get_client(self.hass).search_teams(self._api_key, self._search)
                except SportsDBError:
                    errors["base"] = "cannot_connect"
                else:
                    teams = [Team.parse(r) for r in raws if r.get("idTeam")]
                    if sport != ANY_SPORT:
                        teams = [t for t in teams if t.sport == sport]
                    if not teams:
                        errors["search"] = "no_teams"
                    else:
                        self._teams = {t.id: t for t in teams}
                        return await self.async_step_pick()
        schema = vol.Schema({
            vol.Required("search", default=self._search): str,
            vol.Optional("sport", default=ANY_SPORT): SelectSelector(
                SelectSelectorConfig(options=_sport_options(), mode=SelectSelectorMode.DROPDOWN)),
            vol.Optional(CONF_API_KEY, default=self._default_key()): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_pick(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None and user_input.get("team") in self._teams:
            team = self._teams[user_input["team"]]
            await self.async_set_unique_id(f"{DOMAIN}_{team.id}")
            self._abort_if_unique_id_configured()
            self._team = team
            return await self.async_step_name()
        options = []
        for t in self._teams.values():
            parts = [SPORT_LABEL.get(t.sport, t.sport) or "sport unknown", t.league or "no league"]
            if t.gender and t.gender != "Male":
                parts.append(t.gender)
            options.append(SelectOptionDict(value=t.id, label=f"{t.name} ({', '.join(parts)})"))
        schema = vol.Schema({vol.Required("team"): SelectSelector(SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST))})
        return self.async_show_form(step_id="pick", data_schema=schema,
                                    description_placeholders={"count": str(len(options)), "search": self._search})

    async def async_step_name(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        team = self._team
        assert team is not None
        prefix = prefix_for_sport(team.sport)
        if user_input is not None:
            name = str(user_input.get("name") or "").strip() or team.name
            return self.async_create_entry(
                title=name,
                data={CONF_API_KEY: self._api_key, CONF_TEAM_ID: team.id, CONF_TEAM_NAME: team.name, CONF_SPORT: team.sport,
                      CONF_LEAGUE: team.league, CONF_PREFIX: prefix},
                options={CONF_RESULTS_HOURS: DEFAULT_RESULTS_HOURS, CONF_PRE_HOURS: DEFAULT_PRE_HOURS},
            )
        schema = vol.Schema({vol.Required("name", default=team.name): str})
        return self.async_show_form(step_id="name", data_schema=schema, description_placeholders={
            "team": team.name, "league": team.league or "no league", "sport": SPORT_LABEL.get(team.sport, team.sport),
            "entity_id": f"sensor.{prefix}_{slugify(team.name)}"})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SportsDBOptionsFlow()


class SportsDBOptionsFlow(OptionsFlow):
    """The key, how long a result stays, and when the next fixture takes over."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            user_input[CONF_API_KEY] = str(user_input.get(CONF_API_KEY) or DEFAULT_API_KEY).strip() or DEFAULT_API_KEY
            return self.async_create_entry(title="", data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema({
            vol.Optional(CONF_API_KEY, default=current.get(CONF_API_KEY) or DEFAULT_API_KEY): str,
            vol.Optional(CONF_RESULTS_HOURS, default=int(current.get(CONF_RESULTS_HOURS, DEFAULT_RESULTS_HOURS))):
                vol.All(vol.Coerce(int), vol.Range(min=0, max=168)),
            vol.Optional(CONF_PRE_HOURS, default=int(current.get(CONF_PRE_HOURS, DEFAULT_PRE_HOURS))):
                vol.All(vol.Coerce(int), vol.Range(min=0, max=72)),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
