"""Sensor platform for ECOWORTHY battery telemetry."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import ECOWORTHYBatteryCoordinator, BatteryData

_VALUE = Callable[[BatteryData], Any]

SENSOR_DESCRIPTIONS: dict[str, SensorEntityDescription] = {
    "soc": SensorEntityDescription(
        key="soc",
        name="State of charge",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    "voltage": SensorEntityDescription(
        key="voltage",
        name="Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    "current": SensorEntityDescription(
        key="current",
        name="Current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    "power": SensorEntityDescription(
        key="power",
        name="Power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    "temperature": SensorEntityDescription(
        key="temperature",
        name="Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    "capacity": SensorEntityDescription(
        key="capacity",
        name="Design capacity",
        native_unit_of_measurement="Ah",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:battery-charging",
    ),
    "health": SensorEntityDescription(
        key="health",
        name="State of health",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:heart",
    ),
    "problem_code": SensorEntityDescription(
        key="problem_code",
        name="Problem code",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:alert-circle-outline",
    ),
}


def _cell_description(index: int) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=f"cell_{index}",
        name=f"Cell {index} voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
    )


class ECOWORTHYBatterySensor(CoordinatorEntity, SensorEntity):
    """A single telemetry sensor for one battery."""

    def __init__(
        self,
        coordinator: ECOWORTHYBatteryCoordinator,
        address: str,
        name: str,
        description: SensorEntityDescription,
        value_fn: _VALUE,
    ) -> None:
        super().__init__(coordinator)
        self._address = address
        self._value_fn = value_fn
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{address}_{description.key}"
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            name=name,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self.coordinator.data.get(self._address) is not None

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data.get(self._address)
        if data is None:
            return None
        return self._value_fn(data)


def _getter(key: str) -> _VALUE:
    return {
        "soc": lambda d: d.soc,
        "voltage": lambda d: d.voltage,
        "current": lambda d: d.current,
        "power": lambda d: d.power,
        "temperature": lambda d: d.temperature,
        "capacity": lambda d: d.capacity_ah,
        "health": lambda d: d.soh,
        "problem_code": lambda d: d.problem_code,
    }[key]


@callback
def _entity_list(
    coordinator: ECOWORTHYBatteryCoordinator,
) -> list[ECOWORTHYBatterySensor]:
    entities: list[ECOWORTHYBatterySensor] = []
    for address, battery in coordinator.data.items():
        if battery is None:
            continue
        for key, description in SENSOR_DESCRIPTIONS.items():
            entities.append(
                ECOWORTHYBatterySensor(
                    coordinator, address, battery.name, description, _getter(key)
                )
            )
        for i in range(len(battery.cells)):
            idx = i + 1
            entities.append(
                ECOWORTHYBatterySensor(
                    coordinator,
                    address,
                    battery.name,
                    _cell_description(idx),
                    lambda d, i=idx: d.cells[i - 1] if len(d.cells) >= i else None,
                )
            )
    return entities


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: ECOWORTHYBatteryCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(_entity_list(coordinator))
