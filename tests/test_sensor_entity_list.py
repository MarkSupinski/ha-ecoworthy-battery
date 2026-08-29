"""Regression tests for sensor entity list creation (no HA / no BLE needed).

sensor.py and coordinator.py are loaded directly (as in test_decoder.py) with
minimal stubs for the `homeassistant.*`, `bleak` and `bleak_retry_connector`
imports, so the logic runs on a CI runner that does not have Home Assistant
installed.
"""

import importlib.util
import sys
import types
from pathlib import Path
from typing import Generic, TypeVar

_CC_DIR = Path(__file__).resolve().parent.parent / "custom_components"
_PKG_DIR = _CC_DIR / "ecoworthy_battery"


def _install_stubs() -> None:
    """Populate sys.modules with the minimal homeassistant/bleak surface."""

    def make_package(name: str) -> types.ModuleType:
        """Create a package-like module (has __path__) and register it."""
        mod = types.ModuleType(name)
        mod.__spec__ = importlib.util.spec_from_loader(name, None, is_package=True)
        mod.__path__ = []
        sys.modules[name] = mod
        return mod

    def make_module(name: str, **attrs) -> types.ModuleType:
        mod = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(mod, key, value)
        sys.modules[name] = mod
        return mod

    homeassistant = make_package("homeassistant")
    components = make_package("homeassistant.components")
    helpers = make_package("homeassistant.helpers")
    homeassistant.components = components
    homeassistant.helpers = helpers

    # homeassistant.components.bluetooth
    make_module(
        "homeassistant.components.bluetooth",
        BluetoothServiceInfoBleak=object,
        async_ble_device_from_address=lambda *a, **k: None,
        async_discovered_service_info=lambda *a, **k: [],
    )

    # homeassistant.components.sensor
    class SensorDeviceClass:
        BATTERY = "battery"
        VOLTAGE = "voltage"
        CURRENT = "current"
        POWER = "power"
        TEMPERATURE = "temperature"
        TIMESTAMP = "timestamp"

    class SensorStateClass:
        MEASUREMENT = "measurement"

    class SensorEntityDescription:
        def __init__(self, **kwargs) -> None:
            self.__dict__.update(kwargs)

    class SensorEntity:
        pass

    make_module(
        "homeassistant.components.sensor",
        SensorDeviceClass=SensorDeviceClass,
        SensorStateClass=SensorStateClass,
        SensorEntityDescription=SensorEntityDescription,
        SensorEntity=SensorEntity,
    )

    # homeassistant.config_entries / const / core are direct submodules of
    # `homeassistant` (matching the real package layout).
    make_module("homeassistant.config_entries", ConfigEntry=object)

    class UnitOfElectricPotential:
        VOLT = "V"

    class UnitOfElectricCurrent:
        AMPERE = "A"

    class UnitOfPower:
        WATT = "W"

    class UnitOfTemperature:
        CELSIUS = "°C"

    make_module(
        "homeassistant.const",
        PERCENTAGE="%",
        UnitOfElectricPotential=UnitOfElectricPotential,
        UnitOfElectricCurrent=UnitOfElectricCurrent,
        UnitOfPower=UnitOfPower,
        UnitOfTemperature=UnitOfTemperature,
        CONF_SCAN_INTERVAL="scan_interval",
    )

    def callback(func):
        return func

    make_module("homeassistant.core", HomeAssistant=object, callback=callback)

    # homeassistant.helpers.device_registry / entity_platform /
    # update_coordinator
    class DeviceInfo:
        def __init__(self, **kwargs) -> None:
            self.__dict__.update(kwargs)

    make_module(
        "homeassistant.helpers.device_registry",
        DeviceInfo=DeviceInfo,
        CONNECTION_BLUETOOTH="bluetooth",
    )
    make_module("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)

    _T = TypeVar("_T")

    class DataUpdateCoordinator(Generic[_T]):
        def __init__(self, hass, logger, *, name, update_interval=None, **kwargs) -> None:
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
            self.data = None
            self.last_update_success = True
            self._listeners: list = []

        def async_add_listener(self, listener) -> None:
            self._listeners.append(listener)

        def async_remove_listener(self, listener) -> None:
            self._listeners.remove(listener)

    class CoordinatorEntity:
        def __init__(self, coordinator) -> None:
            self._coordinator = coordinator
            self._attr_should_poll = False

        @property
        def coordinator(self):
            return self._coordinator

        @property
        def available(self) -> bool:
            return bool(getattr(self._coordinator, "last_update_success", False))

    make_module(
        "homeassistant.helpers.update_coordinator",
        DataUpdateCoordinator=DataUpdateCoordinator,
        CoordinatorEntity=CoordinatorEntity,
        UpdateFailed=Exception,
    )

    # bleak / bleak_retry_connector
    make_module("bleak", BleakClient=object)
    make_module("bleak_retry_connector", establish_connection=lambda *a, **k: None)
def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(f"ecoworthy_battery.{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"ecoworthy_battery.{name}"] = module
    spec.loader.exec_module(module)
    return module


# Install stubs once at import time, then load the real package modules in
# dependency order (decoder, const, coordinator, sensor).
_install_stubs()
pkg = types.ModuleType("ecoworthy_battery")
pkg.__path__ = [str(_PKG_DIR)]
sys.modules["ecoworthy_battery"] = pkg

_load_module("decoder", _PKG_DIR / "decoder.py")
_load_module("const", _PKG_DIR / "const.py")
coordinator = _load_module("coordinator", _PKG_DIR / "coordinator.py")
sensor = _load_module("sensor", _PKG_DIR / "sensor.py")


def _fake_coordinator(discovered, data):
    return types.SimpleNamespace(
        discovered_batteries=discovered,
        data=data,
        last_update_success=True,
        async_add_listener=lambda cb: None,
    )


def test_entity_list_with_no_data_yet():
    """Regression: coordinator.data is None until the first refresh completes.

    Entity creation (async_setup_entry -> _entity_list) must not crash when
    data is None, and the created sensors must render unavailable.
    """
    entities = sensor._entity_list(
        _fake_coordinator({"AA:BB": "Battery A"}, None)
    )
    # 9 telemetry sensors + 4 default cell sensors (these packs are 4S).
    assert len(entities) == len(sensor.SENSOR_DESCRIPTIONS) + 4

    for ent in entities:
        assert not ent.available, "no data yet -> sensor must be unavailable"
        assert ent.native_value is None, "no data yet -> value must be None"


def test_entity_list_with_battery_data():
    """With a successful read the full sensor set is created."""
    battery = coordinator.BatteryData(address="AA:BB", name="Battery A", soc=88)
    battery.cells = [3.30, 3.31, 3.32, 3.33]
    entities = sensor._entity_list(
        _fake_coordinator({"AA:BB": "Battery A"}, {"AA:BB": battery})
    )
    assert len(entities) == len(sensor.SENSOR_DESCRIPTIONS) + 4


def test_entity_list_with_unreadable_battery():
    """A battery that advertised but failed to read gets entities too."""
    entities = sensor._entity_list(
        _fake_coordinator(
            {"AA:BB": "Battery A", "CC:DD": "Battery B"}, {"AA:BB": None}
        )
    )
    assert len(entities) == 2 * (len(sensor.SENSOR_DESCRIPTIONS) + 4)

