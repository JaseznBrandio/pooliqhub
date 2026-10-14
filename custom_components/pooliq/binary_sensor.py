"""Binary sensor platform for Pool IQ (on/off states)."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PoolIQCoordinator
from .entity import PoolIQEntity


@dataclass(frozen=True, kw_only=True)
class PoolIQBinaryDescription(BinarySensorEntityDescription):
    """Binary sensor description; on_value is the reported value meaning 'on'."""

    on_value: str = "ON"


BINARY_SENSORS: tuple[PoolIQBinaryDescription, ...] = (
    PoolIQBinaryDescription(
        key="PumpStatus",
        name="Chlorinator pump",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:pump",
    ),
    PoolIQBinaryDescription(
        key="pHStatus",
        name="pH dosing pump",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:pump",
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PoolIQCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(PoolIQBinarySensor(coordinator, desc) for desc in BINARY_SENSORS)


class PoolIQBinarySensor(PoolIQEntity, BinarySensorEntity):
    entity_description: PoolIQBinaryDescription

    def __init__(
        self, coordinator: PoolIQCoordinator, description: PoolIQBinaryDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        value = self._prop_value(self.entity_description.key)
        if value is None:
            return None
        return str(value).upper() == self.entity_description.on_value.upper()
