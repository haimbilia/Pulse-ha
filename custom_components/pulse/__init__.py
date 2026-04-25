from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
from aiohttp import web

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PulseApiClient
from .const import (
    CONF_HOST,
    CONF_PORT,
    CONF_TOKEN,
    CONF_WEBHOOK_ID,
    DATA_ABSENCE,
    DATA_CLIENT,
    DATA_COORDINATOR,
    DATA_WEBHOOK_ID,
    DOMAIN,
    PLATFORMS,
    STALE_CONTROLLER_GRACE_PUSHES,
)
from .coordinator import PULSE_WAKE_EVENT, PulseDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    # Generate and persist a webhook_id on first setup. Persisted in
    # entry.data so the URL stays stable across HA restarts.
    webhook_id = entry.data.get(CONF_WEBHOOK_ID)
    if not webhook_id:
        webhook_id = webhook.async_generate_id()
        new_data = {**entry.data, CONF_WEBHOOK_ID: webhook_id}
        hass.config_entries.async_update_entry(entry, data=new_data)

    session = async_get_clientsession(hass)
    client = PulseApiClient(
        session=session,
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        token=entry.data.get(CONF_TOKEN),
    )
    coordinator = PulseDataUpdateCoordinator(hass, client)

    hass.data[DOMAIN][entry.entry_id] = {
        DATA_CLIENT: client,
        DATA_COORDINATOR: coordinator,
        DATA_WEBHOOK_ID: webhook_id,
        DATA_ABSENCE: {},
    }

    webhook.async_register(
        hass, DOMAIN, "Pulse push", webhook_id, _handle_webhook
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Auto-configure the firmware with the webhook URL HA just generated.
    # Fire-and-forget — if the firmware is unreachable right now, integration
    # setup still succeeds; the user can fix it and the next HA restart
    # re-pushes. Manual `ha_url` / `ha_webhook` serial commands remain as
    # a fallback.
    hass.async_create_task(_push_webhook_url_to_firmware(hass, entry, webhook_id))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        webhook_id = entry.data.get(CONF_WEBHOOK_ID)
        if webhook_id:
            try:
                webhook.async_unregister(hass, webhook_id)
            except ValueError:
                # Already unregistered (e.g. HA restart re-registered).
                pass
        # Best-effort firmware cleanup so it doesn't keep pushing to a dead
        # webhook after the integration is removed. Not awaited — unload
        # should not block on firmware reachability.
        host = entry.data.get(CONF_HOST)
        port = entry.data.get(CONF_PORT)
        if host and port:
            hass.async_create_task(_clear_firmware_webhook_config(hass, host, port))
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _handle_webhook(
    hass: HomeAssistant,
    webhook_id: str,
    request: web.Request,
) -> web.Response:
    try:
        payload: Any = await request.json()
    except (ValueError, TypeError):
        return web.Response(status=400, text="invalid json")

    if not isinstance(payload, dict):
        return web.Response(status=400, text="payload not object")
    if payload.get("deviceName") != "pulse":
        return web.Response(status=400, text="unknown deviceName")

    payload_type = payload.get("type")
    if payload_type not in ("state", "pulse"):
        return web.Response(status=400, text="unknown type")

    # Find the entry for this webhook_id.
    entry: ConfigEntry | None = None
    for candidate in hass.config_entries.async_entries(DOMAIN):
        if candidate.data.get(CONF_WEBHOOK_ID) == webhook_id:
            entry = candidate
            break
    if entry is None:
        return web.Response(status=404, text="no matching entry")

    bucket = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not bucket:
        return web.Response(status=503, text="entry not loaded")

    coordinator: PulseDataUpdateCoordinator = bucket[DATA_COORDINATOR]

    if payload_type == "state":
        await _apply_state_push(hass, entry, coordinator, bucket, payload)
    else:  # pulse
        _fire_pulse_event(hass, payload)

    return web.Response(status=200, text="ok")


async def _apply_state_push(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: PulseDataUpdateCoordinator,
    bucket: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    controllers_raw = payload.get("controllers", [])
    if not isinstance(controllers_raw, list):
        controllers_raw = []

    pc_online = bool(payload.get("pcOnline", False))

    # Normalize MAC casing once so downstream identifier slugs are stable.
    controllers: list[dict[str, Any]] = []
    seen_macs: set[str] = set()
    for c in controllers_raw:
        if not isinstance(c, dict):
            continue
        mac = str(c.get("mac", "")).strip().lower()
        if not mac:
            continue
        seen_macs.add(mac)
        controllers.append(
            {
                "mac": mac,
                "name": c.get("name", mac),
                "radio": c.get("radio", "unknown"),
                "pm_action": c.get("pm_action", 0),
                "sp_action": c.get("sp_action", 0),
                "singlePressValidated": bool(c.get("singlePressValidated", False)),
            }
        )

    new_data = dict(coordinator.data or {})
    new_data["controllers"] = controllers
    new_data["pcOnline"] = pc_online
    if "fw" in payload:
        new_data["fw"] = payload.get("fw")
    coordinator.async_set_updated_data(new_data)

    _reconcile_stale_controllers(hass, entry, bucket, seen_macs)


def _reconcile_stale_controllers(
    hass: HomeAssistant,
    entry: ConfigEntry,
    bucket: dict[str, Any],
    seen_macs: set[str],
) -> None:
    """Track absence counts and remove devices that miss N pushes in a row.

    Grace = STALE_CONTROLLER_GRACE_PUSHES (3 pushes ≈ 6 min) so a single
    bad/empty payload doesn't nuke real controllers.
    """
    absence: dict[str, int] = bucket[DATA_ABSENCE]

    # Reset counters for MACs that are present in this push.
    for mac in list(absence.keys()):
        if mac in seen_macs:
            absence[mac] = 0

    # Make sure tracked-set covers anything the device knows about. We
    # learn known MACs from the diff against currently-registered devices.
    dev_reg = dr.async_get(hass)
    known_devices: dict[str, dr.DeviceEntry] = {}
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        for ident in device.identifiers:
            if len(ident) != 2 or ident[0] != DOMAIN:
                continue
            slug = ident[1]
            prefix = f"{entry.entry_id}_controller_"
            if not slug.startswith(prefix):
                continue
            mac_slug = slug[len(prefix):]
            # Reverse the slug ("aabbccddeeff" → "aa:bb:cc:dd:ee:ff").
            if len(mac_slug) == 12:
                mac = ":".join(mac_slug[i:i + 2] for i in range(0, 12, 2))
                known_devices[mac] = device

    # Increment absence for known devices that didn't appear in this push.
    for mac in known_devices:
        if mac not in seen_macs:
            absence[mac] = absence.get(mac, 0) + 1

    # Remove devices that have hit the grace threshold.
    to_drop: list[str] = []
    for mac, count in absence.items():
        if count >= STALE_CONTROLLER_GRACE_PUSHES and mac in known_devices:
            device = known_devices[mac]
            _LOGGER.info(
                "Removing stale Pulse controller %s after %d missed pushes",
                mac,
                count,
            )
            dev_reg.async_remove_device(device.id)
            to_drop.append(mac)

    for mac in to_drop:
        absence.pop(mac, None)


def _fire_pulse_event(hass: HomeAssistant, payload: dict[str, Any]) -> None:
    """Map a "pulse" webhook payload to PULSE_WAKE_EVENT on the bus.

    Field names match what the old coordinator polling path used (mac,
    name, radio, rssi, source, type) so binary_sensor / sensor listeners
    don't need to change. pulse_type → type.
    """
    mac = str(payload.get("mac", "")).strip().lower()
    if not mac:
        return

    hass.bus.async_fire(
        PULSE_WAKE_EVENT,
        {
            "mac": mac,
            "name": payload.get("name", mac),
            "radio": payload.get("radio", "unknown"),
            "rssi": payload.get("rssi"),
            "source": payload.get("source", ""),
            "type": payload.get("pulse_type", "pairing_mode"),
        },
    )


async def _push_webhook_url_to_firmware(
    hass: HomeAssistant,
    entry: ConfigEntry,
    webhook_id: str,
) -> None:
    """Tell the firmware where to push by POSTing the webhook URL.

    Idempotent — runs every entry setup. If HA's URL changes, the next
    restart re-syncs the firmware. Falls back silently if the firmware
    is unreachable; user can configure manually via serial commands.
    """
    url = webhook.async_generate_url(hass, webhook_id)
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    target = f"http://{host}:{port}/ha_config"

    session = async_get_clientsession(hass)
    try:
        async with session.post(
            target,
            data=url,
            headers={"Content-Type": "text/plain"},
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status == 200:
                _LOGGER.info(
                    "Pushed HA webhook URL to Pulse firmware at %s", host
                )
            else:
                _LOGGER.warning(
                    "Pulse firmware rejected webhook URL push: HTTP %s",
                    resp.status,
                )
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        _LOGGER.warning(
            "Could not push webhook URL to Pulse firmware at %s: %s. "
            "User can configure manually via 'ha_url' / 'ha_webhook' "
            "serial commands.",
            host,
            err,
        )


async def _clear_firmware_webhook_config(
    hass: HomeAssistant, host: str, port: int
) -> None:
    """Best-effort empty POST to clear the firmware's HA config on unload."""
    session = async_get_clientsession(hass)
    try:
        async with session.post(
            f"http://{host}:{port}/ha_config",
            data="",
            headers={"Content-Type": "text/plain"},
            timeout=aiohttp.ClientTimeout(total=5),
        ):
            pass
    except (aiohttp.ClientError, asyncio.TimeoutError):
        pass
