"""DataUpdateCoordinator for Pool IQ."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PoolIQAuthError, PoolIQClient, PoolIQConnectionError, PoolIQError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
CONFIRM_DELAY = 4  # seconds before the first check after a command
# After a command, poll quickly while the device works through it: a
# chlorinator purges for ~16s, then ramps its output for another ~15s.
FAST_INTERVAL = timedelta(seconds=5)
FAST_WINDOW = 90  # seconds of fast polling after each command
# While the device is mid-transition on its own (purging, salt test), keep
# checking every 10s, but never for longer than this.
SETTLING_INTERVAL = timedelta(seconds=10)
SETTLING_MAX = 600
TRIGGER_WAIT = 3  # seconds for the hub to answer a full-report request
DEFAULT_BOOST_HOURS = 8
# Settings the chlorinator doesn't (reliably) report back after a change; their
# current value is taken from the cloud's record of writes when that is newer.
WRITTEN_SETTINGS = (
    "WinterMode", "SpaMode", "pHSwitch", "WinterModeSet", "SpaModeSet",
    "pHRunForPerDay", "pHRunAtDose", "ReriodSet",
)


class PoolIQCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls readings and socket states.

    data = {"properties": {prop_id: item}, "sockets": {"SOCKET2": {"ts", "fields"}}}
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: PoolIQClient,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {client.device_id}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.entry = entry
        self._normal_interval = timedelta(seconds=scan_interval)
        self._fast_until = 0.0
        self._settling_since: float | None = None
        self._salt_test: dict[str, Any] | None = None
        self._salt_checked = 0.0
        self._was_testing = False
        # Socket state is only visible when the hub reports a change, so the
        # last known state is cached here and persisted across restarts.
        self._sockets: dict[str, dict[str, Any]] = {}
        # Boost duration (hours) sent with "start boost"; set by a number entity.
        self.boost_hours: int = DEFAULT_BOOST_HOURS
        self._store: Store = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.sockets"
        )

    @property
    def sockets(self) -> dict[str, dict[str, Any]]:
        return self._sockets

    async def async_load_cache(self) -> None:
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            for sock, fields in stored.items():
                if isinstance(fields, dict):
                    self._sockets[sock] = {"ts": 0, "fields": fields}

    @callback
    def _save_cache(self) -> None:
        self._store.async_delay_save(
            lambda: {s: v["fields"] for s, v in self._sockets.items()}, 10
        )

    async def _async_update_data(self) -> dict[str, Any]:
        if self.data is None:
            # First start: ask the hub to resend every reading and setting, so
            # values that rarely change (sockets, timers) are available at once.
            try:
                await self.client.async_invoke("triggerReport")
                await asyncio.sleep(TRIGGER_WAIT)
            except PoolIQError as err:
                _LOGGER.debug("triggerReport failed, continuing: %s", err)
        try:
            props = await self.client.async_get_properties()
        except PoolIQAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except PoolIQConnectionError as err:
            raise UpdateFailed(str(err)) from err

        chlorinator = "OutputSetPoint" in props
        try:
            if chlorinator and not self._sockets:
                reports = {}  # a chlorinator has no switched sockets
            else:
                # First start with nothing cached: look further back in the log.
                deep = self.data is None and not self._sockets
                reports = await self.client.async_get_socket_reports(deep=deep)
        except PoolIQError as err:
            _LOGGER.debug("Socket report read failed, keeping cached state: %s", err)
            reports = {}

        changed = False
        for sock, rep in reports.items():
            cur = self._sockets.get(sock)
            if cur is None or rep["ts"] > cur["ts"]:
                self._sockets[sock] = rep
                changed = True
        if changed:
            self._save_cache()

        if chlorinator:
            props = await self._apply_recent_writes(props)
            await self._update_salt_test(props)
            if self._salt_test:
                props = {**props, "SaltTestResult": {
                    "property": "SaltTestResult",
                    "value": self._salt_test["value"],
                    "numberValue": self._salt_test["value"],
                    "timestamp": self._salt_test["ts"],
                }}

        self._pick_interval(props)
        return {"properties": props, "sockets": dict(self._sockets)}

    async def _apply_recent_writes(self, props: dict[str, Any]) -> dict[str, Any]:
        """Use the newest written value for settings the device doesn't echo back."""
        try:
            writes = await self.client.async_get_recent_writes()
        except PoolIQError as err:
            _LOGGER.debug("Write log read failed: %s", err)
            return props
        props = dict(props)
        done: set[str] = set()
        for ts, values in writes:  # newest first
            for key, value in values.items():
                if key not in WRITTEN_SETTINGS or key in done:
                    continue
                done.add(key)
                cur = props.get(key) or {}
                if ts > int(cur.get("timestamp") or 0):
                    item = {**cur, "property": key, "value": value, "timestamp": ts}
                    if isinstance(value, (int, float)):
                        item["numberValue"] = value
                    props[key] = item
        return props

    async def _update_salt_test(self, props: dict[str, Any]) -> None:
        """Fetch the last salt test result when one may have just run (or every 5 min)."""
        testing = str((props.get("SpecMode") or {}).get("value", "")) == "3"
        now = time.monotonic()
        due = (
            self._salt_checked == 0.0
            or testing
            or self._was_testing
            or now < self._fast_until
            or now - self._salt_checked > 300
        )
        self._was_testing = testing
        if not due:
            return
        try:
            result = await self.client.async_get_salt_test(deep=self._salt_checked == 0.0)
        except PoolIQError as err:
            _LOGGER.debug("Salt test read failed: %s", err)
            return
        self._salt_checked = now
        if result and (self._salt_test is None or result["ts"] >= self._salt_test["ts"]):
            self._salt_test = result

    @staticmethod
    def _is_settling(props: dict[str, Any]) -> bool:
        """True while the device is in a short-lived state that will change on its own."""
        def val(key: str) -> str:
            return str((props.get(key) or {}).get("value", "")).upper()

        if val("CellStatus") == "PURGE" or val("SpecMode") == "3":  # 3 = salt test
            return True
        # A fault (e.g. low flow) clears itself once the cause is fixed.
        return val("Fault") not in ("", "0", "NONE", "NULL")

    @callback
    def _pick_interval(self, props: dict[str, Any]) -> None:
        now = time.monotonic()
        if self._is_settling(props):
            self._settling_since = self._settling_since or now
        else:
            self._settling_since = None
        if now < self._fast_until:
            self.update_interval = FAST_INTERVAL
        elif self._settling_since is not None and now - self._settling_since < SETTLING_MAX:
            self.update_interval = SETTLING_INTERVAL
        else:
            self.update_interval = self._normal_interval

    async def async_set_socket(self, socket: str, mode: str) -> None:
        """Write a socket mode, update optimistically, then confirm shortly after."""
        try:
            await self.client.async_set_socket(socket, mode)
        except (PoolIQConnectionError, PoolIQAuthError, ValueError) as err:
            raise HomeAssistantError(f"Pool IQ: could not set {socket} to {mode}: {err}") from err

        cur = self._sockets.get(socket) or {"ts": 0, "fields": {}}
        fields = dict(cur["fields"])
        fields["SW"] = mode
        # Keep the old timestamp so the hub's (newer) confirmation replaces this.
        self._sockets[socket] = {"ts": cur["ts"], "fields": fields}
        self._save_cache()
        if self.data is not None:
            self.async_set_updated_data({**self.data, "sockets": dict(self._sockets)})
        self._schedule_confirm()

    @callback
    def _schedule_confirm(self) -> None:
        """Check back soon after a command, then keep checking quickly for a while."""
        self._fast_until = time.monotonic() + FAST_WINDOW
        self.update_interval = FAST_INTERVAL

        async def _confirm(_now) -> None:
            await self.async_refresh()

        async_call_later(self.hass, CONFIRM_DELAY, _confirm)

    async def async_write(
        self, values: dict[str, Any], show: dict[str, Any] | None = None
    ) -> None:
        """Write device settings, show them immediately, confirm shortly after.

        `show` holds extra values to display straight away (e.g. the work mode a
        write will cause), until the device's own report replaces them.
        """
        try:
            await self.client.async_write_properties(values)
        except (PoolIQConnectionError, PoolIQAuthError) as err:
            raise HomeAssistantError(f"Pool IQ: could not set {values}: {err}") from err

        if self.data is not None:
            props = dict(self.data.get("properties") or {})
            for key, value in {**values, **(show or {})}.items():
                item = dict(props.get(key) or {"property": key})
                item["value"] = value
                if isinstance(value, (int, float)):
                    item["numberValue"] = value
                props[key] = item
            self.async_set_updated_data({**self.data, "properties": props})
        self._schedule_confirm()

    async def async_invoke(
        self, function: str, inputs: dict[str, Any] | None = None, *, wait: bool = True
    ) -> None:
        """Call a device function (boost, salt test), then refresh."""
        try:
            await self.client.async_invoke(function, inputs, wait=wait)
        except (PoolIQConnectionError, PoolIQAuthError) as err:
            raise HomeAssistantError(f"Pool IQ: {function} failed: {err}") from err
        self._schedule_confirm()

    def has(self, key: str) -> bool:
        """True when the device reports this property (used to pick entities)."""
        return key in ((self.data or {}).get("properties") or {})
