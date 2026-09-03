const NativeDate = Date;
const fixedNow = NativeDate.parse("2026-09-03T18:30:00Z");

const showFailure = (reason) => {
  document.documentElement.dataset.screenshotError = String(reason);
};
window.addEventListener("error", (event) => showFailure(event.error || event.message));
window.addEventListener("unhandledrejection", (event) => showFailure(event.reason));

class FixedDate extends NativeDate {
  constructor(...args) {
    super(...(args.length ? args : [fixedNow]));
  }

  static now() {
    return fixedNow;
  }
}

window.Date = FixedDate;

class SyntheticHaIcon extends HTMLElement {
  connectedCallback() {
    const icon = this.getAttribute("icon") || "";
    this.textContent = icon.includes("fullscreen") ? "⛶" : icon.includes("home") ? "⌂" : "";
    this.style.textAlign = "center";
  }
}

customElements.define("ha-icon", SyntheticHaIcon);

const { screenshotFixture } = await import("./fixture.js");
await import("/meshmonitor_panel/meshmonitor-panel.js");

const params = new URLSearchParams(location.search);
const tab = params.get("tab") || "overview";
const panel = document.querySelector("meshmonitor-panel-20260902-0003");
const hass = {
  config: { latitude: 39.74, longitude: -104.99 },
  themes: { darkMode: true },
  callWS: async (request) => {
    if (request.type === "meshmonitor/panel") return structuredClone(screenshotFixture);
    if (request.type === "meshmonitor/notification_settings") {
      return { enabled: false, scope: "all", include_preview: false, targets: [] };
    }
    throw new Error(`Unhandled synthetic WebSocket request: ${request.type}`);
  },
};

panel.hass = hass;
const waitFor = (predicate, label) => new Promise((resolve, reject) => {
  const started = performance.now();
  const check = () => {
    if (predicate()) resolve();
    else if (performance.now() - started > 10000) {
      reject(new Error(`Timed out waiting for synthetic ${label}`));
    } else requestAnimationFrame(check);
  };
  check();
});
await waitFor(
  () => panel._data && panel.shadowRoot?.querySelector("#panel-view"),
  "panel data",
);
panel._tab = tab;
if (tab === "messages") panel._conversation = "channel:meshcore:0";
if (tab === "map") panel._mapStyle = "tiles-off";
panel._render();
const readySelector = {
  overview: ".overview",
  messages: ".conversation-shell",
  nodes: ".nodes-table",
};
if (tab === "map") {
  await waitFor(
    () => panel._mapInstance && panel.shadowRoot?.querySelector(".leaflet-marker-pane"),
    "map initialization",
  );
} else {
  await waitFor(
    () => panel.shadowRoot?.querySelector(readySelector[tab]),
    `${tab} view`,
  );
}
await new Promise((resolve) => setTimeout(resolve, 250));
if (tab === "messages") {
  const timeline = panel.shadowRoot.querySelector(".messages");
  timeline.scrollTop = 0;
  timeline.dispatchEvent(new Event("scroll"));
}
document.documentElement.dataset.screenshotReady = "true";
