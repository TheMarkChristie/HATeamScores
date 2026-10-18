"""Open a channel's app on a TV for the Team Scores card: tap a channel, choose the device, the app opens there.

The devices offered by default are the house's Google Cast devices (Mark, 18 Oct 2026: "Google chromecasts should be the
default options for casting or apps"). A Cast device cannot start an Android app by its package name, so the app is
opened through the Android Debug Bridge (core androidtv integration) on the same box: the bridge on the same device, or
whose device has the same name as the chosen one, or the same network MAC. Without a bridge an Android TV Remote entity
is asked instead (Google TV boxes reject packages that way since a Play Store change; links can still work); anything
else cannot open apps and says so.

    service  sportsdb_tracker.open_app   device: <entity>, app: <package or link>, name: <app name for messages>
    command  sportsdb_tracker/devices    -> {"devices": [{entity_id, name, available, apps}]}   the Cast devices
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr, entity_registry as er

from .apps import WAKE, not_installed, open_commands, opened, valid_app
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
SERVICE_OPEN_APP = "open_app"
_LOCKS = f"{DOMAIN}_launch_locks"

OPEN_APP_SCHEMA = vol.Schema({
    vol.Required("device"): cv.entity_id,
    vol.Required("app"): vol.All(cv.string, vol.Length(max=300)),
    vol.Optional("name"): vol.All(cv.string, vol.Length(max=80)),
    vol.Optional("package"): vol.All(cv.string, vol.Length(max=120)),       # the app a link must open in
})


def _device_name(hass: HomeAssistant, entity_id: str) -> str:
    reg = er.async_get(hass)
    entry = reg.async_get(entity_id)
    if entry and entry.device_id and (device := dr.async_get(hass).async_get(entry.device_id)):
        return device.name_by_user or device.name or entity_id
    state = hass.states.get(entity_id)
    return state.name if state else entity_id


def _macs(hass: HomeAssistant, device_id: str | None) -> set[str]:
    device = dr.async_get(hass).async_get(device_id) if device_id else None
    return {v.lower() for k, v in (device.connections if device else set()) if k == dr.CONNECTION_NETWORK_MAC}


def _bridge_for(hass: HomeAssistant, entity_id: str) -> str | None:
    """The Android Debug Bridge media player for the box the entity belongs to, if there is one."""
    reg = er.async_get(hass)
    chosen = reg.async_get(entity_id)
    bridges = [e for e in reg.entities.values()
               if e.platform == "androidtv" and e.domain == "media_player" and not e.disabled_by]
    if not bridges:
        return None
    if chosen and chosen.platform == "androidtv":                     # the bridge itself, or its remote entity
        same = [b for b in bridges if b.device_id and b.device_id == chosen.device_id]
        if same:
            return same[0].entity_id
        return chosen.entity_id if chosen.domain == "media_player" else None
    name = _device_name(hass, entity_id).casefold()
    macs = _macs(hass, chosen.device_id if chosen else None)
    for b in bridges:
        if (chosen and b.device_id and b.device_id == chosen.device_id) or _device_name(hass, b.entity_id).casefold() == name \
                or (macs and macs & _macs(hass, b.device_id)):
            return b.entity_id
    return None


def cast_devices(hass: HomeAssistant) -> list[dict[str, Any]]:
    """The Google Cast media players, with whether each can open apps (it has a bridge)."""
    out = []
    for e in er.async_get(hass).entities.values():
        if e.platform != "cast" or e.domain != "media_player" or e.disabled_by:
            continue
        state = hass.states.get(e.entity_id)
        out.append({"entity_id": e.entity_id, "name": _device_name(hass, e.entity_id),
                    "available": bool(state) and state.state != "unavailable",
                    "apps": _bridge_for(hass, e.entity_id) is not None})
    return sorted(out, key=lambda d: d["name"].casefold())


async def _adb(hass: HomeAssistant, bridge: str, command: str) -> str:
    await hass.services.async_call("androidtv", "adb_command", {"entity_id": bridge, "command": command}, blocking=True)
    state = hass.states.get(bridge)
    return str((state.attributes.get("adb_response") if state else "") or "")


async def _open_app(call: ServiceCall) -> None:
    hass = call.hass
    device, app = str(call.data["device"]), str(call.data["app"]).strip()
    package = str(call.data.get("package") or "").strip() or None
    label = str(call.data.get("name") or app)
    where = _device_name(hass, device)
    if not valid_app(app) or (package and not valid_app(package)):
        raise HomeAssistantError(f"{label}: not an app id or link")
    bridge = _bridge_for(hass, device)
    if bridge:
        state = hass.states.get(bridge)
        if state is None or state.state == "unavailable":
            raise HomeAssistantError(f"The Android Debug Bridge for {where} is not connected")
        locks: dict[str, asyncio.Lock] = hass.data.setdefault(_LOCKS, {})
        async with locks.setdefault(bridge, asyncio.Lock()):            # one command's reply at a time per box
            await _adb(hass, bridge, WAKE)
            reply = ""
            for command in open_commands(app, package):
                reply = await _adb(hass, bridge, command)
                if opened(reply):
                    _LOGGER.debug("opened %s on %s through %s", app, where, bridge)
                    return
            if not_installed(reply):
                raise HomeAssistantError(f"{label} is not installed on {where}")
            raise HomeAssistantError(f"{label} did not open on {where}: {reply.strip()[-200:]}")
    entry = er.async_get(hass).async_get(device)
    if entry and entry.platform == "androidtv_remote":
        remote = device if entry.domain == "remote" else next(
            (e.entity_id for e in er.async_entries_for_device(er.async_get(hass), entry.device_id) if e.domain == "remote"), None)
        if remote:
            await hass.services.async_call("remote", "turn_on", {"entity_id": remote, "activity": app}, blocking=True)
            return
    raise HomeAssistantError(f"{where} cannot open apps from Home Assistant: add the box to the Android Debug Bridge integration")


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/devices"})
@callback
def ws_devices(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    connection.send_result(msg["id"], {"devices": cast_devices(hass)})


@callback
def async_register(hass: HomeAssistant) -> None:
    if not hass.services.has_service(DOMAIN, SERVICE_OPEN_APP):
        hass.services.async_register(DOMAIN, SERVICE_OPEN_APP, _open_app, schema=OPEN_APP_SCHEMA)
    if not hass.data.setdefault(DOMAIN, {}).get("ws_devices"):
        websocket_api.async_register_command(hass, ws_devices)
        hass.data[DOMAIN]["ws_devices"] = True
