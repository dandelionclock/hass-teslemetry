"""Teslemetry parent entity class."""

import asyncio
from typing import Any
from tesla_fleet_api import VehicleSpecific, EnergySpecific
from tesla_fleet_api.exceptions import TeslaFleetError

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import DOMAIN, MODELS, TeslemetryState
from .coordinator import (
    TeslemetryEnergySiteLiveCoordinator,
    TeslemetryVehicleDataCoordinator,
    TeslemetryEnergySiteInfoCoordinator,
)
from .models import TeslemetryEnergyData, TeslemetryVehicleData


class TeslemetryEntity(
    CoordinatorEntity[
        TeslemetryVehicleDataCoordinator
        | TeslemetryEnergySiteLiveCoordinator
        | TeslemetryEnergySiteInfoCoordinator
    ]
):
    """Parent class for all Teslemetry entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TeslemetryVehicleDataCoordinator
        | TeslemetryEnergySiteLiveCoordinator
        | TeslemetryEnergySiteInfoCoordinator,
        api: VehicleSpecific | EnergySpecific,
        key: str,
    ) -> None:
        """Initialize common aspects of a Teslemetry entity."""
        super().__init__(coordinator)
        self.api = api
        self.key = key
        self._attr_translation_key = key

    def get(self, key: str | None = None, default: Any | None = None) -> Any:
        """Return a specific value from coordinator data."""
        return self.coordinator.data.get(key or self.key, default)

    def exactly(self, value: Any) -> bool | None:
        """Return if a specific value is None, or matching in coordinator data."""
        if value is None:
            return self.get(self.key, False) is None
        current = self.get()
        if current is None:
            return None
        return current == value

    def set(self, *args: Any) -> None:
        """Set a value in coordinator data."""
        for key, value in args:
            self.coordinator.data[key] = value
        self.async_write_ha_state()

    def has(self, key: str | None = None) -> bool:
        """Return True if a specific value is in coordinator data."""
        return (key or self.key) in self.coordinator.data

    def raise_for_scope(self):
        """Raise an error if a scope is not available."""
        if not self.scoped:
            raise ServiceValidationError(
                f"Missing required scope: {' or '.join(self.entity_description.scopes)}"
            )


class TeslemetryVehicleEntity(TeslemetryEntity):
    """Parent class for Teslemetry Vehicle entities."""

    def __init__(
        self,
        data: TeslemetryVehicleData,
        key: str,
    ) -> None:
        """Initialize common aspects of a Teslemetry entity."""
        super().__init__(data.coordinator, data.api, key)
        self._attr_unique_id = f"{data.vin}-{key}"
        self._wakelock = data.wakelock

        if car_type := self.coordinator.data.get("vehicle_config_car_type"):
            car_type = MODELS.get(car_type, car_type)
        if sw_version := self.coordinator.data.get("vehicle_state_car_version"):
            sw_version = sw_version.split(" ")[0]

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, data.vin)},
            manufacturer="Tesla",
            configuration_url="https://teslemetry.com/console",
            name=self.coordinator.data.get("vehicle_state_vehicle_name")
            or self.coordinator.data.get("display_name")
            or data.vin,
            model=car_type,
            sw_version=sw_version,
            hw_version=self.coordinator.data.get("vehicle_config_driver_assist"),
            serial_number=data.vin,
        )

    async def wake_up_if_asleep(self) -> None:
        """Wake up the vehicle if its asleep."""
        async with self._wakelock:
            wait = 0
            while self.coordinator.data["state"] != TeslemetryState.ONLINE:
                try:
                    state = (await self.api.wake_up())["response"]["state"]
                except TeslaFleetError as err:
                    raise HomeAssistantError(str(err)) from err
                self.coordinator.data["state"] = state
                if state != TeslemetryState.ONLINE:
                    wait += 5
                    if wait >= 15:  # Give up after 30 seconds total
                        raise HomeAssistantError("Could not wake up vehicle")
                    await asyncio.sleep(wait)


class TeslemetryEnergyLiveEntity(TeslemetryEntity):
    """Parent class for Teslemetry Energy Site Live entities."""

    def __init__(
        self,
        data: TeslemetryEnergyData,
        key: str,
    ) -> None:
        """Initialize common aspects of a Teslemetry entity."""
        super().__init__(data.live_coordinator, data.api, key)
        self._attr_unique_id = f"{data.id}-{key}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(data.id))},
            manufacturer="Tesla",
            configuration_url="https://teslemetry.com/console",
            name=self.coordinator.data.get("site_name", "Energy Site"),
        )


class TeslemetryEnergyInfoEntity(TeslemetryEntity):
    """Parent class for Teslemetry Energy Site Info Entities."""

    def __init__(
        self,
        data: TeslemetryEnergyData,
        key: str,
    ) -> None:
        """Initialize common aspects of a Teslemetry entity."""
        super().__init__(data.info_coordinator, data.api, key)
        self._attr_unique_id = f"{data.id}-{key}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(data.id))},
            manufacturer="Tesla",
            configuration_url="https://teslemetry.com/console",
            name=self.coordinator.data.get("site_name", "Energy Site"),
        )


class TeslemetryWallConnectorEntity(
    TeslemetryEntity, CoordinatorEntity[TeslemetryEnergySiteLiveCoordinator]
):
    """Parent class for Teslemetry Wall Connector Entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        data: TeslemetryEnergyData,
        din: str,
        key: str,
    ) -> None:
        """Initialize common aspects of a Teslemetry entity."""
        super().__init__(data.live_coordinator, data.api, key)
        self._attr_unique_id = f"{data.id}-{din}-{key}"
        self.din = din

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, din)},
            manufacturer="Tesla",
            configuration_url="https://teslemetry.com/console",
            name="Wall Connector",
            via_device=(DOMAIN, str(data.id)),
            serial_number=din.split("-")[-1],
        )

    @property
    def _value(self) -> int:
        """Return a specific wall connector value from coordinator data."""
        return (
            self.coordinator.data.get("wall_connectors", {})
            .get(self.din, {})
            .get(self.key)
        )
