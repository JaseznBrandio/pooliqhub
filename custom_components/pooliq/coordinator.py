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

from urllib.parse import parse_qsl

from .api import SOCKET_KEYS, PoolIQAuthError, PoolIQClient, PoolIQConnectionError, PoolIQError
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
# While live updates are flowing, polling is only a safety net.
PUSH_FALLBACK_INTERVAL = timedelta(seconds=300)
TRIGGER_WAIT = 3  # seconds for the hub to answer a full-report request
DEFAULT_BOOST_HOURS = 8
DEFAULT_PH_AMOUNT = 100  # ml, pH demand/prime amount sent with Start
PENDING_HOLD = 20  # seconds to keep showing a written value the device hasn't confirmed
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
        # Values just written from HA, shown until the device reports something newer:
        # key -> (value, written_at_ms, give_up_at_monotonic)
        self._pending: dict[str, tuple[Any, int, float]] = {}
        self.ph_amount: int = DEFAULT_PH_AMOUNT
        self._salt_test: dict[str, Any] | None = None
        self.push_connected = False
        # When the running boost ends (epoch seconds), learned from the unit's
        # boost screen ("Hour=8&Minute=0&Second=0") and kept across restarts.
        self.boost_ends: float | None = None
        self._boost_asked = 0.0
        self._state_store: Store = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.state"
        )
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

    async def async_load_state(self) -> None:
        stored = await self._state_store.async_load()
        if isinstance(stored, dict) and isinstance(stored.get("boost_ends"), (int, float)):
            self.boost_ends = float(stored["boost_ends"])

    @callback
    def _save_state(self) -> None:
        self._state_store.async_delay_save(lambda: {"boost_ends": self.boost_ends}, 2)

    @callback
    def set_boost(self, ends: float | None) -> None:
        if ends != self.boost_ends:
            self.boost_ends = ends
            self._save_state()

    @callback
    def boost_from_param(self, param: Any) -> bool:
        """Set the boost end time from the boost screen's "Hour=..&Minute=..&Second=.."."""
        if not isinstance(param, str) or "Hour=" not in param:
            return False
        fields = dict(parse_qsl(param))
        try:
            secs = int(fields.get("Hour", 0)) * 3600 + int(fields.get("Minute", 0)) * 60 + int(
                fields.get("Second", 0))
        except ValueError:
            return False
        self.set_boost(time.time() + secs if secs > 0 else None)
        return True

    def _inject_boost(self, props: dict[str, Any]) -> dict[str, Any]:
        spec = str((props.get("SpecMode") or {}).get("value", ""))
        if spec and spec != "2" and self.boost_ends is not None:
            self.set_boost(None)  # boost finished or was stopped
        if self.boost_ends is not None and self.boost_ends < time.time():
            self.set_boost(None)
        props = dict(props)
        if self.boost_ends is not None:
            props["BoostEndsAt"] = {"property": "BoostEndsAt", "value": self.boost_ends}
        else:
            props.pop("BoostEndsAt", None)
        return props

    async def _ask_boost_remaining(self, props: dict[str, Any]) -> None:
        """Boost running but end time unknown (e.g. after a restart): ask the boost screen."""
        if str((props.get("SpecMode") or {}).get("value", "")) != "2" or self.boost_ends:
            return
        if time.monotonic() - self._boost_asked < 600:
            return
        self._boost_asked = time.monotonic()
        try:
            reply = await self.client.async_invoke(
                "optionRequest", {"menu": "M4", "button": "NULL", "param": "NULL"})
        except PoolIQError as err:
            _LOGGER.debug("Boost screen read failed: %s", err)
            return
        for item in reply if isinstance(reply, list) else [reply]:
            if isinstance(item, dict) and self.boost_from_param(item.get("param")):
                return

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

        props = self._apply_pending(props)
        if chlorinator:
            await self._ask_boost_remaining(props)
            props = self._inject_boost(props)
        self._pick_interval(props)
        return {"properties": props, "sockets": dict(self._sockets)}

    @callback
    def hold(self, key: str, value: Any) -> None:
        """Show a value straight away and keep it until the unit reports something newer."""
        self._pending[key] = (value, int(time.time() * 1000), time.monotonic() + PENDING_HOLD)
        if self.data is not None:
            props = self._apply_pending(dict(self.data.get("properties") or {}))
            if "OutputSetPoint" in props:
                props = self._inject_boost(props)
            self.data = {**self.data, "properties": props}
            self.async_update_listeners()

    def forget_pending(self, *keys: str) -> None:
        """Stop holding values that a new change makes out of date."""
        for key in keys:
            self._pending.pop(key, None)

    def _apply_pending(self, props: dict[str, Any]) -> dict[str, Any]:
        """Keep showing values written from HA until the device reports a newer one.

        Without this, a check that started just before a change can finish just
        after it and briefly put the old value back (a mode "bouncing back").
        """
        if not self._pending:
            return props
        now = time.monotonic()
        props = dict(props)
        for key, (value, written_ms, give_up) in list(self._pending.items()):
            reported_ms = int((props.get(key) or {}).get("timestamp") or 0)
            if now > give_up or reported_ms >= written_ms:
                del self._pending[key]
                continue
            item = {**(props.get(key) or {}), "property": key, "value": value}
            if isinstance(value, (int, float)):
                item["numberValue"] = value
            props[key] = item
        return props

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
        # One small log search per check, so a test run from the app shows up too.
        self._was_testing = testing
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
        if self.push_connected:
            # Changes arrive live; poll only as a safety net.
            self.update_interval = max(self._normal_interval, PUSH_FALLBACK_INTERVAL)
        elif now < self._fast_until:
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
        # Use the current time so stale in-flight reports (which carry an
        # older timestamp) cannot overwrite this optimistic state.
        self._sockets[socket] = {"ts": int(time.time() * 1000), "fields": fields}
        self._save_cache()
        if self.data is not None:
            self.async_set_updated_data({**self.data, "sockets": dict(self._sockets)})
        self._schedule_confirm()

    @callback
    def _schedule_confirm(self) -> None:
        """Check back soon after a command, then keep checking quickly for a while."""
        self._fast_until = time.monotonic() + FAST_WINDOW
        if self.push_connected:
            return  # the unit's answer arrives on the live channel
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

        written_ms = int(time.time() * 1000)
        for key, value in {**values, **(show or {})}.items():
            self._pending[key] = (value, written_ms, time.monotonic() + PENDING_HOLD)
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

    # ------------------------------------------------------------ live updates

    @callback
    def push_state(self, connected: bool) -> None:
        """Live channel opened or dropped."""
        self.push_connected = connected
        props = (self.data or {}).get("properties") or {}
        self._pick_interval(props)
        if not connected:
            # Catch up on anything missed while it was down.
            self.hass.async_create_task(self.async_request_refresh())

    @callback
    def handle_push(self, payload: dict[str, Any]) -> None:
        """Apply one message from the live channel straight away."""
        if self.data is None:
            return
        kind = payload.get("messageType")
        now_ms = int(time.time() * 1000)
        ts = payload.get("timestamp")
        # Some replies carry the unit's own clock, which can be years off.
        ts = ts if isinstance(ts, int) and abs(ts - now_ms) < 86_400_000 else now_ms

        updates: dict[str, Any] = {}
        sockets_changed = False
        if kind == "REPORT_PROPERTY":
            for key, value in (payload.get("properties") or {}).items():
                if str(key).upper() in SOCKET_KEYS and isinstance(value, str):
                    sock_key = str(key).upper()
                    cur = self._sockets.get(sock_key)
                    if cur is None or ts >= cur["ts"]:
                        self._sockets[sock_key] = {"ts": ts, "fields": dict(parse_qsl(value))}
                        sockets_changed = True
                else:
                    updates[key] = value
        elif kind == "WRITE_PROPERTY":
            # A setting changed by the app (or by HA); some are never reported back.
            for key, value in (payload.get("properties") or {}).items():
                if key in WRITTEN_SETTINGS:
                    updates[key] = value
        elif kind == "EVENT" and payload.get("event") == "menuStatus":
            data = payload.get("data") or {}
            if data.get("menu") == "M4":
                # Boost screen: step 1 carries the time left, step 0 means stopped.
                if data.get("step") == 1:
                    self.boost_from_param(data.get("param"))
                elif data.get("step") == 0:
                    self.set_boost(None)
                updates["SpecMode"] = 2 if self.boost_ends else 0
            elif data.get("menu") == "M10" and isinstance(data.get("param"), str):
                fields = dict(parse_qsl(data["param"]))
                try:
                    value = int(fields.get("TDS", "0"))
                except ValueError:
                    value = 0
                if value > 0 and fields.get("condition", "").strip() == "OK":
                    self._salt_test = {"value": value, "ts": now_ms}
                    updates["SaltTestResult"] = value
        if not updates and not sockets_changed:
            return

        props = dict(self.data.get("properties") or {})
        for key, value in updates.items():
            item = {**(props.get(key) or {}), "property": key, "value": value, "timestamp": ts}
            if isinstance(value, (int, float)):
                item["numberValue"] = value
            else:
                item.pop("numberValue", None)
            props[key] = item
        props = self._apply_pending(props)
        if "OutputSetPoint" in props:
            props = self._inject_boost(props)
        if sockets_changed:
            self._save_cache()
        self._pick_interval(props)
        # Update listeners without postponing the safety-net poll.
        self.data = {**self.data, "properties": props, "sockets": dict(self._sockets)}
        self.async_update_listeners()
