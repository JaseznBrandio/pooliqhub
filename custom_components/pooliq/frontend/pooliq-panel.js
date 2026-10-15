/*
 * Pool IQ sidebar panel for Home Assistant.
 * Plain web component, no build step. Uses Home Assistant theme variables so it
 * follows the user's light/dark theme. Talks to the integration through the
 * "pooliq/devices" websocket command and normal service calls.
 */

const ICON_RULES = [
  [/light/i, "mdi:lightbulb"],
  [/heater|heat/i, "mdi:water-boiler"],
  [/blower|air/i, "mdi:weather-windy"],
  [/jet/i, "mdi:hydro-power"],
  [/pump|filter/i, "mdi:pump"],
];

const MODES = ["On", "Off", "Auto"];

const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);

class PoolIQPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._devices = null;
    this._error = null;
    this._sig = "";
    this._busy = new Map(); // entity_id -> timestamp of last command
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._init();
    this._render();
  }

  get hass() {
    return this._hass;
  }

  set narrow(v) {
    this._narrow = v;
    this._sig = "";
    this._render();
  }

  set panel(v) {
    this._panel = v;
  }

  async _init() {
    await this._load();
    try {
      this._unsub = await this._hass.connection.subscribeEvents(
        () => this._load(),
        "entity_registry_updated"
      );
    } catch (_e) {
      /* non-admin users may not be allowed to subscribe; polling below covers it */
    }
    this._timer = setInterval(() => this._load(), 60000);
  }

  disconnectedCallback() {
    if (this._unsub) this._unsub();
    if (this._timer) clearInterval(this._timer);
    this._unsub = null;
    this._timer = null;
    this._hass = null;
  }

  connectedCallback() {
    if (this._hass && !this._timer) this._init();
  }

  async _load() {
    if (!this._hass) return;
    try {
      const res = await this._hass.callWS({ type: "pooliq/devices" });
      this._devices = res.devices || [];
      this._version = res.version;
      this._error = null;
    } catch (err) {
      this._error = (err && err.message) || String(err);
    }
    this._sig = "";
    this._render();
  }

  // ------------------------------------------------------------ helpers

  _st(eid) {
    return eid ? this._hass.states[eid] : undefined;
  }

  _shortName(eid, fallback) {
    const st = this._st(eid);
    const reg = this._hass.entities && this._hass.entities[eid];
    if (reg && reg.name) return reg.name;
    let name = (st && st.attributes.friendly_name) || fallback || eid;
    const dev = reg && reg.device_id && this._hass.devices && this._hass.devices[reg.device_id];
    const devName = dev && (dev.name_by_user || dev.name);
    if (devName && name.startsWith(devName + " ")) name = name.slice(devName.length + 1);
    return name;
  }

  _value(eid) {
    const st = this._st(eid);
    if (!st || st.state === "unavailable" || st.state === "unknown") return null;
    return st;
  }

  _fmtNumber(eid) {
    const st = this._value(eid);
    if (!st) return { num: "–", unit: "" };
    const n = Number(st.state);
    const num = Number.isFinite(n) ? (Number.isInteger(n) ? String(n) : n.toFixed(1)) : st.state;
    return { num, unit: st.attributes.unit_of_measurement || "" };
  }

  _icon(name) {
    for (const [re, icon] of ICON_RULES) if (re.test(name)) return icon;
    return "mdi:power-socket-au";
  }

  _isLight(name) {
    return /light/i.test(name);
  }

  // ------------------------------------------------------------ actions

  _onClick(ev) {
    const el = ev.composedPath().find((n) => n.dataset && n.dataset.action);
    if (!el || !this._hass) return;
    const { action, entity, option } = el.dataset;
    ev.stopPropagation();

    if (action === "toggle" && entity) {
      this._mark(entity);
      this._hass.callService("switch", "toggle", { entity_id: entity }).catch((e) => this._fail(entity, e));
    } else if (action === "mode" && entity && option) {
      this._mark(entity);
      this._hass
        .callService("select", "select_option", { entity_id: entity, option })
        .catch((e) => this._fail(entity, e));
    } else if (action === "switch" && entity) {
      this._mark(entity);
      this._hass.callService("switch", "toggle", { entity_id: entity }).catch((e) => this._fail(entity, e));
    } else if (action === "press" && entity) {
      this._mark(entity);
      this._hass.callService("button", "press", { entity_id: entity }).catch((e) => this._fail(entity, e));
    } else if (action === "nudge" && entity) {
      const st = this._st(entity);
      const cur = st ? Number(st.state) : NaN;
      if (!Number.isFinite(cur)) return;
      const min = Number(st.attributes.min ?? 0);
      const max = Number(st.attributes.max ?? 100);
      const value = Math.min(max, Math.max(min, cur + Number(el.dataset.delta || 0)));
      if (value === cur) return;
      this._mark(entity);
      this._hass
        .callService("number", "set_value", { entity_id: entity, value })
        .catch((e) => this._fail(entity, e));
    } else if (action === "more-info" && entity) {
      this.dispatchEvent(
        new CustomEvent("hass-more-info", { detail: { entityId: entity }, bubbles: true, composed: true })
      );
    }
  }

  _mark(eid) {
    this._busy.set(eid, Date.now());
    this._sig = "";
    this._render();
    setTimeout(() => {
      this._busy.delete(eid);
      this._sig = "";
      this._render();
    }, 8000);
  }

  _fail(eid, err) {
    this._busy.delete(eid);
    this._error = `Command failed: ${(err && err.message) || err}`;
    this._sig = "";
    this._render();
    setTimeout(() => {
      this._error = null;
      this._sig = "";
      this._render();
    }, 6000);
  }

  // ------------------------------------------------------------ render

  _signature() {
    const ids = [];
    for (const d of this._devices || []) {
      ids.push(...Object.values(d.readings));
      for (const s of d.sockets) ids.push(s.switch, s.mode);
    }
    const parts = ids.map((id) => {
      const st = this._st(id);
      return st ? `${id}=${st.state}|${st.attributes.friendly_name}|${st.attributes.mode || ""}` : `${id}=?`;
    });
    return JSON.stringify([
      parts, [...this._busy.keys()], this._error, this._narrow,
      (this._devices || []).map((d) => [d.entry_id, d.sockets.length, d.last_update_success]),
    ]);
  }

  _render() {
    if (!this._hass) return;
    const sig = this._signature();
    if (sig === this._sig && this.shadowRoot.childElementCount) return;
    this._sig = sig;

    const body =
      this._devices === null
        ? `<div class="empty">Loading…</div>`
        : this._devices.length === 0
          ? this._renderEmpty()
          : this._devices.map((d) => this._renderDevice(d)).join("");

    this.shadowRoot.innerHTML = `
      <style>${STYLES}</style>
      <div class="toolbar">
        <ha-menu-button></ha-menu-button>
        <div class="title">Pool IQ</div>
      </div>
      <div class="content">
        ${this._error ? `<div class="banner">${esc(this._error)}</div>` : ""}
        ${body}
      </div>`;

    const menu = this.shadowRoot.querySelector("ha-menu-button");
    if (menu) {
      menu.hass = this._hass;
      menu.narrow = this._narrow;
    }
  }

  _renderEmpty() {
    return `
      <div class="card empty">
        <ha-icon icon="mdi:pool"></ha-icon>
        <h2>No Pool IQ device set up yet</h2>
        <p>Add one under <a href="/config/integrations/integration/pooliq">Settings → Devices &amp; services → Pool IQ</a>.</p>
      </div>`;
  }

  _renderDevice(d) {
    const r = d.readings;
    // Pool probe (B) first when labelled; skip probes the device doesn't report.
    const temps = [r.temp_b, r.temp_a].filter((eid) => eid && this._value(eid));
    const stale = !d.last_update_success;

    const tempTiles = temps
      .map((eid) => {
        const { num, unit } = this._fmtNumber(eid);
        return `
          <button class="temp" data-action="more-info" data-entity="${esc(eid)}">
            <div class="temp-label">${esc(this._shortName(eid))}</div>
            <div class="temp-value">${esc(num)}<span>${esc(unit)}</span></div>
          </button>`;
      })
      .join("");

    const stat = (eid, label, icon) => {
      if (!eid) return "";
      const st = this._value(eid);
      if (!st) return ""; // not reported by this device
      let text = st.state;
      if (st && st.attributes.unit_of_measurement) text += ` ${st.attributes.unit_of_measurement}`;
      if (eid === r.fault && st) text = Number(st.state) === 0 ? "OK" : `Code ${st.state}`;
      if (eid === r.pump && st) text = st.state === "on" ? "Running" : "Stopped";
      if (eid === r.work_mode && st && /^(null|none)$/i.test(st.state)) text = "Normal";
      const warn =
        (eid === r.fault && st && Number(st.state) !== 0) ||
        (eid === r.fault_text && st && !["OK", "unknown", "unavailable"].includes(st.state));
      return `
        <button class="stat ${warn ? "warn" : ""}" data-action="more-info" data-entity="${esc(eid)}">
          <ha-icon icon="${icon}"></ha-icon>
          <div><div class="stat-label">${esc(label)}</div><div class="stat-value">${esc(text)}</div></div>
        </button>`;
    };

    // Salt test runs from a button right next to the salt reading.
    const withTest = (html) => html && r.salt_test
      ? `<div class="stat-with-act">${html}
          <button class="act small ${this._busy.has(r.salt_test) ? "busy" : ""}" data-action="press"
            data-entity="${esc(r.salt_test)}"><ha-icon icon="mdi:shaker-outline"></ha-icon><span>Run test</span></button>
        </div>`
      : html;

    const stats = [
      // The salt test result is the figure the unit and app show; the live reading
      // is only a fallback until the first test result arrives.
      // Salt is the salt test result only (the figure the unit and app show).
      r.salt_test_result
        ? withTest(this._value(r.salt_test_result)
            ? stat(r.salt_test_result, "Salt", "mdi:shaker-outline")
            : `<button class="stat untested" data-action="more-info" data-entity="${esc(r.salt_test_result)}">
                 <ha-icon icon="mdi:shaker-outline"></ha-icon>
                 <div><div class="stat-label">Salt</div><div class="stat-value">Not tested</div></div>
               </button>`)
        : stat(r.salt, "Salt", "mdi:shaker-outline"),
      stat(r.output, "Chlorinator output", "mdi:water-percent"),
      stat(r.cell, "Cell", "mdi:flash-outline"),
      stat(r.pump, "Chlorinator pump", "mdi:pump"),
      stat(r.power_pack, "Power pack", "mdi:thermometer"),
      stat(r.work_mode, "Work mode", "mdi:cog-outline"),
      r.fault_text
        ? stat(r.fault_text, "Faults", "mdi:alert-circle-outline")
        : stat(r.fault, "Faults", "mdi:alert-circle-outline"),
    ].join("");

    const sockets = d.sockets.length
      ? d.sockets.map((s) => this._renderSocket(s)).join("")
      : `<div class="hint">No sockets reported yet. Toggle each socket once in the Pool IQ app and they will appear here within a few minutes.</div>`;

    const dev = d.device_id && this._hass.devices && this._hass.devices[d.device_id];
    const title = (dev && (dev.name_by_user || dev.name)) || d.title;
    const devLink = d.device_id
      ? `<a class="link" href="/config/devices/device/${esc(d.device_id)}">Device page</a>`
      : "";

    return `
      <section class="device">
        <div class="device-head">
          <div>
            <h1>${esc(title)}</h1>
            <div class="sub">${d.sw_version ? `Firmware ${esc(d.sw_version)} · ` : ""}${
              stale ? `<span class="bad">Cloud not reachable, showing last known values</span>` : "Connected"
            }</div>
          </div>
          ${devLink}
        </div>
        <div class="temps">${tempTiles || `<div class="hint">No temperature readings yet.</div>`}</div>
        ${stats.trim() ? `<div class="card stats">${stats}</div>` : ""}
        ${r.mode ? this._renderChlorinator(r) : ""}
        ${d.sockets.length || !r.mode ? `<h2 class="section">Equipment</h2>
        <div class="grid">${sockets}</div>` : ""}
      </section>`;
  }

  _renderChlorinator(r) {
    const val = (eid) => this._value(eid);
    const mode = val(r.mode);
    const special = val(r.special);
    const cell = val(r.cell);
    const out = this._fmtNumber(r.output);
    const set = val(r.setpoint);
    const work = val(r.work_mode_ctl);
    const busy = (eid) => (eid && this._busy.has(eid)) ? "busy" : "";
    const specialText = special ? special.state : "Normal";
    const boosting = specialText === "Boost";

    let status = mode ? `Mode ${mode.state}` : "";
    if (specialText !== "Normal") status = specialText;
    else if (cell) status += ` · cell ${cell.state.toLowerCase()}`;

    const segment = (eid, label, options) => eid
      ? `<div class="seg-row"><span class="stat-label">${esc(label)}</span>
          <div class="seg ${busy(eid)}" role="group" aria-label="${esc(label)}">${options.map(
          (m) => `<button class="${val(eid) && val(eid).state === m ? "sel" : ""}" data-action="mode"
                   data-entity="${esc(eid)}" data-option="${m}">${m}</button>`).join("")}</div></div>`
      : "";

    const appliesTo = set && set.attributes.applies_to;
    const outLabel = appliesTo && appliesTo !== "Normal" ? `${appliesTo} output` : "Output";

    const action = (eid, label, icon) => eid
      ? `<button class="act ${busy(eid)}" data-action="press" data-entity="${esc(eid)}">
           <ha-icon icon="${icon}"></ha-icon><span>${esc(label)}</span></button>` : "";

    const phSwitch = this._st(r.ph);
    const phOn = phSwitch && phSwitch.state === "on";
    const dosing = val(r.ph_status) && val(r.ph_status).state === "on";
    const left = val(r.ph_left);
    const leftNum = left ? Number(left.state) : 0;
    const running = Number.isFinite(leftNum) && leftNum > 0;
    // Compact stepper: value and unit on top, label underneath.
    const mini = (eid, label, unit, delta) => {
      if (!eid) return "";
      const st = val(eid);
      return `<div class="mini ${busy(eid)}">
        <div class="mini-row">
          <button class="step sm" data-action="nudge" data-entity="${esc(eid)}" data-delta="-${delta}" aria-label="Lower ${esc(label)}">−</button>
          <span class="mini-val">${esc(st ? Math.round(Number(st.state)) : "–")}<small> ${esc(unit)}</small></span>
          <button class="step sm" data-action="nudge" data-entity="${esc(eid)}" data-delta="${delta}" aria-label="Raise ${esc(label)}">+</button>
        </div>
        <div class="stat-label">${esc(label)}</div>
      </div>`;
    };
    const phBlock = r.ph
      ? `<div class="ph">
          <div class="ph-head">
            <span class="ph-title"><ha-icon icon="mdi:beaker-outline"></ha-icon> pH dosing
              <span class="sub">${phOn ? (running ? `dosing · ${esc(left.state)} left` : dosing ? "pump running" : "on") : "off"}</span></span>
            <button class="toggle ${phOn ? "on" : ""} ${busy(r.ph)}" data-action="switch" data-entity="${esc(r.ph)}"
              role="switch" aria-checked="${phOn}" aria-label="pH dosing"><span class="pill"><span></span></span></button>
          </div>
          ${phOn ? `<div class="ph-body">
            ${mini(r.ph_runtime, "pH1 run time", "min/day", 1)}
            ${mini(r.ph_amount, "pH2 prime amount", "ml", 10)}
            <div class="ph-go">
              ${running ? action(r.ph_stop, "Stop pH dose", "mdi:stop-circle-outline")
                        : action(r.ph_start, "Start pH dose", "mdi:play-circle-outline")}
            </div>
          </div>` : ""}
        </div>`
      : "";

    return `
      <h2 class="section">Chlorinator</h2>
      <div class="card chlor ${boosting ? "boost" : ""}">
        <div class="chlor-top">
          <button class="chlor-out" data-action="more-info" data-entity="${esc(r.output || "")}">
            <div class="stat-label">Actual output</div>
            <div class="temp-value">${esc(out.num)}<span>${esc(out.unit || "%")}</span></div>
            <div class="sub">${esc(status)}</div>
          </button>
          <div class="chlor-ctl">
            ${segment(r.mode, "Power", ["On", "Off", "Auto"])}
            ${segment(r.work_mode_ctl, "Mode", ["Normal", "Winter", "Spa"])}
            ${r.setpoint ? `<div class="setpoint ${busy(r.setpoint)}">
              <span class="stat-label">${esc(outLabel)}</span>
              <button class="step" data-action="nudge" data-entity="${esc(r.setpoint)}" data-delta="-5" aria-label="Lower">−</button>
              <span class="set-val">${esc(set ? Math.round(Number(set.state)) : "–")}%</span>
              <button class="step" data-action="nudge" data-entity="${esc(r.setpoint)}" data-delta="5" aria-label="Raise">+</button>
            </div>` : ""}
            <div class="wide">
              ${boosting ? action(r.boost_stop, "Stop boost", "mdi:stop-circle-outline")
                         : action(r.boost_start, "Start boost", "mdi:rocket-launch")}
            </div>
          </div>
        </div>
        ${phBlock}
      </div>`;
  }

  _renderSocket(s) {
    const sw = this._st(s.switch);
    const mode = this._st(s.mode);
    const name = this._shortName(s.switch, s.socket);
    const on = sw && sw.state === "on";
    const unavailable = !sw || sw.state === "unavailable";
    const busy = this._busy.has(s.switch) || this._busy.has(s.mode);
    const current = mode && mode.state;
    const timers = (sw && sw.attributes.timers) || [];
    const kind = this._isLight(name) ? "light" : "power";

    let status = "Unavailable";
    if (!unavailable) {
      if (current === "Auto") status = `Auto · ${on ? "running on timer" : "idle"}`;
      else status = on ? "On" : "Off";
    }

    const seg = s.mode
      ? `<div class="seg" role="group" aria-label="Mode">${MODES.map(
          (m) =>
            `<button class="${current === m ? "sel" : ""}" data-action="mode" data-entity="${esc(
              s.mode
            )}" data-option="${m}" ${unavailable ? "disabled" : ""}>${m}</button>`
        ).join("")}</div>`
      : "";

    return `
      <div class="tile ${on ? "on" : ""} ${kind} ${busy ? "busy" : ""} ${unavailable ? "na" : ""}">
        <button class="tile-main" data-action="toggle" data-entity="${esc(s.switch)}" ${unavailable ? "disabled" : ""}>
          <span class="bubble"><ha-icon icon="${this._icon(name)}"></ha-icon></span>
          <span class="tile-text">
            <span class="tile-name">${esc(name)}</span>
            <span class="tile-status">${esc(busy ? "Sending…" : status)}</span>
          </span>
          <span class="pill" aria-hidden="true"><span></span></span>
        </button>
        ${seg}
        <div class="tile-foot">
          <span>${timers.length ? `Timer ${esc(timers.join(", "))}` : "No timer"}</span>
          <button class="info" data-action="more-info" data-entity="${esc(s.switch)}" aria-label="Details">
            <ha-icon icon="mdi:information-outline"></ha-icon>
          </button>
        </div>
      </div>`;
  }
}

const STYLES = `
  :host {
    display: block;
    min-height: 100vh;
    background: var(--primary-background-color);
    color: var(--primary-text-color);
    font-family: var(--paper-font-body1_-_font-family, inherit);
    --pq-card: var(--ha-card-background, var(--card-background-color, #fff));
    --pq-radius: var(--ha-card-border-radius, 12px);
    --pq-border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--divider-color, #e0e0e0));
    --pq-accent: var(--primary-color, #03a9f4);
    --pq-light: var(--state-light-on-color, var(--amber-color, #ffb300));
    --pq-power: var(--state-switch-on-color, var(--pq-accent));
  }
  * { box-sizing: border-box; }
  button { font: inherit; color: inherit; background: none; border: 0; padding: 0; cursor: pointer; text-align: left; }
  button:disabled { cursor: default; }
  a { color: var(--pq-accent); }
  .toolbar {
    display: flex; align-items: center; gap: 8px;
    height: var(--header-height, 56px); padding: 0 12px;
    background: var(--app-header-background-color, var(--primary-color));
    color: var(--app-header-text-color, #fff);
    border-bottom: var(--app-header-border-bottom, none);
    position: sticky; top: 0; z-index: 2;
  }
  .title { font-size: 20px; font-weight: 400; margin-left: 4px; }
  .content { max-width: 1100px; margin: 0 auto; padding: 16px; }
  .banner { background: var(--error-color, #db4437); color: #fff; padding: 10px 14px; border-radius: var(--pq-radius); margin-bottom: 16px; }
  .card { background: var(--pq-card); border: var(--pq-border); border-radius: var(--pq-radius); box-shadow: var(--ha-card-box-shadow, none); }
  .empty { text-align: center; padding: 48px 16px; color: var(--secondary-text-color); }
  .empty ha-icon { --mdc-icon-size: 48px; color: var(--pq-accent); }
  .device + .device { margin-top: 40px; }
  .device-head { display: flex; justify-content: space-between; align-items: flex-end; gap: 12px; margin: 4px 0 16px; }
  h1 { font-size: 24px; font-weight: 500; margin: 0; }
  .sub { color: var(--secondary-text-color); font-size: 14px; margin-top: 2px; }
  .bad { color: var(--error-color, #db4437); }
  .link { font-size: 14px; white-space: nowrap; }
  .temps { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 12px; }
  .temp {
    background: var(--pq-card); border: var(--pq-border); border-radius: var(--pq-radius);
    padding: 18px 20px; position: relative; overflow: hidden;
  }
  .temp::after {
    content: ""; position: absolute; inset: auto -40px -60px auto; width: 160px; height: 160px; border-radius: 50%;
    background: radial-gradient(circle, color-mix(in srgb, var(--pq-accent) 28%, transparent), transparent 70%);
    pointer-events: none;
  }
  .temp-label { color: var(--secondary-text-color); font-size: 14px; }
  .temp-value { font-size: 44px; font-weight: 300; line-height: 1.1; margin-top: 6px; letter-spacing: -1px; }
  .temp-value span { font-size: 20px; margin-left: 4px; color: var(--secondary-text-color); letter-spacing: 0; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 4px; padding: 8px; }
  .stat { display: flex; align-items: center; gap: 12px; padding: 10px; border-radius: 10px; }
  .stat:hover, .temp:hover { background: color-mix(in srgb, var(--primary-text-color) 4%, var(--pq-card)); }
  .stat ha-icon { color: var(--secondary-text-color); }
  .stat.warn ha-icon, .stat.warn .stat-value { color: var(--error-color, #db4437); }
  .stat-label { font-size: 12px; color: var(--secondary-text-color); }
  .stat-value { font-size: 15px; font-weight: 500; }
  .section { font-size: 16px; font-weight: 500; margin: 24px 4px 12px; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: .6px; }
  .chlor { padding: 16px; display: flex; flex-direction: column; gap: 14px; }
  .chlor.boost { box-shadow: 0 0 0 1px color-mix(in srgb, var(--pq-accent) 40%, transparent), 0 8px 28px -10px color-mix(in srgb, var(--pq-accent) 60%, transparent); }
  .chlor-top { display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap; align-items: center; }
  .chlor-out { min-width: 160px; }
  .chlor-ctl { display: flex; flex-direction: column; gap: 10px; min-width: 240px; flex: 1; max-width: 360px; }
  .setpoint { display: flex; align-items: center; gap: 10px; justify-content: space-between; }
  .setpoint.busy, .chip.busy, .act.busy { opacity: .6; }
  .step { width: 36px; height: 36px; border-radius: 50%; text-align: center; font-size: 20px; line-height: 36px;
    background: color-mix(in srgb, var(--secondary-text-color) 12%, transparent); }
  .set-val { font-size: 20px; font-weight: 500; min-width: 56px; text-align: center; }
  .chips, .actions { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip, .act { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: 18px; font-size: 14px;
    background: color-mix(in srgb, var(--secondary-text-color) 10%, transparent); color: var(--secondary-text-color); }
  .chip ha-icon, .act ha-icon { --mdc-icon-size: 18px; }
  .chip.on { background: color-mix(in srgb, var(--pq-accent) 18%, transparent); color: var(--pq-accent); }
  .act { color: var(--primary-text-color); border: var(--pq-border); background: none; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
  .hint { color: var(--secondary-text-color); padding: 12px 4px; }
  .tile {
    --c: var(--pq-power);
    background: var(--pq-card); border: var(--pq-border); border-radius: var(--pq-radius);
    padding: 12px; display: flex; flex-direction: column; gap: 10px;
    transition: box-shadow .25s, border-color .25s;
  }
  .tile.light { --c: var(--pq-light); }
  .tile.on {
    border-color: color-mix(in srgb, var(--c) 55%, transparent);
    box-shadow: 0 0 0 1px color-mix(in srgb, var(--c) 25%, transparent), 0 6px 24px -8px color-mix(in srgb, var(--c) 55%, transparent);
  }
  .tile.na { opacity: .55; }
  .tile.busy { opacity: .75; }
  .tile-main { display: flex; align-items: center; gap: 12px; width: 100%; }
  .bubble {
    width: 42px; height: 42px; border-radius: 50%; display: grid; place-items: center; flex: none;
    background: color-mix(in srgb, var(--secondary-text-color) 12%, transparent); color: var(--secondary-text-color);
    transition: background .25s, color .25s;
  }
  .tile.on .bubble { background: color-mix(in srgb, var(--c) 20%, transparent); color: var(--c); }
  .tile-text { display: flex; flex-direction: column; flex: 1; min-width: 0; }
  .tile-name { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .tile-status { font-size: 13px; color: var(--secondary-text-color); }
  .pill { width: 40px; height: 22px; border-radius: 11px; flex: none; position: relative;
    background: color-mix(in srgb, var(--secondary-text-color) 30%, transparent); transition: background .2s; }
  .pill span { position: absolute; top: 3px; left: 3px; width: 16px; height: 16px; border-radius: 50%; background: #fff; transition: transform .2s; box-shadow: 0 1px 2px rgba(0,0,0,.3); }
  .tile.on .pill { background: var(--c); }
  .tile.on .pill span { transform: translateX(18px); }
  .seg-row { display: flex; flex-direction: column; gap: 4px; }
  .ph { border-top: 1px solid var(--divider-color, rgba(127,127,127,.25)); margin-top: 14px; padding-top: 12px; }
  .ph-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .ph-title { display: flex; align-items: center; gap: 8px; font-weight: 500; }
  .ph-title .sub { font-weight: 400; opacity: .7; }
  .toggle { display: flex; align-items: center; background: none; border: 0; padding: 4px; cursor: pointer; color: inherit; }
  .toggle.on .pill { background: var(--primary-color, #03a9f4); }
  .toggle.on .pill span { transform: translateX(18px); }
  .ph-body { display: flex; flex-wrap: wrap; align-items: center; gap: 12px 24px; margin-top: 12px; }
  .mini { display: flex; flex-direction: column; align-items: center; gap: 2px; flex: 1 1 140px; }
  .mini-row { display: flex; align-items: center; gap: 10px; }
  .mini-val { font-size: 20px; font-weight: 500; min-width: 72px; text-align: center; white-space: nowrap; }
  @media (max-width: 520px) {
    .ph-body { gap: 12px 8px; }
    .mini-row { gap: 6px; }
    .ph-body .ph-go { flex-basis: 100%; margin-left: 0; }
    .ph-body .ph-go .act { width: 100%; justify-content: center; box-sizing: border-box; }
  }
  .mini-val small { font-size: 12px; opacity: .7; font-weight: 400; }
  .step.sm { width: 30px; height: 30px; line-height: 30px; font-size: 18px; }
  .ph-go { flex: 0 0 auto; margin-left: auto; }
  .wide .act { width: 100%; justify-content: center; box-sizing: border-box; }
  .stat-with-act { display: flex; align-items: center; gap: 6px; grid-column: span 2; }
  .stat-with-act .stat { flex: 1; min-width: 0; }
  .stat.untested .stat-value { opacity: .65; font-style: italic; white-space: nowrap; }
  .act.small { padding: 6px 10px; font-size: 13px; flex: none; }
  .act.small ha-icon { --mdc-icon-size: 16px; }
  .set-val small { font-size: 12px; opacity: .7; }
  .seg { display: grid; grid-template-columns: repeat(3, 1fr); border-radius: 8px; padding: 2px;
    background: color-mix(in srgb, var(--secondary-text-color) 10%, transparent); }
  .seg button { text-align: center; padding: 5px 0; border-radius: 6px; font-size: 13px; color: var(--secondary-text-color); }
  .seg button.sel { background: var(--pq-card); color: var(--primary-text-color); font-weight: 500; box-shadow: 0 1px 3px rgba(0,0,0,.18); }
  .tile-foot { display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: var(--secondary-text-color); }
  .info ha-icon { --mdc-icon-size: 18px; color: var(--secondary-text-color); }
  @media (max-width: 600px) {
    .content { padding: 12px; }
    .temp-value { font-size: 38px; }
    .grid { grid-template-columns: 1fr; }
  }
`;

if (!customElements.get("pooliq-panel")) {
  customElements.define("pooliq-panel", PoolIQPanel);
}
