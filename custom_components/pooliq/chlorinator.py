"""Chlorinator controls: power mode, output, winter/spa modes, pH dosing, boost, salt test.

Each control is created only when the device reports the property it drives,
so a Pool IQ controller without a salt cell doesn't get chlorinator entities.

Settings are written exactly as the Pool IQ app writes them. Boost and the salt
test are device functions (optionRequest with menu M4 / M10), also as the app
sends them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.components.number import (
    NumberEntityDescription,
    NumberMode,
    RestoreNumber,
)
from homeassistant.components.number import NumberEntity
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime

from .coordinator import PoolIQCoordinator
from .entity import PoolIQEntity

# The setting that tells us a device has a salt cell.
CHLORINATOR_MARKER = "OutputSetPoint"


# --------------------------------------------------------------------- selects


@dataclass(frozen=True, kw_only=True)
class ChlorSelectDescription(SelectEntityDescription):
    prop: str
    choices: dict[str, str]  # label -> value sent to the device


CHLOR_SELECTS: tuple[ChlorSelectDescription, ...] = (
    ChlorSelectDescription(
        key="PowerMode_ctl",
        prop="PowerMode",
        name="Chlorinator mode",
        icon="mdi:power",
        choices={"On": "ON", "Off": "OFF", "Auto": "AUTO"},
    ),
    ChlorSelectDescription(
        key="ReriodSet_ctl",
        prop="ReriodSet",
        name="Timer cycle",
        icon="mdi:timer-outline",
        entity_category=EntityCategory.CONFIG,
        choices={"Single": "SINGLE_CYCLE", "Double": "DOUBLE_CYCLE"},
    ),
)


class ChlorSelect(PoolIQEntity, SelectEntity):
    entity_description: ChlorSelectDescription

    def __init__(self, coordinator: PoolIQCoordinator, desc: ChlorSelectDescription) -> None:
        super().__init__(coordinator, desc.key)
        self.entity_description = desc
        self._attr_options = list(desc.choices)

    @property
    def current_option(self) -> str | None:
        value = self._prop_value(self.entity_description.prop)
        for label, raw in self.entity_description.choices.items():
            if str(value).upper() == raw:
                return label
        return None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_write(
            {self.entity_description.prop: self.entity_description.choices[option]}
        )


# --------------------------------------------------------------------- numbers


@dataclass(frozen=True, kw_only=True)
class ChlorNumberDescription(NumberEntityDescription):
    prop: str


CHLOR_NUMBERS: tuple[ChlorNumberDescription, ...] = (
    ChlorNumberDescription(
        key="OutputSetPoint_ctl",
        prop="OutputSetPoint",
        name="Output setpoint",
        icon="mdi:water-percent",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
    ),
    ChlorNumberDescription(
        key="WinterModeSet_ctl",
        prop="WinterModeSet",
        name="Winter mode output",
        icon="mdi:snowflake",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.CONFIG,
    ),
    ChlorNumberDescription(
        key="SpaModeSet_ctl",
        prop="SpaModeSet",
        name="Spa mode output",
        icon="mdi:hot-tub",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.CONFIG,
    ),
    ChlorNumberDescription(
        key="pHRunForPerDay_ctl",
        prop="pHRunForPerDay",
        name="pH pump run time",
        icon="mdi:timer-outline",
        native_min_value=0,
        native_max_value=1440,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
    ChlorNumberDescription(
        key="pHRunAtDose_ctl",
        prop="pHRunAtDose",
        name="pH dose",
        icon="mdi:beaker-outline",
        native_min_value=0,
        native_max_value=5000,
        native_step=1,
        native_unit_of_measurement="mL",
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
)


class ChlorNumber(PoolIQEntity, NumberEntity):
    entity_description: ChlorNumberDescription

    def __init__(self, coordinator: PoolIQCoordinator, desc: ChlorNumberDescription) -> None:
        super().__init__(coordinator, desc.key)
        self.entity_description = desc

    @property
    def native_value(self) -> float | None:
        item = self._prop(self.entity_description.prop) or {}
        raw = item.get("numberValue", item.get("value"))
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_write({self.entity_description.prop: int(round(value))})


class BoostHours(PoolIQEntity, RestoreNumber):
    """How long boost runs when started from Home Assistant. Stored locally."""

    _attr_name = "Boost duration"
    _attr_icon = "mdi:rocket-launch-outline"
    _attr_native_min_value = 1
    _attr_native_max_value = 24
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PoolIQCoordinator) -> None:
        super().__init__(coordinator, "boost_hours")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last and last.native_value:
            self.coordinator.boost_hours = int(last.native_value)

    @property
    def native_value(self) -> float:
        return float(self.coordinator.boost_hours)

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.boost_hours = int(value)
        self.async_write_ha_state()


# -------------------------------------------------------------------- switches


@dataclass(frozen=True, kw_only=True)
class ChlorSwitchDescription(SwitchEntityDescription):
    prop: str
    on_value: str = "ON"
    off_value: str = "OFF"


CHLOR_SWITCHES: tuple[ChlorSwitchDescription, ...] = (
    ChlorSwitchDescription(key="WinterMode_ctl", prop="WinterMode", name="Winter mode",
                           icon="mdi:snowflake"),
    ChlorSwitchDescription(key="SpaMode_ctl", prop="SpaMode", name="Spa mode",
                           icon="mdi:hot-tub"),
    ChlorSwitchDescription(key="pHSwitch_ctl", prop="pHSwitch", name="pH dosing",
                           icon="mdi:beaker-outline"),
)


class ChlorSwitch(PoolIQEntity, SwitchEntity):
    entity_description: ChlorSwitchDescription

    def __init__(self, coordinator: PoolIQCoordinator, desc: ChlorSwitchDescription) -> None:
        super().__init__(coordinator, desc.key)
        self.entity_description = desc

    @property
    def is_on(self) -> bool | None:
        value = self._prop_value(self.entity_description.prop)
        if value is None:
            return None
        return str(value).upper() in (self.entity_description.on_value, "1")

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_write(
            {self.entity_description.prop: self.entity_description.on_value}
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_write(
            {self.entity_description.prop: self.entity_description.off_value}
        )


# --------------------------------------------------------------------- buttons


class ChlorButton(PoolIQEntity, ButtonEntity):
    """Runs a device function the same way the Pool IQ app does."""

    def __init__(self, coordinator: PoolIQCoordinator, desc: ButtonEntityDescription) -> None:
        super().__init__(coordinator, desc.key)
        self.entity_description = desc

    async def async_press(self) -> None:
        key = self.entity_description.key
        hours = self.coordinator.boost_hours
        if key == "boost_start":
            # The app opens the boost screen (menu M4) before pressing start.
            await self.coordinator.async_invoke(
                "optionRequest", {"menu": "M4", "button": "NULL", "param": "NULL"}
            )
            await self.coordinator.async_invoke(
                "optionRequest",
                {"menu": "M4", "button": "CHLORBOOST=START", "param": f"RUNHOURS={hours}"},
                wait=False,
            )
        elif key == "boost_stop":
            await self.coordinator.async_invoke(
                "optionRequest",
                {"menu": "M4", "button": "CHLORBOOST=STOP", "param": f"RUNHOURS={hours}"},
                wait=False,
            )
        elif key == "salt_test":
            # Opening the salt test screen (menu M10) runs the test.
            await self.coordinator.async_invoke(
                "optionRequest", {"menu": "M10", "button": "NULL", "param": "NULL"}
            )


CHLOR_BUTTONS: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(key="boost_start", name="Start boost", icon="mdi:rocket-launch"),
    ButtonEntityDescription(key="boost_stop", name="Stop boost", icon="mdi:stop-circle-outline"),
    ButtonEntityDescription(key="salt_test", name="Run salt test", icon="mdi:shaker-outline"),
)


# ---------------------------------------------------------------- factories


def is_chlorinator(coordinator: PoolIQCoordinator) -> bool:
    return coordinator.has(CHLORINATOR_MARKER)


def chlor_selects(c: PoolIQCoordinator) -> list[ChlorSelect]:
    return [ChlorSelect(c, d) for d in CHLOR_SELECTS if c.has(d.prop)]


def chlor_numbers(c: PoolIQCoordinator) -> list[NumberEntity]:
    ents: list[NumberEntity] = [ChlorNumber(c, d) for d in CHLOR_NUMBERS if c.has(d.prop)]
    if is_chlorinator(c):
        ents.append(BoostHours(c))
    return ents


def chlor_switches(c: PoolIQCoordinator) -> list[ChlorSwitch]:
    return [ChlorSwitch(c, d) for d in CHLOR_SWITCHES if c.has(d.prop)]


def chlor_buttons(c: PoolIQCoordinator) -> list[ChlorButton]:
    return [ChlorButton(c, d) for d in CHLOR_BUTTONS] if is_chlorinator(c) else []
