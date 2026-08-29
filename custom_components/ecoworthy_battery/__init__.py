"""ECOWORTHY 0B / 02 battery BLE integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MANUFACTURER,
    MODEL,
    TITLE,
)
from .coordinator import ECOWORTHYBatteryCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration (config-flow only; nothing to do here)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    coordinator = ECOWORTHYBatteryCoordinator(hass, entry)
    # Seed the discovery cache synchronously so sensor entities can be created
    # for batteries that are already advertising, without waiting on a BLE poll.
    coordinator.seed_discovered()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Start the polling loop in the background; never block HA startup on BLE.
    hass.async_create_task(coordinator.async_config_entry_first_refresh())
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply option changes (e.g. scan interval) without a full reload."""
    coordinator: ECOWORTHYBatteryCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.update_interval = timedelta(
        seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )
    await coordinator.async_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the integration and all its platforms."""
    coordinator: ECOWORTHYBatteryCoordinator = hass.data[DOMAIN][entry.entry_id]
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await coordinator.async_unload()
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
