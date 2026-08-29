import {
  nodeActivity,
  relativeNodeActivity,
  relativeNodeTime,
  sortNodes,
} from "./node-table.js?v=20260823-1120";
import {
  batteryPresentation,
  hardwareModelLabel,
  nodeDetailPresentation,
  nodeHistoryStatePresentation,
  nodeRoleModelLabel,
  normalizeHistoryPoints,
  sparklinePoints,
  telemetrySeries,
} from "./node-detail.js?v=20260823-1453";
import {
  overviewAttentionItems,
  overviewHealthPresentation,
  overviewLifecyclePresentation,
  overviewSummary,
} from "./overview.js?v=20260820-1912";
import {
  automationOverviewSummary,
  automationRunPresentation,
  automationStatePresentation,
  sortedAutomationRuns,
} from "./automation-view.js";
import {
  MAP_STYLES,
  homeLocation,
  mapCountLabel,
  mapEmptyPresentation,
  mapLayerSummary,
  mapStylePresentation,
  nodeIsVisibleOnMap,
  persistMapStyle,
  persistShowHome,
  readMapStyle,
  readShowHome,
} from "./map-view.js?v=20260829-0803";
import {
  reticulumCardPresentation,
  sourceCardPresentation,
} from "./source-view.js?v=20260822-1242";
import { serverCardPresentation } from "./server-view.js?v=20260820-1810";
import {
  conversationSourceChoices,
  conversationUnreadCounts,
  messageDraftValidation,
  messageConversationCatalog,
  messageConversationKey,
  messagePresentation,
  messageSendNonce,
  messageTimestampMs,
  sortMessagesChronologically,
  sendErrorPresentation,
} from "./message-view.js?v=20260823-1752";
import {
  PANEL_TABS,
  adjacentPanelTab,
  notificationDeepLink,
  normalizePanelTab,
} from "./panel-navigation.js?v=20260822-1545";

const sourceSelectionKey = (source) =>
  `${encodeURIComponent(source.entry_id || "")}|${encodeURIComponent(source.source_id || "")}`;

const escapeHtml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

const batteryMarkup = (level, voltage = null, fallback = "—") => {
  const battery = batteryPresentation(level, voltage);
  if (!battery) return escapeHtml(fallback);
  return `<span class="battery-value ${battery.tone}"><ha-icon icon="${battery.icon}" aria-hidden="true"></ha-icon><span>${escapeHtml(battery.label)}</span></span>`;
};

const nodeListBatteryMarkup = (level) => {
  const battery = batteryPresentation(level);
  if (!battery?.percentLabel) return "—";
  return `<span class="battery-value ${battery.tone}"><ha-icon icon="${battery.icon}" aria-hidden="true"></ha-icon><span>${escapeHtml(battery.percentLabel)}</span></span>`;
};

const nodeDetailBatteryMarkup = (level, voltage = null) => {
  const battery = batteryPresentation(level, voltage);
  if (!battery) return "<span class=\"power-unreported\">Not reported</span>";
  const primary = battery.percentLabel || battery.voltageLabel;
  const secondary = battery.percentLabel ? battery.voltageLabel : null;
  return `<span class="power-value battery-value ${battery.tone}"><ha-icon icon="${battery.icon}" aria-hidden="true"></ha-icon><span class="power-reading"><span class="power-primary">${escapeHtml(primary)}</span>${secondary ? `<span class="power-voltage">${escapeHtml(secondary)}</span>` : ""}</span></span>`;
};

const advertErrorPresentation = (error) => {
  const messages = {
    permission_denied: "The MeshMonitor account lacks connection:write permission.",
    transmit_disabled: "Outbound radio actions are disabled for this source.",
    rate_limited: "An advert was already attempted recently. Wait five minutes.",
    duplicate: "This advert activation was blocked from replay.",
    protocol_mismatch: "The selected source is no longer MeshCore.",
    not_found: "The selected MeshCore source is no longer available.",
    invalid_auth: "MeshMonitor authentication failed. Reauthenticate before trying again.",
    advert_failed: "MeshMonitor rejected the advert. No retry was attempted.",
  };
  return messages[error?.code] || error?.message || "The advert was blocked. No retry was attempted.";
};

const readableTime = (value) => {
  if (value === null || value === undefined) return "Unknown";
  const date =
    typeof value === "number"
      ? new Date(value > 1e11 ? value : value * 1000)
      : new Date(value);
  return Number.isNaN(date.valueOf()) ? "Unknown" : date.toLocaleString();
};

class MeshMonitorPanel extends HTMLElement {
  set route(value) {
    this._route = value;
    if (this.shadowRoot) this._applyNotificationDeepLink();
  }

  set hass(value) {
    this._hass = value;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this._tab = normalizePanelTab("overview");
      this._query = "";
      this._nodeProtocol = "all";
      this._nodeFavorite = "all";
      this._nodePosition = "all";
      const savedNodeSort = localStorage.getItem("meshmonitor.nodes.sort");
      this._nodeSort = savedNodeSort || "last_heard";
      this._nodeDirection =
        localStorage.getItem("meshmonitor.nodes.direction") ||
        (savedNodeSort ? "asc" : "desc");
      this._messageQuery = "";
      this._messageProtocol = "all";
      this._messageSource = "all";
      this._messageScope = "all";
      this._messageUnread = false;
      this._messageFavorite = false;
      this._messageSort = localStorage.getItem("meshmonitor.messages.sort") || "newest";
      this._conversation = localStorage.getItem("meshmonitor.messages.conversation") || "all";
      const notificationLink = notificationDeepLink(window.location.search);
      if (notificationLink) {
        this._tab = "messages";
        this._conversation = notificationLink.conversation;
      }
      this._linkedMessageId = notificationLink?.messageId || "";
      this._pinnedConversations = new Set(JSON.parse(localStorage.getItem("meshmonitor.messages.pinned") || "[]"));
      this._mutedConversations = new Set(JSON.parse(localStorage.getItem("meshmonitor.messages.muted") || "[]"));
      this._messageScrollByConversation = new Map();
      this._conversationRailScroll = 0;
      this._messageScrollRestoreGeneration = 0;
      this._messageDrafts = new Map();
      this._composeSource = "";
      this._composeText = "";
      this._replyContext = null;
      this._sending = false;
      this._sendStatus = "";
      this._pendingMessages = [];
      this._notificationSettings = null;
      this._notificationDialogOpen = false;
      this._notificationSaving = false;
      this._notificationError = "";
      this._advertReview = null;
      this._advertSending = false;
      this._advertStatus = "";
      this._mapProtocol = "all";
      this._mapSource = "all";
      this._mapFreshness = "all";
      this._mapStyle = readMapStyle(localStorage);
      this._mapShowHome = readShowHome(localStorage);
      this._mapTopology =
        localStorage.getItem("meshmonitor.map.topology") !== "false";
      this._mapNeighbors =
        localStorage.getItem("meshmonitor.map.neighbors") !== "false";
      this._positionRange = 24;
      this._positionTrail = null;
      this._positionIndex = 0;
      this._positionLoading = false;
      this._positionPlaying = false;
      this._nodeDetail = null;
      this._nodeActionStatus = "";
      this._nodeActionPending = "";
      this._nodeIgnoreReview = false;
      this._nodeDirectTarget = null;
      this._mapFocusNode = null;
      this._nodeHistory = null;
      this._nodeHistoryHours = 24;
      this._nodeHistoryLoading = false;
      this._nodeHistoryError = "";
      this._nodeHistoryGeneration = 0;
      this._favoritePending = new Set();
      this._favoriteOverrides = new Map();
      this._lastRead = Number(
        localStorage.getItem("meshmonitor.messages.lastRead") || 0,
      );
      try {
        const savedConversationReads = JSON.parse(
          localStorage.getItem("meshmonitor.messages.lastReadByConversation") || "{}",
        );
        this._conversationLastRead =
          savedConversationReads && !Array.isArray(savedConversationReads)
            ? savedConversationReads
            : {};
      } catch {
        this._conversationLastRead = {};
      }
      this.shadowRoot.addEventListener("click", (event) => {
        const reply = event.target.closest?.("[data-reply-message]");
        if (reply) {
          this._activateMessageReply(reply.dataset.replyMessage);
          return;
        }
        const message = event.target.closest?.("[data-open-conversation]");
        if (message)
          this._selectConversation(message.dataset.openConversation);
      });
      this.shadowRoot.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        const message = event.target.closest?.("[data-open-conversation]");
        if (!message) return;
        event.preventDefault();
        this._selectConversation(message.dataset.openConversation);
      });
      this._load();
    }
    this._startTimers();
  }

  connectedCallback() {
    if (!this._locationChangedHandler) {
      this._locationChangedHandler = () => this._applyNotificationDeepLink();
      window.addEventListener("location-changed", this._locationChangedHandler);
      window.addEventListener("popstate", this._locationChangedHandler);
    }
    this._startTimers();
    if (this._data) this._load();
  }

  _startTimers() {
    if (!this.isConnected) return;
    if (!this._timer)
      this._timer = window.setInterval(() => this._load(), 30000);
    if (!this._relativeTimeTimer)
      this._relativeTimeTimer = window.setInterval(() => {
        this._refreshNodeTimes();
        if (this._tab === "overview") this._render();
      }, 15000);
  }

  disconnectedCallback() {
    if (this._locationChangedHandler) {
      window.removeEventListener("location-changed", this._locationChangedHandler);
      window.removeEventListener("popstate", this._locationChangedHandler);
      this._locationChangedHandler = null;
    }
    window.clearInterval(this._timer);
    window.clearInterval(this._relativeTimeTimer);
    this._timer = null;
    this._relativeTimeTimer = null;
    this._stopPositionPlayback();
    this._destroyMap();
  }

  async _load() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    if (!this._data) this._render();
    try {
      const data = await this._hass.callWS({ type: "meshmonitor/panel" });
      this._applyFavoriteOverrides(data);
      this._data = data;
      if (this._notificationSettings === null)
        await this._loadNotificationSettings();
      this._error = null;
    } catch (error) {
      this._error = error?.message || String(error);
    } finally {
      this._loading = false;
      this._render();
    }
  }

  _allNodes() {
    return (this._data?.sources || []).flatMap((source) => source.nodes);
  }

  _allMapNodes() {
    return (this._data?.sources || []).flatMap((source) => [
      ...(source.nodes || []).filter(nodeIsVisibleOnMap),
      ...(source.protocol === "reticulum"
        ? (source.reticulum?.peers || []).map((peer) => ({
            ...peer,
            entry_id: source.entry_id,
            source_id: source.source_id,
            source_name: source.name,
            protocol: "reticulum",
            last_heard: peer.last_seen,
            role: peer.app_name || "LXMF destination",
          }))
        : []),
    ]);
  }

  _applyFavoriteOverrides(data) {
    const nodes = (data?.sources || []).flatMap((source) => source.nodes);
    for (const [favoriteKey, favorite] of this._favoriteOverrides) {
      const [entryId, sourceId, nodeId] = favoriteKey.split("\u0000");
      const node = nodes.find(
        (item) => item.entry_id === entryId && item.source_id === sourceId && item.id === nodeId,
      );
      if (!node) continue;
      if (Boolean(node.favorite) === favorite) this._favoriteOverrides.delete(favoriteKey);
      else node.favorite = favorite;
    }
  }

  _rememberConversationView() {
    const timeline = this.shadowRoot?.querySelector(".messages");
    if (timeline) {
      const key = timeline.dataset.conversation || "all";
      this._messageScrollByConversation.set(key, {
        atBottom:
          timeline.scrollHeight - timeline.clientHeight - timeline.scrollTop <
          48,
        top: timeline.scrollTop,
      });
    }
    const rail = this.shadowRoot?.querySelector(".conversation-rail");
    if (rail)
      this._conversationRailScroll = {
        left: rail.scrollLeft,
        top: rail.scrollTop,
      };
  }

  _restoreConversationView() {
    const generation = ++this._messageScrollRestoreGeneration;
    window.requestAnimationFrame(() => {
      if (generation !== this._messageScrollRestoreGeneration) return;
      const timeline = this.shadowRoot?.querySelector(".messages");
      if (timeline) {
        const saved = this._messageScrollByConversation.get(
          timeline.dataset.conversation || "all",
        );
        timeline.scrollTop = saved?.atBottom
          ? timeline.scrollHeight
          : saved?.top ?? timeline.scrollHeight;
      }
      const rail = this.shadowRoot?.querySelector(".conversation-rail");
      if (rail && this._conversationRailScroll) {
        rail.scrollLeft = this._conversationRailScroll.left || 0;
        rail.scrollTop = this._conversationRailScroll.top || 0;
      }
    });
  }

  _render() {
    if (!this.shadowRoot) return;
    this._rememberConversationView();
    this._rememberMapView();
    this._destroyMap();
    const sources = this._data?.sources || [];
    const nodes = this._allNodes();
    const messages = this._data?.messages || [];
    const positioned = this._allMapNodes().filter(
      (node) => node.latitude != null && node.longitude != null,
    );
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; min-width:0; min-height:100%; color:var(--primary-text-color); background:var(--primary-background-color); --protocol-meshtastic:#2e9b63; --protocol-meshcore:#8b5cf6; --protocol-reticulum:#3b82f6; --protocol-unknown:#7b8794; }
        * { box-sizing:border-box; }
        h1 { margin:0; font-size:28px; font-weight:650; } .muted { color:var(--secondary-text-color); }
        .tab-bar { display:flex; align-items:stretch; gap:0; padding:0 18px 0 26px; border-bottom:1px solid var(--divider-color); background:var(--sidebar-background-color,var(--card-background-color)); }
        .sidebar-toggle { display:none; flex:0 0 46px; align-items:center; justify-content:center; min-height:46px; padding:0; border:0; border-radius:0; background:transparent; box-shadow:none; }
        .sidebar-toggle ha-icon { width:24px; height:24px; }
        nav { min-width:0; flex:1 1 auto; display:flex; gap:22px; overflow-x:auto; border-right:0; box-shadow:none; scrollbar-width:none; }
        nav::-webkit-scrollbar { display:none; }
        nav button { position:relative; display:inline-flex; align-items:center; justify-content:center; gap:7px; min-height:46px; padding:10px 2px 9px; border:0; border-radius:0; background:transparent; color:var(--secondary-text-color); font-weight:600; }
        nav button::after { content:""; position:absolute; height:3px; left:0; right:0; bottom:-1px; border-radius:3px 3px 0 0; background:transparent; }
        nav button:hover:not(:disabled) { border-color:transparent; background:transparent; color:var(--primary-text-color); }
        nav button.active,nav button.active:hover:not(:disabled) { border-color:transparent; background:transparent; color:var(--primary-color); }
        nav button.active::after { background:var(--primary-color); }
        .tab-count { min-width:21px; padding:2px 6px; border-radius:999px; background:#ffffff14; font-size:11px; line-height:1.45; }
        button { border:1px solid transparent; border-radius:18px; padding:9px 15px; color:var(--primary-text-color); background:var(--secondary-background-color); cursor:pointer; font:inherit; }
        button:hover:not(:disabled) { border-color:color-mix(in srgb,var(--primary-color) 38%,var(--divider-color)); background:color-mix(in srgb,var(--secondary-background-color) 88%,var(--primary-color)); }
        button:disabled { opacity:.55; cursor:not-allowed; }
        button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible,a:focus-visible { outline:2px solid var(--primary-color); outline-offset:2px; }
        button.active { color:var(--text-primary-color); background:var(--primary-color); }
        button.active:hover:not(:disabled) { border-color:color-mix(in srgb,var(--primary-color) 55%,white); background:color-mix(in srgb,var(--primary-color) 88%,black); }
        main { padding:18px 26px 30px; max-width:1700px; margin:auto; }
        main.messages-view { width:100%; max-width:none; height:calc(100dvh - 46px); margin:0; padding:0 0 0 12px; overflow:hidden; }
        .grid { display:grid; gap:16px; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); }
        .card { background:var(--card-background-color); border-radius:14px; padding:18px; box-shadow:var(--ha-card-box-shadow,0 2px 5px #0002); }
        .section-heading { display:flex; align-items:end; justify-content:space-between; gap:18px; margin:0 0 14px; }
        .section-heading h2 { margin:4px 0 0; font-size:23px; }
        .section-heading p { max-width:700px; margin:5px 0 0; line-height:1.45; }
        .section-eyebrow { color:var(--primary-color); font-size:11px; font-weight:750; letter-spacing:.09em; text-transform:uppercase; }
        .panel-state { min-height:340px; display:grid; place-items:center; padding:30px; border:1px dashed var(--divider-color); border-radius:14px; background:var(--card-background-color); text-align:center; }
        .panel-state>div { max-width:540px; }
        .panel-state h2 { margin:7px 0 8px; }
        .panel-state p { margin:0; line-height:1.55; }
        .metric { font-size:32px; font-weight:650; margin-top:8px; }
        .source { border-left:5px solid var(--protocol-meshtastic); } .source.meshcore { border-left-color:var(--protocol-meshcore); } .source.reticulum { border-left-color:var(--protocol-reticulum); }
        .badge { display:inline-block; border:1px solid color-mix(in srgb,var(--protocol-color,var(--protocol-unknown)) 48%,var(--divider-color)); border-radius:12px; padding:3px 9px; background:color-mix(in srgb,var(--protocol-color,var(--protocol-unknown)) 14%,var(--card-background-color)); color:color-mix(in srgb,var(--protocol-color,var(--protocol-unknown)) 76%,var(--primary-text-color)); font-size:12px; font-weight:650; text-transform:capitalize; }
        .protocol-meshtastic { --protocol-color:var(--protocol-meshtastic); } .protocol-meshcore { --protocol-color:var(--protocol-meshcore); } .protocol-reticulum { --protocol-color:var(--protocol-reticulum); } .protocol-unknown { --protocol-color:var(--protocol-unknown); }
        .ok { color:var(--success-color,#43a047); } .bad { color:var(--error-color,#db4437); }
        .overview { display:grid; gap:18px; }
        .overview-hero { display:flex; align-items:start; justify-content:space-between; flex-wrap:wrap; gap:12px 22px; padding:18px 20px; border:1px solid var(--divider-color); box-shadow:none; }
        .overview-eyebrow { margin:0 0 4px; color:var(--primary-color); font-size:10px; font-weight:750; letter-spacing:.09em; text-transform:uppercase; }
        .overview-hero h2 { margin:0; font-size:24px; line-height:1.2; }
        .overview-hero p { max-width:780px; margin:5px 0 0; line-height:1.45; }
        .overview-hero-actions { display:flex; align-items:flex-end; flex-direction:column; gap:8px; }
        .overview-state { display:flex; align-items:center; gap:9px; min-width:max-content; padding:8px 12px; border-radius:999px; background:var(--secondary-background-color); font-size:12px; font-weight:700; }
        .overview-state::before { content:""; width:9px; height:9px; border-radius:50%; background:var(--success-color,#43a047); box-shadow:0 0 0 3px color-mix(in srgb,var(--success-color,#43a047) 18%,transparent); }
        .overview-state.attention::before { background:var(--warning-color,#ffb300); box-shadow:0 0 0 3px color-mix(in srgb,var(--warning-color,#ffb300) 18%,transparent); }
        .overview-state.empty::before { background:var(--secondary-text-color); box-shadow:none; }
        .overview-alerts { min-width:min(100%,300px); display:grid; gap:7px; }
        .overview-alert { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:4px 12px; padding:9px 11px; border:1px solid color-mix(in srgb,var(--warning-color,#ffb300) 38%,var(--divider-color)); border-radius:10px; background:color-mix(in srgb,var(--warning-color,#ffb300) 8%,var(--card-background-color)); text-align:left; }
        .overview-alert strong,.overview-alert small { min-width:0; overflow-wrap:anywhere; }
        .overview-alert strong { font-size:12px; }
        .overview-alert small { grid-column:1; color:var(--secondary-text-color); font-size:10px; }
        .overview-alert::after { grid-column:2; grid-row:1/3; content:"↓"; color:var(--warning-color,#ffb300); font-weight:800; }
        .overview-metrics { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; }
        .overview-metric { min-width:0; padding:17px 18px; border:1px solid var(--divider-color); box-shadow:none; }
        .overview-metric .metric { margin:5px 0 3px; font-size:29px; line-height:1; }
        .overview-metric small { color:var(--secondary-text-color); line-height:1.35; }
        .overview-section-head { display:flex; justify-content:space-between; gap:16px; align-items:end; margin-bottom:12px; }
        .overview-section-head h2 { margin:0; font-size:20px; }
        .overview-section-head p { margin:4px 0 0; }
        .overview-servers { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),360px)); justify-content:start; gap:14px; }
        .overview-server { min-width:0; padding:14px 15px; border:1px solid var(--divider-color); box-shadow:none; }
        .overview-server-head { display:flex; align-items:start; justify-content:space-between; gap:12px; }
        .overview-server-head h3 { margin:3px 0 0; overflow-wrap:anywhere; font-size:16px; }
        .server-state { display:inline-flex; align-items:center; gap:6px; flex:none; font-size:11px; font-weight:700; }
        .server-state::before { content:""; width:7px; height:7px; border-radius:50%; background:currentColor; }
        .server-versions { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; margin:13px 0 10px; }
        .server-version { min-width:0; padding:9px 10px; border-radius:9px; background:var(--secondary-background-color); }
        .server-version span,.server-meta { display:block; color:var(--secondary-text-color); font-size:11px; }
        .server-version strong { display:block; margin-top:3px; overflow-wrap:anywhere; font-size:15px; }
        .server-update { display:flex; align-items:center; justify-content:space-between; gap:10px; padding-top:10px; border-top:1px solid var(--divider-color); font-size:12px; }
        .server-update strong.attention { color:var(--warning-color,#ffb300); }
        .server-update a { color:var(--primary-color); font-weight:650; text-decoration:none; }
        .server-update a:hover { text-decoration:underline; }
        .server-meta { margin-top:7px; line-height:1.4; }
        .server-automation { margin-top:10px; padding-top:10px; border-top:1px solid var(--divider-color); }
        .server-automation span,.server-automation small { display:block; color:var(--secondary-text-color); font-size:11px; }
        .server-automation strong { display:block; margin:3px 0; font-size:12px; }
        .overview-sources { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr)); align-items:start; gap:14px; }
        .overview-source:only-child { max-width:720px; }
        .overview-source { display:flex; flex-direction:column; min-width:0; padding:0; overflow:hidden; border:1px solid var(--divider-color); box-shadow:none; }
        .overview-source.overview-source-highlight { border-color:var(--warning-color,#ffb300); box-shadow:0 0 0 3px color-mix(in srgb,var(--warning-color,#ffb300) 20%,transparent); }
        .overview-source-head { display:flex; justify-content:space-between; gap:14px; align-items:start; padding:17px 18px 13px; border-top:4px solid var(--protocol-meshtastic); }
        .overview-source.meshcore .overview-source-head { border-top-color:var(--protocol-meshcore); }
        .overview-source.reticulum .overview-source-head { border-top-color:var(--protocol-reticulum); }
        .overview-source h3 { margin:8px 0 0; overflow-wrap:anywhere; font-size:18px; }
        .source-health-state { display:flex; flex:none; flex-direction:column; align-self:stretch; align-items:flex-end; justify-content:space-between; gap:4px; text-align:right; }
        .source-state { display:flex; gap:7px; align-items:center; font-size:12px; font-weight:650; }
        .source-state::before { content:""; width:8px; height:8px; border-radius:50%; background:currentColor; }
        .source-reported { color:var(--secondary-text-color); font-size:11px; font-weight:400; line-height:1.35; }
        .source-stats { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); margin:0 18px; padding:14px 0; border-top:1px solid var(--divider-color); border-bottom:1px solid var(--divider-color); }
        .source-stat + .source-stat { border-left:1px solid var(--divider-color); padding-left:16px; }
        .source-stat strong { display:block; font-size:21px; }
        .source-stat span { color:var(--secondary-text-color); font-size:12px; }
        .source-details { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); flex:1; margin:0 18px; border-bottom:1px solid var(--divider-color); }
        .source-detail-column { min-width:0; padding:13px 16px 4px 0; }
        .source-detail-column + .source-detail-column { margin:13px 0; padding:0 0 0 16px; border-left:1px solid var(--divider-color); }
        .source-details p { margin:0 0 9px; overflow-wrap:anywhere; line-height:1.4; }
        .source-errors { margin:0; padding:11px 18px; border-bottom:1px solid var(--divider-color); }
        .firmware-state { font-size:12px; font-weight:650; }
        .firmware-state a { color:inherit; text-decoration:none; }
        .firmware-state a:hover { text-decoration:underline; }
        .source-links { display:flex; flex-wrap:wrap; gap:8px 14px; margin-top:auto; padding:11px 18px 16px; }
        .source-links a { color:var(--primary-color); font-weight:600; text-decoration:none; }
        .source-links a:hover { text-decoration:underline; }
        .advert-scrim { position:fixed; inset:0; z-index:1002; display:grid; place-items:center; padding:18px; background:#0009; }
        .advert-dialog { width:min(520px,100%); padding:0; overflow:hidden; border:1px solid var(--divider-color); border-radius:16px; background:var(--card-background-color); box-shadow:0 20px 70px #0008; }
        .advert-dialog-head { padding:20px 21px 13px; border-bottom:1px solid var(--divider-color); }
        .advert-dialog-head h2 { margin:5px 0 0; font-size:22px; }
        .advert-dialog-body { padding:18px 21px; line-height:1.5; }
        .advert-dialog-body dl { display:grid; grid-template-columns:auto minmax(0,1fr); gap:8px 14px; margin:15px 0 0; }
        .advert-dialog-body dt { color:var(--secondary-text-color); }
        .advert-dialog-body dd { margin:0; overflow-wrap:anywhere; font-weight:650; }
        .advert-dialog-actions { display:flex; justify-content:flex-end; gap:9px; padding:13px 21px 18px; }
        .advert-dialog-actions .danger { color:var(--text-primary-color); background:var(--primary-color); }
        .advert-status { margin:0 18px 14px; padding:9px 11px; border-radius:9px; background:var(--secondary-background-color); font-size:12px; }
        .overview-empty { min-height:300px; display:grid; place-items:center; text-align:center; border:1px dashed var(--divider-color); box-shadow:none; }
        .overview-empty h2 { margin:0 0 8px; }
        .overview-empty p { max-width:520px; margin:0; line-height:1.55; }
        .automation-section { display:grid; gap:12px; }
        .automation-summary { display:inline-flex; align-items:center; width:max-content; max-width:100%; padding:5px 9px; border:1px solid var(--divider-color); border-radius:999px; background:var(--secondary-background-color); color:var(--secondary-text-color); font-size:11px; font-weight:700; white-space:nowrap; }
        .automation-summary.ok,.automation-run-status.ok { color:var(--success-color,#43a047); border-color:color-mix(in srgb,var(--success-color,#43a047) 36%,var(--divider-color)); }
        .automation-summary.bad,.automation-run-status.bad { color:var(--error-color,#db4437); border-color:color-mix(in srgb,var(--error-color,#db4437) 36%,var(--divider-color)); }
        .automation-metrics { display:flex; flex-wrap:wrap; gap:8px; }
        .automation-metrics span { padding:7px 10px; border:1px solid var(--divider-color); border-radius:9px; background:color-mix(in srgb,var(--secondary-background-color) 65%,transparent); color:var(--secondary-text-color); font-size:12px; }
        .automation-metrics strong { color:var(--primary-text-color); font-size:14px; }
        .automation-groups { display:grid; gap:18px; }
        .automation-group { display:grid; gap:11px; min-width:0; }
        .automation-group-head { display:flex; align-items:end; justify-content:space-between; gap:14px; padding:0 2px; }
        .automation-group-head h3 { margin:3px 0 0; overflow-wrap:anywhere; font-size:16px; }
        .automation-notice { display:flex; align-items:baseline; gap:8px; padding:10px 12px; border:1px solid var(--divider-color); border-radius:10px; background:color-mix(in srgb,var(--secondary-background-color) 55%,transparent); font-size:12px; line-height:1.45; }
        .automation-notice.bad { border-color:color-mix(in srgb,var(--error-color,#db4437) 38%,var(--divider-color)); }
        .automation-notice span { color:var(--secondary-text-color); }
        .automation-state { min-height:150px; display:grid; place-items:center; padding:22px; border:1px dashed var(--divider-color); box-shadow:none; text-align:center; }
        .automation-state h3 { margin:0 0 7px; }
        .automation-state p { max-width:650px; margin:0; line-height:1.5; }
        .automation-state code { color:var(--primary-text-color); }
        .automation-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(330px,1fr)); gap:12px; }
        .automation-card { min-width:0; overflow:hidden; border:1px solid var(--divider-color); box-shadow:none; }
        .automation-card-head { display:flex; align-items:start; justify-content:space-between; gap:12px; padding:15px 16px 12px; border-bottom:1px solid var(--divider-color); }
        .automation-card h4 { margin:0; overflow-wrap:anywhere; font-size:16px; }
        .automation-id { display:block; margin-top:4px; color:var(--secondary-text-color); font-size:10px; overflow-wrap:anywhere; }
        .automation-description { margin:0; padding:12px 16px 2px; line-height:1.45; overflow-wrap:anywhere; }
        .automation-definition-meta { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin:0; padding:12px 16px; }
        .automation-definition-meta div { min-width:0; }
        .automation-definition-meta dt { color:var(--secondary-text-color); font-size:10px; text-transform:uppercase; letter-spacing:.05em; }
        .automation-definition-meta dd { margin:3px 0 0; overflow-wrap:anywhere; font-size:12px; }
        .automation-history { padding:12px 16px 15px; border-top:1px solid var(--divider-color); background:color-mix(in srgb,var(--secondary-background-color) 38%,transparent); }
        .automation-history h5 { margin:0 0 9px; font-size:12px; text-transform:uppercase; letter-spacing:.05em; }
        .automation-history-state { margin:0 0 8px; padding:8px 9px; border-left:3px solid var(--divider-color); background:color-mix(in srgb,var(--secondary-background-color) 64%,transparent); color:var(--secondary-text-color); font-size:11px; line-height:1.4; }
        .automation-history-state.bad { border-left-color:var(--error-color,#db4437); }
        .automation-runs { display:grid; gap:0; margin:0; padding:0; list-style:none; }
        .automation-runs li { min-width:0; display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:center; gap:8px; padding:8px 0; border-top:1px solid var(--divider-color); font-size:11px; }
        .automation-runs li:first-child { border-top:0; }
        .automation-run-status { display:inline-flex; padding:3px 6px; border:1px solid var(--divider-color); border-radius:7px; color:var(--secondary-text-color); font-weight:700; text-transform:capitalize; }
        .automation-run-source { min-width:0; overflow-wrap:anywhere; }
        .automation-runs time { color:var(--secondary-text-color); text-align:right; }
        .automation-no-runs { margin:0; font-size:12px; }
        .automation-more { margin-top:4px; }
        .automation-more summary { width:max-content; max-width:100%; padding:6px 0; color:var(--primary-color); cursor:pointer; font-size:11px; font-weight:650; }
        .automation-more summary:focus-visible { outline:2px solid var(--primary-color); outline-offset:3px; }
        .map-shell { position:relative; overflow:hidden; border:1px solid var(--divider-color); border-radius:16px; background:var(--card-background-color); box-shadow:var(--ha-card-box-shadow,0 2px 5px #0002); }
        .map-head { display:flex; align-items:center; justify-content:space-between; gap:14px; padding:15px 16px 12px; background:color-mix(in srgb,var(--card-background-color) 94%,var(--primary-color)); }
        .map-head h2 { margin:0; font-size:18px; }
        .map-head p { margin:3px 0 0; font-size:12px; }
        .map-shell:fullscreen { display:flex; flex-direction:column; width:100vw; height:100vh; border:0; border-radius:0; background:var(--primary-background-color); }
        .map-shell:fullscreen .map-canvas { flex:1; min-height:0; }
        .map-shell:fullscreen .map { height:100%; }
        .map-toolbar { display:grid; grid-template-columns:minmax(400px,1.4fr) auto minmax(260px,auto); gap:10px 18px; align-items:end; padding:13px 14px; border-bottom:1px solid var(--divider-color); background:color-mix(in srgb,var(--card-background-color) 88%,var(--primary-color)); }
        .map-control-row { display:flex; align-items:center; gap:15px; }
        .map-control-group { min-width:0; display:flex; align-items:center; gap:7px; }
        .map-control-group.filters select { flex:1; min-width:0; }
        .map-control-label { align-self:center; flex:none; margin-right:2px; color:var(--secondary-text-color); font-size:10px; font-weight:750; letter-spacing:.08em; text-transform:uppercase; }
        .map-toolbar select,.map-toolbar button { min-height:37px; padding:8px 11px; border:1px solid color-mix(in srgb,var(--divider-color) 82%,white); border-radius:10px; background:var(--secondary-background-color); box-shadow:none; }
        .map-toolbar button:hover,.map-toolbar button:focus-visible,.map-toolbar select:hover,.map-toolbar select:focus-visible { border-color:color-mix(in srgb,var(--primary-color) 55%,var(--divider-color)); background:color-mix(in srgb,var(--secondary-background-color) 88%,var(--primary-color)); }
        .map-toolbar button { display:inline-flex; align-items:center; justify-content:center; gap:6px; }
        .map-toolbar ha-icon { --mdc-icon-size:18px; }
        .map-toolbar button.active { border-color:color-mix(in srgb,var(--primary-color) 68%,white); background:color-mix(in srgb,var(--primary-color) 78%,#14212a); }
        .map-toolbar .map-icon-button { min-width:39px; padding-left:10px; padding-right:10px; }
        .map-toolbar input[type="range"] { width:110px; margin:0; padding:0; border:0; accent-color:var(--primary-color); }
        .map-canvas { position:relative; background:#081016; }
        .map,.map.leaflet-container { width:100%; height:clamp(540px,70vh,820px); background-color:#081016; background-image:radial-gradient(circle at 18% 22%,#203541 0,transparent 31%),radial-gradient(circle at 82% 76%,#152a34 0,transparent 34%),linear-gradient(#ffffff08 1px,transparent 1px),linear-gradient(90deg,#ffffff08 1px,transparent 1px); background-size:auto,auto,48px 48px,48px 48px; z-index:0; }
        .map.neutral-dark-tiles .leaflet-tile-pane { filter:grayscale(1) brightness(.34) contrast(1.42); }
        .map.neutral-dark-tiles::before { content:""; position:absolute; inset:0; z-index:250; pointer-events:none; background:linear-gradient(#05090d52,#05090d52),#18232b42; mix-blend-mode:multiply; }
        .map-stat { position:absolute; z-index:700; top:12px; right:12px; padding:7px 11px; border:1px solid #ffffff1f; border-radius:999px; background:#0b151de8; color:#e3edf3; box-shadow:0 4px 16px #0008; font-size:12px; font-weight:650; pointer-events:none; }
        .leaflet-container { color:#dce7ed; font:14px system-ui,sans-serif; }
        .leaflet-bar { overflow:hidden; border:1px solid #ffffff24!important; border-radius:10px!important; box-shadow:0 4px 14px #0008!important; }
        .leaflet-bar a,.leaflet-bar a:hover { border-color:#ffffff14!important; background:#101c24!important; color:#e9f2f6!important; }
        .map .leaflet-popup-content-wrapper,.map .leaflet-popup-tip { background:#142129; color:#e7eff3; }
        .map .leaflet-popup-content-wrapper { border:1px solid #ffffff1f; border-radius:12px; box-shadow:0 7px 26px #000a; }
        .map .leaflet-popup-content { min-width:210px; line-height:1.45; }
        .map .leaflet-popup-content p { margin:9px 0; }
        .map .leaflet-popup-content a { color:#65c8fa; font-weight:650; }
        .map .leaflet-popup-content button { border:1px solid #ffffff20; border-radius:9px; background:#20313c; }
        .map .leaflet-popup-close-button { color:#c7d5dc!important; }
        .map .leaflet-tooltip { border:1px solid #ffffff24; border-radius:8px; background:#101b22; color:#e5eef2; box-shadow:0 4px 16px #0009; }
        .leaflet-tooltip-top::before { border-top-color:#101b22; }
        .leaflet-control-attribution { border-radius:7px 0 0; background:#0b151dcc!important; color:#b7c4cb; font-size:10px; }
        .leaflet-control-attribution a { color:#79cdf6; }
        .map-marker { width:19px; height:19px; border:2px solid #effbff; border-radius:50%; box-shadow:0 0 0 3px #061017cc,0 0 13px currentColor; }
        .map-marker.meshtastic { background:var(--protocol-meshtastic); color:var(--protocol-meshtastic); } .map-marker.meshcore { background:var(--protocol-meshcore); color:var(--protocol-meshcore); } .map-marker.reticulum { background:var(--protocol-reticulum); color:var(--protocol-reticulum); }
        .map-marker.stale { opacity:.72; } .map-marker.old { opacity:.52; filter:grayscale(.55); }
        .map-home-marker { width:34px; height:34px; display:grid; place-items:center; color:#1c1c1c; background:var(--warning-color,#ff9800); border:3px solid white; border-radius:50%; box-shadow:0 2px 10px #0009; }
        .map-home-marker ha-icon { --mdc-icon-size:21px; }
        .map-cluster { display:flex; align-items:center; justify-content:center; width:38px; height:38px; border:2px solid #dff6ff; border-radius:50%; background:linear-gradient(145deg,#2187bd,#125174); color:#fff; font-weight:800; box-shadow:0 0 0 3px #061017cc,0 4px 15px #000a; }
        .map-state { position:absolute; inset:0; z-index:1; display:grid; place-items:center; padding:32px; text-align:center; }
        .map-state>div { max-width:480px; padding:24px 26px; border:1px solid #ffffff1c; border-radius:14px; background:#0b151de8; box-shadow:0 10px 35px #0008; }
        .map-state-label { color:#78cdf6; font-size:10px; font-weight:750; letter-spacing:.1em; text-transform:uppercase; }
        .map-state.failed .map-state-label { color:var(--error-color,#ef5350); }
        .map-state h2 { margin:7px 0 8px; font-size:21px; }
        .map-state p { margin:0; line-height:1.5; }
        .map-footer { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:11px 18px; padding:11px 14px 13px; background:color-mix(in srgb,var(--card-background-color) 96%,var(--primary-color)); }
        .map-legend { display:flex; align-items:center; gap:7px 14px; flex-wrap:wrap; }
        .map-legend-item { display:inline-flex; align-items:center; gap:6px; white-space:nowrap; font-size:12px; }
        .legend-dot { width:9px; height:9px; border-radius:50%; background:currentColor; box-shadow:0 0 0 2px color-mix(in srgb,currentColor 22%,transparent); }
        .legend-line { width:18px; border-top:3px solid currentColor; }
        .legend-line.dashed { border-top-style:dashed; }
        .map-tile-state { align-self:center; font-size:12px; text-align:right; }
        .map-layer-status { grid-column:1/-1; display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; }
        .map-status { min-width:0; padding:8px 10px; border:1px solid var(--divider-color); border-radius:999px; background:var(--secondary-background-color); color:var(--secondary-text-color); font-size:12px; overflow-wrap:anywhere; }
        .map-status::before { content:""; display:inline-block; width:7px; height:7px; margin-right:7px; border-radius:50%; background:var(--secondary-text-color); }
        .map-status.ok::before { background:var(--success-color,#49cf7b); }
        .map-status.bad { color:var(--primary-text-color); font-weight:600; }
        .map-status.bad::before { background:var(--error-color,#ef5350); }
        input,textarea { width:100%; padding:12px 14px; margin-bottom:14px; border:1px solid var(--divider-color); border-radius:10px; color:var(--primary-text-color); background:var(--card-background-color); font:inherit; }
        textarea { min-height:100px; resize:vertical; }
        .table { overflow:auto; background:var(--card-background-color); border-radius:14px; scrollbar-color:var(--divider-color) transparent; scrollbar-width:thin; }
        table { width:100%; border-collapse:collapse; min-width:760px; } th,td { padding:11px 13px; text-align:left; border-bottom:1px solid var(--divider-color); } th { color:var(--secondary-text-color); }
        .node-name { min-width:150px; } .node-mobile-protocol { display:none; margin-top:6px; }
        .node-favorite { width:58px; text-align:center; } .node-favorite button { min-width:42px; padding:9px 12px; }
        .node-row { cursor:pointer; }
        .node-row:hover td { background:color-mix(in srgb,var(--primary-color) 7%,transparent); }
        .node-row:focus-visible { outline:2px solid var(--primary-color); outline-offset:-2px; }
        .node-row:focus-visible td { background:color-mix(in srgb,var(--primary-color) 10%,transparent); }
        .battery-value { display:inline-flex; align-items:center; gap:5px; color:var(--primary-text-color); white-space:nowrap; }
        .battery-value ha-icon { --mdc-icon-size:20px; flex:none; color:var(--secondary-text-color); }
        .battery-value.high ha-icon { color:var(--state-sensor-battery-high-color,var(--success-color,#43a047)); }
        .battery-value.medium ha-icon { color:var(--state-sensor-battery-medium-color,var(--warning-color,#ffb300)); }
        .battery-value.low ha-icon { color:var(--state-sensor-battery-low-color,var(--error-color,#db4437)); }
        .node-detail-stat.power-stat { padding:12px 13px; }
        .power-value { gap:8px; white-space:normal; }
        .power-value ha-icon { --mdc-icon-size:27px; }
        .power-reading { display:flex; min-width:0; flex-direction:column; gap:1px; line-height:1.1; }
        .power-primary { font-size:20px; font-weight:700; white-space:nowrap; }
        .power-voltage { color:var(--secondary-text-color); font-size:12px; font-weight:500; white-space:nowrap; }
        .power-unreported { color:var(--secondary-text-color); font-size:14px; }
        .last-heard { white-space:nowrap; } .last-heard.stale,.last-heard.unknown { color:var(--secondary-text-color); }
        .node-detail-scrim { position:fixed; inset:0; z-index:1500; display:flex; justify-content:flex-end; background:#0008; }
        .node-detail { width:min(590px,100vw); height:100%; overflow:auto; padding:0; border:0; border-left:1px solid var(--divider-color); background:var(--primary-background-color); box-shadow:-12px 0 34px #0008; scrollbar-color:var(--divider-color) transparent; scrollbar-width:thin; }
        .node-detail-head { position:sticky; top:0; z-index:2; display:flex; align-items:start; justify-content:space-between; gap:16px; padding:20px 21px 16px; border-bottom:1px solid var(--divider-color); background:color-mix(in srgb,var(--card-background-color) 94%,transparent); backdrop-filter:blur(12px); }
        .node-detail-title-row { display:flex; align-items:center; gap:10px; }
        .node-detail-favorite { flex:none; min-width:40px; padding:6px 9px; font-size:22px; line-height:1; }
        .node-detail-head h2 { margin:5px 0 3px; overflow-wrap:anywhere; font-size:24px; }
        .node-detail-head p { margin:0; overflow-wrap:anywhere; }
        .node-detail-close { flex:none; min-width:43px; padding:10px 12px; font-size:18px; }
        .node-detail-body { display:grid; gap:15px; padding:17px 20px 26px; }
        .node-detail-summary { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:9px; }
        .node-detail-stat { min-width:0; padding:12px; border:1px solid var(--divider-color); border-radius:11px; background:var(--card-background-color); }
        .node-detail-stat>strong,.node-detail-stat>span { display:block; overflow-wrap:anywhere; }
        .node-detail-stat strong { margin-top:5px; font-size:18px; line-height:1.35; }
        .node-detail-stat>span { color:var(--secondary-text-color); font-size:12px; }
        .node-detail-groups { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }
        .node-detail-group { min-width:0; padding:16px 17px; border-radius:12px; background:var(--card-background-color); }
        .node-detail-group h3 { margin:0 0 12px; font-size:16px; }
        .node-detail-group.position { grid-column:1/-1; }
        .node-detail-group.position .node-detail-meta { grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; }
        .node-detail-group-empty { margin:0; color:var(--secondary-text-color); font-size:15px; line-height:1.4; }
        .node-detail-meta { display:grid; grid-template-columns:1fr; gap:11px; margin:0; }
        .node-detail-meta div { min-width:0; }
        .node-detail-meta dt { color:var(--secondary-text-color); font-size:12px; }
        .node-detail-meta dd { margin:4px 0 0; overflow-wrap:anywhere; font-size:15px; line-height:1.4; }
        .node-detail-actions { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
        .node-detail-actions a,.node-detail-actions button { display:inline-flex; align-items:center; justify-content:center; gap:7px; min-height:42px; padding:9px 12px; border:1px solid color-mix(in srgb,var(--divider-color) 82%,transparent); border-radius:12px; color:var(--primary-text-color); background:var(--card-background-color); font-weight:650; text-align:center; text-decoration:none; }
        .node-detail-actions ha-icon { --mdc-icon-size:19px; }
        .node-detail-actions .primary { color:var(--primary-color); border-color:color-mix(in srgb,var(--primary-color) 48%,var(--divider-color)); background:color-mix(in srgb,var(--primary-color) 10%,var(--card-background-color)); }
        .node-detail-actions .warning { color:var(--warning-color,#f5a623); border-color:color-mix(in srgb,var(--warning-color,#f5a623) 46%,var(--divider-color)); background:color-mix(in srgb,var(--warning-color,#f5a623) 9%,var(--card-background-color)); }
        .node-detail-actions button { width:100%; }
        .node-detail-actions .danger { color:var(--error-color); border-color:color-mix(in srgb,var(--error-color) 48%,var(--divider-color)); background:color-mix(in srgb,var(--error-color) 8%,var(--card-background-color)); }
        .node-detail-position-note { margin:0; padding:11px 13px; border-radius:10px; background:var(--card-background-color); font-size:12px; }
        .node-history { display:grid; gap:12px; padding-top:3px; }
        .node-history-head { display:flex; align-items:end; justify-content:space-between; gap:12px; }
        .node-history-head h3 { margin:3px 0 0; font-size:20px; }
        .node-history-controls { display:flex; align-items:center; gap:7px; }
        .node-history-controls select { min-width:105px; }
        .node-history-note { margin:0; font-size:12px; line-height:1.45; }
        .trend-list { display:grid; gap:10px; }
        .trend-card { min-width:0; padding:13px 14px; border:1px solid var(--divider-color); border-radius:12px; background:var(--card-background-color); }
        .trend-card-head { display:flex; align-items:start; justify-content:space-between; gap:12px; }
        .trend-card h4 { margin:0; overflow-wrap:anywhere; font-size:15px; text-transform:capitalize; }
        .trend-value { flex:none; font-size:18px; font-weight:700; }
        .trend-range { margin-top:2px; color:var(--secondary-text-color); font-size:11px; }
        .trend-chart { width:100%; height:70px; margin-top:10px; overflow:visible; }
        .trend-chart .grid-line { stroke:var(--divider-color); stroke-width:1; }
        .trend-chart polyline { fill:none; stroke:var(--primary-color); stroke-width:3; stroke-linecap:round; stroke-linejoin:round; vector-effect:non-scaling-stroke; }
        .trend-card.link-quality polyline { stroke:#d56cff; }
        .node-history-state { min-height:112px; display:grid; place-items:center; padding:17px; border:1px dashed var(--divider-color); border-radius:12px; background:var(--card-background-color); text-align:center; }
        .node-history-state h4 { margin:0 0 5px; }
        .node-history-state p { margin:0; line-height:1.45; }
        .error { margin:0 26px 15px; padding:12px; background:var(--error-color,#db4437); color:white; border-radius:8px; }
        .toolbar { display:flex; gap:10px; align-items:center; margin-bottom:14px; flex-wrap:wrap; }
        .toolbar .search-field { flex:1; min-width:220px; }
        .toolbar input { width:100%; min-width:0; margin:0; }
        .search-field { position:relative; }
        .search-field input { padding-right:38px; }
        .search-clear { position:absolute; top:50%; right:7px; width:28px; min-width:28px; height:28px; margin:0; padding:0; transform:translateY(-50%); border:0; border-radius:50%; background:transparent; color:var(--secondary-text-color); box-shadow:none; font-size:21px; line-height:1; }
        .search-clear:hover,.search-clear:focus-visible { background:color-mix(in srgb,var(--primary-text-color) 10%,transparent); color:var(--primary-text-color); }
        select { padding:11px; border:1px solid var(--divider-color); border-radius:10px; color:var(--primary-text-color); background:var(--card-background-color); font:inherit; }
        input:hover:not(:disabled),textarea:hover:not(:disabled),select:hover:not(:disabled) { border-color:color-mix(in srgb,var(--primary-color) 45%,var(--divider-color)); }
        .conversation-shell { height:100%; display:grid; grid-template-columns:clamp(294px,calc((100vw - 1700px)/2 + 294px),430px) minmax(0,1fr); overflow:hidden; border:0; border-radius:0; background:transparent; box-shadow:none; }
        .conversation-rail { min-width:0; border-right:1px solid var(--divider-color); overflow:auto; background:transparent; scrollbar-color:color-mix(in srgb,var(--secondary-text-color) 72%,transparent) transparent; scrollbar-width:auto; scrollbar-gutter:stable; }
        .conversation-search { padding:9px 12px 10px; position:sticky; top:0; z-index:2; border-bottom:1px solid var(--divider-color); background:var(--primary-background-color); }
        .conversation-search input { width:100%; margin:0; }
        .conversation-picker-wrap,.conversation-picker { display:none; }
        .conversation-picker { width:100%; margin:0; }
        .rail-heading { margin-top:5px; padding:10px 15px 6px; border-top:1px solid var(--divider-color); color:var(--secondary-text-color); font-size:10px; font-weight:750; letter-spacing:.09em; text-transform:uppercase; }
        .conversation-item { width:100%; min-width:0; margin:0; border:0; border-radius:0; padding:10px 12px; display:flex; align-items:center; gap:9px; text-align:left; background:transparent; }
        .conversation-item:hover { background:color-mix(in srgb,var(--primary-color) 8%,transparent); }
        .conversation-item.active { background:color-mix(in srgb,var(--primary-color) 11%,transparent); box-shadow:inset 3px 0 var(--primary-color); color:var(--primary-text-color); }
        .conversation-icon { width:30px; height:30px; flex:none; display:grid; place-items:center; border-radius:9px; background:color-mix(in srgb,var(--primary-text-color) 8%,transparent); color:var(--secondary-text-color); font-weight:750; }
        .conversation-item.active .conversation-icon { background:color-mix(in srgb,var(--primary-color) 20%,transparent); color:var(--primary-text-color); }
        .conversation-label { flex:1; min-width:0; } .conversation-label strong,.conversation-label small { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .conversation-label strong { font-size:13px; line-height:1.35; } .conversation-label small { margin-top:2px; font-size:11px; }
        .unread-count { min-width:22px; padding:2px 7px; border-radius:999px; background:var(--primary-color); color:var(--text-primary-color,#fff); font-size:11px; font-weight:750; text-align:center; }
        .message.openable { cursor:pointer; }
        .message.openable:hover { box-shadow:0 0 0 2px color-mix(in srgb,var(--primary-color) 30%,transparent); }
        .conversation-pane { min-width:0; min-height:0; display:grid; grid-template-rows:auto minmax(0,1fr) auto; background:transparent; }
        .conversation-chrome { min-width:0; background:transparent; border-bottom:1px solid var(--divider-color); }
        .conversation-alert { margin:10px 14px 0; padding:10px 12px; border:1px solid color-mix(in srgb,var(--warning-color,#ffb300) 40%,var(--divider-color)); border-radius:9px; background:color-mix(in srgb,var(--warning-color,#ffb300) 9%,var(--card-background-color)); font-size:12px; line-height:1.45; }
        .conversation-head { min-width:0; padding:9px 13px 10px; display:flex; align-items:center; gap:9px; }
        .conversation-head .title { flex:1; min-width:140px; } .conversation-head h3 { margin:0; overflow-wrap:anywhere; font-size:19px; line-height:1.25; }
        .conversation-head .title .muted { margin-top:3px; font-size:12px; }
        .conversation-actions { min-width:0; display:flex; flex-wrap:wrap; justify-content:flex-end; gap:8px; }
        .conversation-actions select,.conversation-actions button { min-height:34px; padding:6px 9px; border-radius:8px; font-size:12px; }
        .notification-bell { position:relative; flex:0 0 32px; align-self:center; width:32px; height:34px; margin:0; padding:5px; border:0; border-radius:0; background:transparent; box-shadow:none; line-height:1; }
        .notification-bell:hover,.notification-bell:focus-visible { background:color-mix(in srgb,var(--primary-color) 10%,transparent); }
        .notification-bell svg { width:23px; height:23px; display:block; fill:none; stroke:currentColor; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; }
        .notification-bell.enabled svg { fill:currentColor; stroke:none; }
        .node-sort-button { width:100%; margin:0; padding:0; display:inline-flex; align-items:center; gap:5px; border:0; border-radius:0; background:transparent; color:inherit; font:inherit; font-weight:inherit; text-align:left; }
        .node-sort-button:hover,.node-sort-button:focus-visible { color:var(--primary-color); background:transparent; }
        .node-sort-indicator { min-width:10px; color:var(--primary-color); }
        .notification-scrim { position:fixed; inset:0; z-index:1002; display:grid; place-items:center; padding:20px; background:#0009; }
        .notification-dialog { width:min(480px,100%); overflow:hidden; border:1px solid var(--divider-color); border-radius:16px; background:var(--card-background-color); box-shadow:0 20px 70px #0008; }
        .notification-dialog-head { display:flex; align-items:center; justify-content:space-between; gap:18px; padding:17px 21px 13px; border-bottom:1px solid var(--divider-color); }
        .notification-dialog-head h2 { margin:0; font-size:21px; }
        .notification-dialog-head button { padding:5px 9px; border-radius:8px; font-size:20px; }
        .notification-dialog-body { display:grid; gap:13px; padding:16px 21px; }
        .notification-field { display:grid; gap:6px; font-size:12px; font-weight:700; }
        .notification-empty { margin:0; padding:10px 12px; border:1px dashed var(--divider-color); border-radius:10px; color:var(--secondary-text-color); font-size:12px; line-height:1.4; }
        .notification-toggle { display:flex; align-items:center; gap:9px; font-weight:650; }
        .notification-toggle input { width:18px; height:18px; margin:0; }
        .notification-help { margin:0; color:var(--secondary-text-color); font-size:11px; line-height:1.4; }
        .notification-error { margin:0; padding:9px 11px; border-radius:8px; color:var(--error-color,#db4437); background:color-mix(in srgb,var(--error-color,#db4437) 10%,transparent); font-size:12px; }
        .notification-dialog-actions { display:flex; justify-content:flex-end; gap:9px; padding:11px 21px 17px; }
        .notification-dialog-actions .primary { color:var(--text-primary-color); background:var(--primary-color); }
        .messages { min-width:0; min-height:0; overflow-y:scroll; overflow-x:hidden; display:flex; flex-direction:column; gap:10px; padding:18px clamp(16px,3vw,34px) 28px; scrollbar-color:color-mix(in srgb,var(--secondary-text-color) 78%,transparent) color-mix(in srgb,var(--secondary-background-color) 72%,transparent); scrollbar-width:auto; scrollbar-gutter:stable; touch-action:pan-y; -webkit-overflow-scrolling:touch; overscroll-behavior-y:auto; }
        .messages::-webkit-scrollbar,.conversation-rail::-webkit-scrollbar { width:12px; height:12px; }
        .messages::-webkit-scrollbar-track,.conversation-rail::-webkit-scrollbar-track { background:color-mix(in srgb,var(--secondary-background-color) 72%,transparent); }
        .messages::-webkit-scrollbar-thumb,.conversation-rail::-webkit-scrollbar-thumb { min-height:44px; border:3px solid transparent; border-radius:999px; background:color-mix(in srgb,var(--secondary-text-color) 78%,transparent); background-clip:padding-box; }
        .messages:focus-visible { outline:2px solid var(--primary-color); outline-offset:-4px; }
        .day-divider { width:min(100%,1040px); margin:9px auto 3px; display:flex; align-items:center; gap:12px; color:var(--secondary-text-color); font-size:10px; font-weight:700; letter-spacing:.05em; text-transform:uppercase; }
        .day-divider::before,.day-divider::after { content:""; height:1px; background:var(--divider-color); flex:1; }
        .message { width:min(82%,760px); min-width:0; padding:11px 14px 10px; border:0; border-radius:11px; background:var(--secondary-background-color); box-shadow:none; }
        .message.notification-target { outline:3px solid color-mix(in srgb,var(--primary-color) 65%,transparent); outline-offset:3px; }
        .message.incoming { align-self:flex-start; border-bottom-left-radius:0; }
        .message.outgoing { align-self:flex-end; border-bottom-right-radius:0; background:color-mix(in srgb,var(--primary-color) 18%,var(--card-background-color)); }
        .message.pending { opacity:.82; }
        .message-send-state { margin-left:auto; display:inline-flex; align-items:center; gap:5px; }
        .message-send-state.sending::before { content:""; width:10px; height:10px; border:2px solid currentColor; border-right-color:transparent; border-radius:50%; animation:message-spin .75s linear infinite; }
        .message-send-state.queued::before { content:"◷"; font-size:13px; }
        .message-send-state.failed { color:var(--error-color,#db4437); }
        .message-send-state.failed::before { content:"!"; font-weight:800; }
        @keyframes message-spin { to { transform:rotate(360deg); } }
        .message.unread { border-color:color-mix(in srgb,var(--primary-color) 10%,var(--divider-color)); background:color-mix(in srgb,var(--primary-color) 4%,var(--card-background-color)); box-shadow:inset 3px 0 var(--primary-color),0 2px 8px #00000026; }
        .message-head { min-width:0; display:flex; justify-content:space-between; gap:14px; align-items:baseline; }
        .message-identity { min-width:0; display:flex; align-items:baseline; gap:7px; }
        .message-sender { min-width:0; overflow-wrap:anywhere; font-size:13px; font-weight:700; }
        .message-time { flex:none; color:var(--secondary-text-color); font-size:11px; white-space:nowrap; }
        .message-text { max-width:76ch; margin:7px 0 9px; color:var(--primary-text-color); font-size:14px; line-height:1.52; white-space:pre-wrap; overflow-wrap:anywhere; }
        .message-meta { display:flex; align-items:center; flex-wrap:wrap; gap:5px 8px; color:var(--secondary-text-color); font-size:10px; line-height:1.4; }
        .message-protocol { display:inline-flex; align-items:center; gap:5px; font-weight:700; text-transform:capitalize; }
        .message-protocol::before { content:""; width:6px; height:6px; border-radius:50%; background:var(--protocol-meshtastic); }
        .message-protocol.meshcore::before { background:var(--protocol-meshcore); }
        .message-protocol.reticulum::before { background:var(--protocol-reticulum); }
        .message-delivery::before { content:"·"; margin-right:8px; }
        .message.outgoing .message-delivery::before { content:"✓"; margin-right:5px; font-weight:800; }
        .message-reply { margin-left:auto; padding:3px 7px; border:0; border-radius:6px; background:transparent; color:var(--secondary-text-color); font-size:10px; }
        .message-reply:hover { color:var(--primary-text-color); background:color-mix(in srgb,var(--primary-color) 9%,transparent); }
        .messages .panel-state { min-height:100%; border:0; background:transparent; }
        .compose { min-width:0; margin:0; border-radius:0; border:0; border-top:1px solid var(--divider-color); padding:9px 13px 10px; background:transparent; box-shadow:none; }
        .compose-top { min-width:0; display:flex; align-items:center; gap:9px; margin-bottom:7px; }
        .compose-top label { min-width:0; display:flex; align-items:center; gap:6px; color:var(--secondary-text-color); font-size:10px; }
        .compose-top select { min-width:150px; max-width:310px; padding:6px 8px; font-size:11px; }
        .compose-route { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--secondary-text-color); font-size:10px; }
        .reply-context { min-width:0; display:grid; grid-template-columns:minmax(0,1fr) auto; gap:3px 8px; margin-bottom:7px; padding:6px 8px; border-left:3px solid var(--primary-color); border-radius:5px; background:var(--secondary-background-color); font-size:10px; }
        .reply-context strong,.reply-context span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .reply-context span { color:var(--secondary-text-color); }
        .reply-context button { grid-row:1/3; grid-column:2; align-self:center; padding:3px 7px; }
        .compose-body { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:end; gap:9px; }
        .compose textarea { width:100%; min-height:54px; max-height:150px; margin:0; resize:vertical; padding:9px 10px; }
        .compose-action { display:grid; gap:4px; justify-items:end; }
        .compose-action button { min-height:38px; white-space:nowrap; }
        #compose-send { border-color:var(--primary-color); background:var(--primary-color); color:var(--text-primary-color,#fff); font-weight:650; }
        #compose-send:hover:not(:disabled) { border-color:color-mix(in srgb,var(--primary-color) 70%,white); background:color-mix(in srgb,var(--primary-color) 88%,black); }
        .compose-count { font-size:10px; }
        .send-status { margin-top:7px; font-size:11px; line-height:1.4; }
        .send-status.ambiguous { color:var(--warning-color,#ffb300); }
        .reply-placeholder { min-width:0; display:flex; align-items:center; justify-content:space-between; gap:14px; padding:12px 16px; border-top:1px solid var(--divider-color); background:var(--card-background-color); color:var(--secondary-text-color); }
        .reply-placeholder strong { display:block; color:var(--primary-text-color); font-size:13px; }
        .reply-placeholder span { display:block; margin-top:2px; font-size:11px; line-height:1.4; }
        .reply-state { flex:none; padding:5px 8px; border:1px solid var(--divider-color); border-radius:999px; background:var(--secondary-background-color); font-size:10px; font-weight:700; letter-spacing:.04em; text-transform:uppercase; }
        @media(max-width:1100px){.map-toolbar{grid-template-columns:minmax(0,1fr) auto}.map-control-group.filters{grid-column:1/-1}.map-control-group.history{justify-self:end}.conversation-head{align-items:flex-start;flex-wrap:wrap}.conversation-actions{flex:1 1 100%;justify-content:flex-start}.automation-grid{grid-template-columns:1fr}}
        @media(max-width:760px){.tab-bar{padding-left:0}.sidebar-toggle{display:flex}}
        @media(max-width:760px){ main{padding-left:10px;padding-right:10px}nav{gap:14px;padding:0 10px;overflow-x:auto}nav button{min-width:max-content;padding:10px 0 9px;font-size:12px}.section-heading{align-items:start;flex-direction:column;gap:8px}.overview{gap:17px}.overview-hero{grid-template-columns:1fr;gap:16px;padding:21px 19px}.overview-state{width:max-content}.overview-metrics{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.overview-metric{padding:15px 14px}.overview-metric .metric{font-size:26px}.overview-section-head{align-items:start;flex-direction:column}.overview-protocols{justify-content:flex-start}.overview-sources{grid-template-columns:1fr;gap:12px}.map-toolbar{display:flex;align-items:stretch;gap:9px;flex-direction:column;padding:10px}.map-control-group{width:100%;gap:6px}.map-control-group.filters{display:grid;grid-template-columns:repeat(3,minmax(0,1fr))}.map-control-group.filters .map-control-label{grid-column:1/-1}.map-control-group.filters select{width:100%;padding-left:7px;padding-right:7px;font-size:12px}.map-control-row{display:flex;align-items:stretch;flex-direction:column;gap:9px}.map-control-group.layers,.map-control-group.view{width:100%;display:flex;flex-wrap:wrap}.map-control-group.layers .map-control-label,.map-control-group.view .map-control-label{flex-basis:100%}.map-control-group.view select{min-width:0;flex:1}.map-control-group.history{justify-content:flex-start;overflow-x:auto;padding:2px}.map-control-label{font-size:9px}.map-toolbar button{padding-left:9px;padding-right:9px}.map-toolbar input[type="range"]{min-width:84px;flex:1}.map,.map.leaflet-container{height:58vh;min-height:410px}.map-stat{top:9px;right:9px}.map-footer{grid-template-columns:1fr;padding:10px}.map-legend{gap:7px 12px}.map-tile-state{text-align:left}.map-layer-status{grid-template-columns:1fr;gap:6px}.toolbar select,.toolbar button{flex:1}.nodes-table{overflow:visible}.nodes-table table{min-width:0;table-layout:fixed}.nodes-table th,.nodes-table td{padding:10px 7px}.nodes-table .node-protocol,.nodes-table .node-power,.nodes-table .node-signal,.nodes-table .node-hops,.nodes-table .node-role{display:none}.nodes-table .node-name{width:auto;min-width:0;overflow-wrap:anywhere}.nodes-table .node-mobile-protocol{display:block}.nodes-table .node-favorite{width:52px}.nodes-table .node-last-heard{width:82px}.last-heard{white-space:normal}.node-detail-head{padding:16px 14px 13px}.node-detail-body{padding:14px}.node-detail-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.node-detail-groups,.node-detail-actions{grid-template-columns:1fr}.node-history-head{align-items:stretch;flex-direction:column}.node-history-controls{display:grid;grid-template-columns:minmax(0,1fr) auto}.conversation-shell{height:auto;min-height:0;display:block;overflow:hidden}.conversation-rail{display:flex;align-items:stretch;overflow-x:auto;overflow-y:hidden;border-right:0;border-bottom:1px solid var(--divider-color)}.conversation-search{position:sticky;left:0;z-index:3;min-width:155px;padding:9px}.conversation-item{min-width:158px;max-width:180px;padding:10px;border-right:1px solid var(--divider-color)}.conversation-rail .rail-heading{display:none}.conversation-label small{display:block}.conversation-pane{height:calc(100vh - 294px);min-height:540px}.conversation-head{padding:11px;gap:8px}.conversation-head>.conversation-icon{display:none}.conversation-head .title{min-width:0;flex:1 1 100%}.conversation-actions{display:grid;grid-template-columns:minmax(0,1fr) auto auto;flex:1 1 100%;width:100%;justify-content:stretch}.conversation-actions select{width:100%;min-width:0}.conversation-actions #mark-read{grid-column:1/-1}.messages{padding:12px}.message{width:100%;max-width:100%!important;padding:13px 14px}.message-head{align-items:flex-start;flex-wrap:wrap}.compose-grid{grid-template-columns:1fr} }
        @media(max-width:760px){
          .overview-hero { display:grid; gap:12px; padding:16px; }
          .overview-hero-actions { align-items:flex-start; }
          .overview-alerts { min-width:0; width:100%; }
          .overview-source:only-child { max-width:none; }
          .source-details { grid-template-columns:1fr; }
          .source-detail-column + .source-detail-column { margin:0; padding:13px 0 4px; border-top:1px solid var(--divider-color); border-left:0; }
          .automation-group-head { align-items:start; flex-direction:column; gap:7px; }
          .automation-notice { align-items:start; flex-direction:column; gap:3px; }
          .automation-card-head { padding:13px 14px 11px; }
          .automation-description,.automation-definition-meta,.automation-history { padding-left:14px; padding-right:14px; }
          .automation-runs li { grid-template-columns:auto minmax(0,1fr); }
          .automation-runs time { grid-column:2; text-align:left; }
          .conversation-shell { height:calc(100dvh - 205px); min-height:560px; max-height:760px; display:grid; grid-template-columns:1fr; grid-template-rows:auto minmax(0,1fr); }
          .conversation-rail { max-width:100%; display:flex; align-items:stretch; overflow-x:auto; overflow-y:hidden; border-right:0; border-bottom:1px solid var(--divider-color); scrollbar-gutter:auto; touch-action:pan-x; }
          .conversation-search { position:sticky; left:0; top:auto; z-index:3; width:160px; min-width:160px; padding:9px; }
          .conversation-item { width:auto; min-width:154px; max-width:184px; margin:5px 2px; border-radius:8px; padding:9px; }
          .conversation-item.active { box-shadow:inset 0 -3px var(--primary-color); }
          .conversation-rail .rail-heading { display:none; }
          .conversation-pane { height:auto; min-height:0; }
          .conversation-head { padding:11px 12px 12px; gap:8px; }
          .conversation-head>.conversation-icon { display:none; }
          .conversation-head .title { min-width:0; flex:1 1 100%; }
          .conversation-actions { display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); flex:1 1 100%; width:100%; justify-content:stretch; }
          .conversation-actions select { width:100%; min-width:0; grid-column:span 3; }
          .conversation-actions button { min-width:0; padding-left:8px; padding-right:8px; grid-column:span 2; }
          .conversation-actions #mark-read { grid-column:span 2; }
          .conversation-alert { margin:9px 11px 0; }
          .messages { padding:12px 10px 20px 12px; scrollbar-gutter:stable; }
          .message { width:100%; padding:12px 13px 11px; }
          .message-text { max-width:none; }
          .message-head { align-items:baseline; flex-wrap:nowrap; }
          .reply-placeholder { align-items:flex-start; padding:11px 12px; }
          .compose-grid { grid-template-columns:1fr; }
        }
        @media(max-width:430px){
          .conversation-shell { height:calc(100dvh - 196px); }
          .message-identity { align-items:flex-start; flex-direction:column; gap:3px; }
          .reply-state { display:none; }
        }
        @media(max-width:760px){.conversation-shell{height:max(640px,calc(100dvh - 92px));display:grid;grid-template-rows:auto minmax(0,1fr)}.conversation-rail{display:grid;grid-template-rows:auto auto;overflow:visible;border-bottom:1px solid var(--divider-color);background:var(--primary-background-color)}.conversation-search{position:static;width:auto;min-width:0;padding:9px 10px 6px;border:0}.conversation-picker{display:block}.conversation-picker-wrap{display:block;padding:0 10px 9px}.conversation-rail>.conversation-item,.conversation-rail>.rail-heading{display:none}.conversation-pane{height:auto;min-height:0;grid-template-rows:minmax(0,1fr) auto}.conversation-chrome{display:none}.messages{min-height:0;overflow-y:scroll}.compose{position:relative;bottom:auto}.compose-top{align-items:flex-start;flex-direction:column}.compose-top label,.compose-top select{width:100%;max-width:none}.compose-body{grid-template-columns:1fr}.compose-action{display:flex;align-items:center;justify-content:space-between}.send-review-grid{grid-template-columns:1fr}}
        @media(prefers-reduced-motion:reduce){.leaflet-fade-anim .leaflet-popup,.leaflet-zoom-anim .leaflet-zoom-animated{transition:none!important}}
      </style>
      ${this._error ? `<div class="error">${escapeHtml(this._error)}</div>` : ""}
      <div class="tab-bar"><button id="sidebar-toggle" class="sidebar-toggle" aria-label="Open Home Assistant sidebar"><ha-icon icon="mdi:menu" aria-hidden="true"></ha-icon></button><nav aria-label="MeshMonitor views" role="tablist">${PANEL_TABS.map(({value, label}) => {
        const selected = this._tab === value;
        const unread = value === "messages" ? this._unread(messages) : 0;
        return `<button id="panel-tab-${value}" data-tab="${value}" role="tab" aria-controls="panel-view" aria-selected="${selected}" tabindex="${selected ? "0" : "-1"}" class="${selected ? "active" : ""}"><span>${label}</span>${unread ? `<span class="tab-count" aria-label="${unread} unread">${unread}</span>` : ""}</button>`;
      }).join("")}</nav>${this._notificationBell()}</div>
      <main id="panel-view" class="${this._tab === "messages" ? "messages-view" : ""}" role="tabpanel" aria-labelledby="panel-tab-${this._tab}" tabindex="0">${this._tab === "overview" ? this._overview(sources, nodes, positioned) : this._tab === "messages" ? this._messages(messages, sources, this._data?.message_status) : this._tab === "nodes" ? this._nodes(nodes, sources) : this._map(positioned)}</main>
      ${this._nodeDetailDrawer(nodes, sources)}
      ${this._advertDialog()}
      ${this._notificationDialog()}`;
    this._restoreConversationView();
    this._restoreNotificationDeepLink();
    this.shadowRoot.querySelector("#sidebar-toggle")?.addEventListener("click", () =>
      this.dispatchEvent(new CustomEvent("hass-toggle-menu", {
        bubbles: true,
        composed: true,
        detail: {open: true},
      })),
    );
    this.shadowRoot.querySelectorAll("[data-tab]").forEach((button) => {
      button.addEventListener("click", () => {
        this._tab = normalizePanelTab(button.dataset.tab);
        this._render();
        window.requestAnimationFrame(() =>
          this.shadowRoot.querySelector(`[data-tab="${this._tab}"]`)?.focus(),
        );
      });
      button.addEventListener("keydown", (event) => {
        const tab = adjacentPanelTab(button.dataset.tab, event.key);
        if (!tab) return;
        event.preventDefault();
        this._tab = tab;
        this._render();
        window.requestAnimationFrame(() =>
          this.shadowRoot.querySelector(`[data-tab="${tab}"]`)?.focus(),
        );
      });
    });
    this.shadowRoot.querySelectorAll("[data-overview-source]").forEach((button) =>
      button.addEventListener("click", () => {
        const card = [...this.shadowRoot.querySelectorAll(".overview-source")].find(
          (item) =>
            item.dataset.overviewCardEntry === button.dataset.overviewEntry &&
            item.dataset.overviewCardSource === button.dataset.overviewSource,
        );
        if (!card) return;
        card.scrollIntoView({behavior: "smooth", block: "center"});
        card.focus({preventScroll: true});
        card.classList.add("overview-source-highlight");
        window.setTimeout(() => card.classList.remove("overview-source-highlight"), 1800);
      }),
    );
    this.shadowRoot.querySelectorAll("[data-meshcore-advert]").forEach((button) =>
      button.addEventListener("click", () => {
        const source = (this._data?.sources || []).find(
          (item) => item.entry_id === button.dataset.entry && item.source_id === button.dataset.meshcoreAdvert,
        );
        if (!source) return;
        this._advertReview = source;
        this._advertSending = false;
        this._advertStatus = "";
        this._render();
        window.requestAnimationFrame(() => this.shadowRoot.querySelector("#confirm-advert")?.focus());
      }),
    );
    this.shadowRoot.querySelector("#cancel-advert")?.addEventListener("click", () => {
      this._advertReview = null;
      this._advertSending = false;
      this._advertStatus = "";
      this._render();
    });
    this.shadowRoot.querySelector("#confirm-advert")?.addEventListener("click", () => this._sendMeshCoreAdvert());
    this.shadowRoot
      .querySelector("#search")
      ?.addEventListener("input", (event) => {
        this._query = event.target.value;
        this._render();
        const input = this.shadowRoot.querySelector("#search");
        input?.focus();
        input?.setSelectionRange(this._query.length, this._query.length);
      });
    this.shadowRoot
      .querySelector("#clear-node-search")
      ?.addEventListener("click", () => {
        this._query = "";
        this._render();
        this.shadowRoot.querySelector("#search")?.focus();
      });
    for (const id of ["node-protocol", "node-favorite", "node-position", "node-sort", "node-direction"]) {
      this.shadowRoot.querySelector(`#${id}`)?.addEventListener("change", (event) => {
        const field = {"node-protocol":"_nodeProtocol","node-favorite":"_nodeFavorite","node-position":"_nodePosition","node-sort":"_nodeSort","node-direction":"_nodeDirection"}[id];
        this[field] = event.target.value;
        if (id === "node-sort") localStorage.setItem("meshmonitor.nodes.sort", this._nodeSort);
        if (id === "node-direction") localStorage.setItem("meshmonitor.nodes.direction", this._nodeDirection);
        this._render();
      });
    }
    this.shadowRoot.querySelectorAll("[data-node-sort-key]").forEach((button) =>
      button.addEventListener("click", () => {
        const key = button.dataset.nodeSortKey;
        if (this._nodeSort === key)
          this._nodeDirection = this._nodeDirection === "asc" ? "desc" : "asc";
        else {
          this._nodeSort = key;
          this._nodeDirection = key === "last_heard" ? "desc" : "asc";
        }
        localStorage.setItem("meshmonitor.nodes.sort", this._nodeSort);
        localStorage.setItem("meshmonitor.nodes.direction", this._nodeDirection);
        this._render();
      }),
    );
    this.shadowRoot.querySelectorAll("[data-favorite-node]").forEach((button) =>
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        this._setFavorite(button.dataset.entry, button.dataset.source, button.dataset.favoriteNode, button.dataset.favorite !== "true");
      }),
    );
    this.shadowRoot.querySelectorAll("[data-node-detail]").forEach((row) => {
      row.addEventListener("click", () =>
        this._openNodeDetail(row.dataset.entry, row.dataset.source, row.dataset.nodeDetail),
      );
      row.addEventListener("keydown", (event) => {
        if (event.target !== event.currentTarget || (event.key !== "Enter" && event.key !== " ")) return;
        event.preventDefault();
        this._openNodeDetail(row.dataset.entry, row.dataset.source, row.dataset.nodeDetail);
      });
    });
    this.shadowRoot
      .querySelector("#close-node-detail")
      ?.addEventListener("click", () => this._closeNodeDetail());
    this.shadowRoot
      .querySelector(".node-detail-scrim")
      ?.addEventListener("click", (event) => {
        if (event.target === event.currentTarget) this._closeNodeDetail();
      });
    this.shadowRoot
      .querySelector("#node-history-range")
      ?.addEventListener("change", (event) => {
        this._nodeHistoryHours = Number(event.target.value);
        this._nodeHistory = null;
        this._nodeHistoryError = "";
        this._render();
      });
    this.shadowRoot
      .querySelector("#load-node-history")
      ?.addEventListener("click", () => this._loadNodeHistory());
    this.shadowRoot
      .querySelector("#node-detail-trail")
      ?.addEventListener("click", (event) => {
        const button = event.currentTarget;
        this._closeNodeDetail(false);
        this._loadPositionHistory(
          button.dataset.entry,
          button.dataset.source,
          button.dataset.positionNode,
          button.dataset.nodeName,
        );
      });
    this.shadowRoot
      .querySelector("#node-detail-message")
      ?.addEventListener("click", () => this._messageNodeFromDetail());
    this.shadowRoot.querySelectorAll("[data-node-request]").forEach((button) =>
      button.addEventListener("click", () =>
        this._requestNodeAction(button.dataset.nodeRequest),
      ),
    );
    this.shadowRoot
      .querySelector("#node-detail-ignore")
      ?.addEventListener("click", () => {
        this._nodeIgnoreReview = true;
        this._render();
      });
    this.shadowRoot
      .querySelector("#confirm-node-ignore")
      ?.addEventListener("click", () => this._setNodeIgnored());
    this.shadowRoot
      .querySelector("#cancel-node-ignore")
      ?.addEventListener("click", () => {
        this._nodeIgnoreReview = false;
        this._render();
      });
    this.shadowRoot
      .querySelector("#node-detail-map")
      ?.addEventListener("click", () => this._mapNodeFromDetail());
    this.shadowRoot
      .querySelector(".node-detail")
      ?.addEventListener("keydown", (event) => this._nodeDetailKeydown(event));
    this.shadowRoot.querySelectorAll("[data-position-node]").forEach((button) =>
      button.addEventListener("click", () => this._loadPositionHistory(button.dataset.entry, button.dataset.source, button.dataset.positionNode, button.dataset.nodeName)),
    );
    this.shadowRoot
      .querySelector("#message-search")
      ?.addEventListener("input", (event) => {
        this._messageQuery = event.target.value;
        this._render();
        const input = this.shadowRoot.querySelector("#message-search");
        input?.focus();
        input?.setSelectionRange(
          this._messageQuery.length,
          this._messageQuery.length,
        );
      });
    this.shadowRoot
      .querySelector("#clear-message-search")
      ?.addEventListener("click", () => {
        this._messageQuery = "";
        this._render();
        this.shadowRoot.querySelector("#message-search")?.focus();
      });
    this.shadowRoot
      .querySelector("#message-protocol")
      ?.addEventListener("change", (event) => {
        this._messageProtocol = event.target.value;
        this._render();
      });
    this.shadowRoot
      .querySelector("#message-source")
      ?.addEventListener("change", (event) => {
        this._messageSource = event.target.value;
        this._render();
      });
    this.shadowRoot
      .querySelector("#message-scope")
      ?.addEventListener("change", (event) => {
        this._messageScope = event.target.value;
        this._render();
      });
    this.shadowRoot.querySelector("#message-sort")?.addEventListener("change", (event) => {
      this._messageSort = event.target.value;
      localStorage.setItem("meshmonitor.messages.sort", this._messageSort);
      this._render();
    });
    this.shadowRoot.querySelector("#message-unread")?.addEventListener("click", () => { this._messageUnread = !this._messageUnread; this._render(); });
    this.shadowRoot.querySelector("#message-favorite")?.addEventListener("click", () => { this._messageFavorite = !this._messageFavorite; this._render(); });
    this.shadowRoot.querySelectorAll("[data-conversation]").forEach((button) =>
      button.addEventListener("click", () => {
        this._selectConversation(button.dataset.conversation);
      }),
    );
    this.shadowRoot
      .querySelector("#conversation-picker")
      ?.addEventListener("change", (event) =>
        this._selectConversation(event.target.value),
      );
    this.shadowRoot.querySelector("#conversation-pin")?.addEventListener("click", () =>
      this._toggleConversationPreference("pinned", this._conversation),
    );
    this.shadowRoot.querySelector("#conversation-mute")?.addEventListener("click", () =>
      this._toggleConversationPreference("muted", this._conversation),
    );
    this.shadowRoot.querySelector("#notification-bell")?.addEventListener("click", async () => {
      this._notificationDialogOpen = true;
      this._notificationError = "";
      this._render();
      await this._loadNotificationSettings();
      this._render();
    });
    this.shadowRoot.querySelector("#close-notification-dialog")?.addEventListener("click", () => {
      this._notificationDialogOpen = false;
      this._render();
    });
    this.shadowRoot.querySelector("#cancel-notification-settings")?.addEventListener("click", () => {
      this._notificationDialogOpen = false;
      this._render();
    });
    this.shadowRoot.querySelector("#save-notification-settings")?.addEventListener("click", () =>
      this._saveNotificationSettings(),
    );
    this.shadowRoot
      .querySelector("#mark-read")
      ?.addEventListener("click", () => {
        const readAt = Date.now();
        if (this._conversation === "all") {
          this._lastRead = readAt;
          for (const item of this._conversationCatalog(
            this._data?.messages || [],
            this._data?.sources || [],
          )) this._conversationLastRead[item.key] = readAt;
        } else this._markConversationRead(this._conversation, readAt);
        localStorage.setItem(
          "meshmonitor.messages.lastRead",
          String(this._lastRead),
        );
        localStorage.setItem(
          "meshmonitor.messages.lastReadByConversation",
          JSON.stringify(this._conversationLastRead),
        );
        this._render();
      });
    this.shadowRoot
      .querySelector("#compose-source")
      ?.addEventListener("change", (event) => {
        this._composeSource = event.target.value;
        this._render();
      });
    this.shadowRoot
      .querySelector("#compose-text")
      ?.addEventListener("input", (event) => {
        this._composeText = event.target.value;
        this._messageDrafts.set(this._conversation, this._composeText);
        const selected = this._conversationCatalog(
          this._data?.messages || [],
          this._data?.sources || [],
        ).find((item) => item.key === this._conversation);
        const validation = messageDraftValidation(
          this._composeText,
          selected?.protocol,
          selected?.type,
        );
        const count = this.shadowRoot.querySelector("#compose-count");
        if (count)
          count.textContent = `${validation.bytes} / ${validation.limit} bytes`;
        const button = this.shadowRoot.querySelector("#compose-send");
        if (button) button.disabled = !validation.valid || this._sending;
      });
    this.shadowRoot
      .querySelector("#compose-send")
      ?.addEventListener("click", () => this._sendMessage());
    this.shadowRoot
      .querySelector("#cancel-reply-context")
      ?.addEventListener("click", () => {
        this._replyContext = null;
        this._render();
        window.requestAnimationFrame(() =>
          this.shadowRoot.querySelector("#compose-text")?.focus(),
        );
      });
    this.shadowRoot
      .querySelector("#map-protocol")
      ?.addEventListener("change", (event) => {
        this._mapProtocol = event.target.value;
        this._render();
      });
    this.shadowRoot
      .querySelector("#map-source")
      ?.addEventListener("change", (event) => {
        this._mapSource = event.target.value;
        this._render();
      });
    this.shadowRoot
      .querySelector("#map-freshness")
      ?.addEventListener("change", (event) => {
        this._mapFreshness = event.target.value;
        this._render();
      });
    this.shadowRoot
      .querySelector("#map-reset-filters")
      ?.addEventListener("click", () => {
        this._mapProtocol = "all";
        this._mapSource = "all";
        this._mapFreshness = "all";
        this._render();
      });
    this.shadowRoot
      .querySelector("#map-position-range")
      ?.addEventListener("change", (event) => {
        this._positionRange = Number(event.target.value);
        if (this._positionTrail)
          this._loadPositionHistory(
            this._positionTrail.entry_id,
            this._positionTrail.source_id,
            this._positionTrail.node_id,
            this._positionTrail.node_name,
          );
      });
    this.shadowRoot
      .querySelector("#map-position-play")
      ?.addEventListener("click", () => this._togglePositionPlayback());
    this.shadowRoot
      .querySelector("#map-position-progress")
      ?.addEventListener("input", (event) => {
        this._positionIndex = Number(event.target.value);
        this._renderPositionTrail();
        this._updatePositionControls();
      });
    this.shadowRoot
      .querySelector("#map-position-clear")
      ?.addEventListener("click", () => {
        this._stopPositionPlayback();
        this._positionTrail = null;
        this._render();
      });
    this.shadowRoot
      .querySelector("#map-style")
      ?.addEventListener("change", (event) => {
        this._mapStyle = persistMapStyle(localStorage, event.target.value);
        this._render();
      });
    for (const [id, field, storage] of [
      ["map-topology", "_mapTopology", "meshmonitor.map.topology"],
      ["map-neighbors", "_mapNeighbors", "meshmonitor.map.neighbors"],
    ]) {
      this.shadowRoot.querySelector(`#${id}`)?.addEventListener("click", () => {
        this[field] = !this[field];
        localStorage.setItem(storage, String(this[field]));
        this._render();
      });
    }
    this.shadowRoot
      .querySelector("#map-fit")
      ?.addEventListener("click", () => this._fitMap());
    this.shadowRoot
      .querySelector("#map-home")
      ?.addEventListener("click", () => this._focusHome());
    this.shadowRoot
      .querySelector("#map-show-home")
      ?.addEventListener("click", () => {
        this._mapShowHome = persistShowHome(
          localStorage,
          !this._mapShowHome,
        );
        this._render();
      });
    this.shadowRoot
      .querySelector("#map-fullscreen")
      ?.addEventListener("click", async () => {
        const shell = this.shadowRoot.querySelector(".map-shell");
        if (!document.fullscreenElement) await shell?.requestFullscreen();
        else await document.exitFullscreen();
        window.setTimeout(() => this._mapInstance?.invalidateSize(), 100);
      });
    this.shadowRoot.querySelector("#mesh-map")?.addEventListener("click", (event) => {
      const button = event.target.closest?.("[data-position-node]");
      if (button)
        this._loadPositionHistory(
          button.dataset.entry,
          button.dataset.source,
          button.dataset.positionNode,
          button.dataset.nodeName,
        );
      const detailButton = event.target.closest?.("[data-map-node-detail]");
      if (detailButton)
        this._nodeDetailFromMap(
          detailButton.dataset.entry,
          detailButton.dataset.source,
          detailButton.dataset.mapNodeDetail,
        );
    });
    if (this._tab === "map")
      window.requestAnimationFrame(() => this._initMap(positioned));
  }

  _panelState(label, title, detail) {
    return `<section class="panel-state" aria-live="polite"><div><div class="section-eyebrow">${escapeHtml(label)}</div><h2>${escapeHtml(title)}</h2><p class="muted">${escapeHtml(detail)}</p></div></section>`;
  }

  _overview(sources, nodes, positioned) {
    const lifecycle = overviewLifecyclePresentation({
      loading: this._loading,
      hasSnapshot: Boolean(this._data),
      sourceCount: sources.length,
      error: Boolean(this._error),
    });
    if (lifecycle)
      return `<section class="card overview-empty" data-state="${lifecycle.state}" aria-live="polite"><div><h2>${lifecycle.title}</h2><p class="muted">${lifecycle.detail}</p></div></section>`;
    const summary = overviewSummary(sources, nodes);
    const health = overviewHealthPresentation(summary);
    const attentionItems = overviewAttentionItems(sources);
    const attention = attentionItems.length
      ? `<div class="overview-alerts" aria-label="Sources requiring attention">${attentionItems.map((item) => `<button class="overview-alert" data-overview-entry="${escapeHtml(item.entryId)}" data-overview-source="${escapeHtml(item.sourceId)}"><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.reason)}</small></button>`).join("")}</div>`
      : "";
    const serverCards = (this._data?.servers || []).map((server) => {
      const presentation = serverCardPresentation(server);
      const automationGroups = (this._data?.automation_groups || []).filter(
        (group) => (group.entry_ids || []).includes(server.entry_id),
      );
      const automation = automationOverviewSummary(automationGroups);
      const automationSummary = automationGroups.length
        ? `${automation.automationCount} configured · ${automation.enabledCount} enabled`
        : "Not monitored";
      const automationDetail = automationGroups.length
        ? `${automation.runCount} recent runs · ${automation.label}`
        : "Automation read access is unavailable";
      const update = `<strong class="${escapeHtml(presentation.updateTone)}">${escapeHtml(presentation.updateLabel)}</strong>`;
      const release = presentation.releaseUrl
        ? `<a href="${escapeHtml(presentation.releaseUrl)}" target="_blank" rel="noopener noreferrer">Release notes ↗</a>`
        : "";
      return `<article class="card overview-server"><div class="overview-server-head"><div><span class="section-eyebrow">Server name</span><h3>${escapeHtml(server.name || "MeshMonitor")}</h3></div><span class="server-state ${escapeHtml(presentation.healthTone)}" role="status">${escapeHtml(presentation.healthLabel)}</span></div><div class="server-versions"><div class="server-version"><span>Installed</span><strong>${escapeHtml(presentation.installed)}</strong></div><div class="server-version"><span>Latest available</span><strong>${escapeHtml(presentation.latest)}</strong></div></div><div class="server-update">${update}${release}</div><span class="server-meta">${server.source_count || 0} source${server.source_count === 1 ? "" : "s"} · ${escapeHtml(presentation.checked)}</span><div class="server-automation"><span>Automations</span><strong>${escapeHtml(automationSummary)}</strong><small>${escapeHtml(automationDetail)}</small></div></article>`;
    }).join("");
    const sourceCards = sources.map((source) => {
      const presentation = sourceCardPresentation(source);
      const reticulum = reticulumCardPresentation(source);
      const device = source.device || {};
      const update = source.firmware_update || { state: "unknown" };
      const updateLabel = update.state === "current" ? "Current" : update.state === "available" ? `Update available: ${update.latest_version}` : "Update status unknown";
      const updateClass = update.state === "available" ? "bad" : update.state === "current" ? "ok" : "quiet";
      const uptime = Number.isFinite(device.uptime_seconds)
        ? device.uptime_seconds < 3600
          ? `${Math.floor(device.uptime_seconds / 60)}m`
          : `${Math.floor(device.uptime_seconds / 3600)}h ${Math.floor(device.uptime_seconds % 3600 / 60)}m`
        : null;
      const radio = [
        device.frequency_mhz != null ? `${device.frequency_mhz} MHz` : null,
        device.bandwidth_khz != null ? `${device.bandwidth_khz} kHz` : null,
        device.spreading_factor != null ? `SF${device.spreading_factor}` : null,
        device.coding_rate != null ? `CR 4/${device.coding_rate}` : null,
      ].filter(Boolean).join(" · ");
      const sourceBattery = batteryPresentation(device.battery_percent, device.battery_voltage);
      const healthDetails = [
        uptime ? `Uptime ${uptime}` : null,
        device.noise_floor_dbm != null ? `Noise ${device.noise_floor_dbm} dBm` : null,
        device.last_rssi_dbm != null ? `Last signal ${device.last_rssi_dbm} dBm${device.last_snr_db != null ? ` / ${device.last_snr_db} dB SNR` : ""}` : null,
      ].filter(Boolean);
      const advertEnabled = source.protocol === "meshcore" && this._data?.can_send_messages === true && source.available && source.connected === true && source.transmit_enabled;
      const advertReason = this._data?.can_send_messages !== true
        ? "Administrator access required"
        : !source.transmit_enabled
          ? "Enable outbound radio actions for this source"
          : !source.available || source.connected !== true
            ? "Source must be connected"
            : "Send one MeshCore flood advert";
      const advert = source.protocol === "meshcore"
        ? `<button data-entry="${escapeHtml(source.entry_id)}" data-meshcore-advert="${escapeHtml(source.source_id)}" title="${escapeHtml(advertReason)}" ${advertEnabled ? "" : "disabled"}>Send advert</button>`
        : "";
      const sourceStats = reticulum
        ? reticulum.stats.map((stat) => `<div class="source-stat"><strong>${escapeHtml(stat.value)}</strong><span>${escapeHtml(stat.label)}</span></div>`).join("")
        : `<div class="source-stat"><strong>${source.node_count}</strong><span>known nodes</span></div><div class="source-stat"><strong>${source.positioned_count}</strong><span>positioned</span></div>`;
      const sourceDetails = reticulum
        ? `<div class="source-details"><div class="source-detail-column">${reticulum.primary.map(([label, value]) => `<p>${escapeHtml(label)}: <strong>${escapeHtml(value)}</strong></p>`).join("")}</div><div class="source-detail-column">${reticulum.secondary.map(([label, value]) => `<p>${escapeHtml(label)}: <strong>${escapeHtml(value)}</strong></p>`).join("")}</div></div>`
        : `<div class="source-details"><div class="source-detail-column"><p>Connection: <strong>${escapeHtml(presentation.connection)}</strong></p><p>Device: <strong>${escapeHtml(hardwareModelLabel(device.model || device.device_type, source.protocol) || "Unknown")}</strong></p><p>Firmware: <strong>${escapeHtml(device.firmware || "Unknown")}</strong>${device.firmware_build ? ` <span class="muted">(${escapeHtml(device.firmware_build)})</span>` : ""}</p><p class="firmware-state ${updateClass}">${update.release_url ? `<a href="${escapeHtml(update.release_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(updateLabel)} ↗</a>` : escapeHtml(updateLabel)}</p></div><div class="source-detail-column">${radio ? `<p>Radio: <strong>${escapeHtml(radio)}</strong></p>` : ""}${sourceBattery ? `<p>Battery: ${batteryMarkup(device.battery_percent, device.battery_voltage)}</p>` : ""}${healthDetails.length ? `<p>${healthDetails.map(escapeHtml).join(" · ")}</p>` : ""}${device.packets_received != null ? `<p>Receiver: <strong>${device.packets_received} packets</strong>${device.receive_errors != null ? ` · ${device.receive_errors} errors` : ""}</p>` : ""}</div></div>`;
      return `<article class="card overview-source ${escapeHtml(source.protocol)}" data-overview-card-entry="${escapeHtml(source.entry_id)}" data-overview-card-source="${escapeHtml(source.source_id)}" tabindex="-1">
        <div class="overview-source-head"><div><span class="badge protocol-${escapeHtml(source.protocol)}">${escapeHtml(source.protocol)}</span><h3>${escapeHtml(source.name)}</h3></div><div class="source-health-state"><span class="source-state ${presentation.tone}" role="status" aria-label="${escapeHtml(source.name)}: ${escapeHtml(presentation.stateLabel)}">${escapeHtml(presentation.stateLabel)}</span><small class="source-reported" title="${escapeHtml(presentation.updated.title)}">${escapeHtml(presentation.updated.label)}</small></div></div>
        <div class="source-stats">${sourceStats}</div>
        ${sourceDetails}
        ${presentation.errors.length ? `<p class="source-errors bad">Partial data: ${presentation.errors.map(escapeHtml).join(", ")}</p>` : ""}
        ${advert ? `<div class="source-links">${advert}</div>` : ""}
      </article>`;
    }).join("");
    return `<div class="overview">
      <section class="card overview-hero" aria-live="polite" aria-label="${escapeHtml(health.ariaLabel)}"><div><div class="overview-eyebrow">MeshMonitor</div><h2>Overview</h2><p class="muted"><strong>${escapeHtml(health.headline)}.</strong>${this._error ? " Showing the last successful snapshot while refresh is unavailable." : ""}</p></div><div class="overview-hero-actions"><div class="overview-state ${summary.state}" role="status" aria-label="${escapeHtml(health.ariaLabel)}">${escapeHtml(health.badge)}</div>${attention}</div></section>
      <section class="overview-metrics" aria-label="Mesh summary">
        <div class="card overview-metric"><div class="muted">Known nodes</div><div class="metric">${summary.nodeCount}</div><small>Across visible sources</small></div>
        <div class="card overview-metric"><div class="muted">Heard in the last hour</div><div class="metric">${summary.recent}</div><small>Future and unknown times excluded</small></div>
        <div class="card overview-metric"><div class="muted">Positioned nodes</div><div class="metric">${summary.positioned}</div><small>${summary.nodeCount ? `${Math.round(summary.positioned / summary.nodeCount * 100)}% of known nodes` : "No known nodes"}</small></div>
        <div class="card overview-metric"><div class="muted">Protocols</div><div class="metric">${summary.protocols.length}</div><small>${summary.protocols.length ? summary.protocols.map((protocol) => protocol[0].toUpperCase() + protocol.slice(1)).join(" + ") : "None represented"}</small></div>
      </section>
      <section><div class="overview-section-head"><div><h2>MeshMonitor server(s)</h2><p class="muted">Installed and latest available versions, checked independently for each configured server.</p></div></div><div class="overview-servers">${serverCards}</div></section>
      <section><div class="overview-section-head"><div><h2>Source health</h2><p class="muted">Connectivity, installed firmware, radio preset, and practical device health.</p></div></div><div class="overview-sources">${sourceCards}</div></section>
    </div>`;
  }

  _advertDialog() {
    const source = this._advertReview;
    if (!source) return "";
    const completed = Boolean(this._advertStatus);
    const title = this._advertSending ? "Sending MeshCore advert…" : completed ? "Advert not sent" : "Send MeshCore advert?";
    const actions = completed
      ? `<button id="cancel-advert">Close</button>`
      : `<button id="cancel-advert" ${this._advertSending ? "disabled" : ""}>Cancel</button><button id="confirm-advert" class="danger" ${this._advertSending ? "disabled" : ""}>${this._advertSending ? "Sending…" : "Send one advert"}</button>`;
    return `<div class="advert-scrim"><section class="advert-dialog" role="dialog" aria-modal="true" aria-labelledby="advert-dialog-title"><div class="advert-dialog-head"><div class="section-eyebrow">Radio transmission review</div><h2 id="advert-dialog-title">${title}</h2></div><div class="advert-dialog-body"><p>This sends one flood advert from the selected local companion. It may be repeated by the mesh, does not request replies, and will not be retried automatically.</p><dl><dt>Source</dt><dd>${escapeHtml(source.name)}</dd><dt>Source ID</dt><dd>${escapeHtml(source.source_id)}</dd><dt>Protocol</dt><dd>MeshCore</dd><dt>Action</dt><dd>One flood advert</dd></dl></div>${completed ? `<p class="advert-status" role="status" aria-live="polite">${escapeHtml(this._advertStatus)}</p>` : ""}<div class="advert-dialog-actions">${actions}</div></section></div>`;
  }

  async _sendMeshCoreAdvert() {
    if (this._advertSending || !this._advertReview) return;
    const source = this._advertReview;
    this._advertSending = true;
    this._advertStatus = "";
    this._render();
    try {
      const result = await this._hass.callWS({
        type: "meshmonitor/send_meshcore_advert",
        entry_id: source.entry_id,
        source_id: source.source_id,
        nonce: messageSendNonce(),
        confirm: "ADVERT",
      });
      if (result.accepted) {
        this._advertReview = null;
        this._advertStatus = "";
      } else {
        this._advertStatus = "MeshMonitor did not accept the advert. Nothing will be retried.";
      }
    } catch (error) {
      this._advertStatus = advertErrorPresentation(error);
    } finally {
      this._advertSending = false;
      this._render();
    }
  }

  _automationSection(groups) {
    const summary = automationOverviewSummary(groups);
    const heading = `<div class="overview-section-head"><div><h2>MeshMonitor automations</h2><p class="muted">Read-only definitions and recent bounded outcomes. Manage and run automations in MeshMonitor.</p></div><span class="automation-summary ${summary.tone}" role="status">${escapeHtml(summary.label)}</span></div>`;
    if (!groups.length)
      return `<section class="automation-section" aria-label="MeshMonitor automations">${heading}<div class="card automation-state"><div><h3>Automation visibility is off</h3><p class="muted">Enable <strong>Read configured automations and recent outcomes</strong> only after the dedicated account has the global <code>automations:read</code> permission.</p></div></div></section>`;
    const metrics = `<div class="automation-metrics" aria-label="Automation summary"><span><strong>${summary.automationCount}</strong> configured</span><span><strong>${summary.enabledCount}</strong> enabled</span><span><strong>${summary.runCount}</strong> recent runs</span></div>`;
    return `<section class="automation-section" aria-label="MeshMonitor automations">${heading}${metrics}<div class="automation-groups">${groups.map((group) => this._automationGroup(group)).join("")}</div></section>`;
  }

  _automationGroup(group) {
    const automations = group.automations || [];
    const state = automationStatePresentation(group.state, automations.length > 0);
    const sourceNames = (group.sources || []).map((source) => source.name || source.id);
    const sources = sourceNames.length ? sourceNames.join(", ") : "Configured MeshMonitor server";
    const notice = group.state !== "ok"
      ? `<div class="automation-notice ${state.tone}" role="status"><strong>${escapeHtml(state.title)}</strong><span>${escapeHtml(state.detail)}</span></div>`
      : "";
    const truncated = group.definitions_truncated
      ? `<div class="automation-notice quiet" role="status"><strong>Definition list bounded</strong><span>Showing the first 25 definitions in stable order.</span></div>`
      : "";
    const empty = automations.length
      ? ""
      : `<div class="card automation-state"><div><h3>${escapeHtml(state.title)}</h3><p class="muted">${escapeHtml(state.detail)}</p></div></div>`;
    return `<section class="automation-group"><div class="automation-group-head"><div><span class="section-eyebrow">Server scope</span><h3>${escapeHtml(sources)}</h3></div><span class="automation-summary ${state.tone}">${escapeHtml(state.label)}</span></div>${notice}${truncated}${empty}<div class="automation-grid">${automations.map((automation) => this._automationCard(automation)).join("")}</div></section>`;
  }

  _automationCard(automation) {
    const history = automation.history || { state: "pending", runs: [] };
    const runs = sortedAutomationRuns(history.runs || []);
    const historyState = automationStatePresentation(history.state, runs.length > 0);
    const name = automation.name || `Automation ${automation.id}`;
    const enabled = automation.enabled === true
      ? ["Enabled", "ok"]
      : automation.enabled === false
        ? ["Disabled", "quiet"]
        : ["State unknown", "quiet"];
    const runRows = (items) => items.map((run) => {
      const presentation = automationRunPresentation(run);
      const source = run.source_id ? `Source ${run.source_id}` : "Global run";
      return `<li><span class="automation-run-status ${presentation.tone}">${escapeHtml(presentation.label)}</span><span class="automation-run-source">${escapeHtml(source)}</span><time>${escapeHtml(readableTime(presentation.timestamp))}</time></li>`;
    }).join("");
    const visible = runs.slice(0, 4);
    const older = runs.slice(4);
    const historyNotice = history.state !== "ok" && history.state !== "empty"
      ? `<div class="automation-history-state ${historyState.tone}" role="status">${escapeHtml(historyState.detail)}</div>`
      : "";
    const gap = history.history_gap
      ? `<div class="automation-history-state bad" role="status">History gap detected. Unknown rows were safely baselined; no event replay was attempted.</div>`
      : "";
    const bounded = history.may_be_truncated
      ? `<div class="automation-history-state quiet">This 20-row history may omit older outcomes.</div>`
      : "";
    const recent = runs.length
      ? `<ol class="automation-runs">${runRows(visible)}</ol>${older.length ? `<details class="automation-more"><summary>Show ${older.length} older retained outcome${older.length === 1 ? "" : "s"}</summary><ol class="automation-runs">${runRows(older)}</ol></details>` : ""}`
      : `<p class="automation-no-runs muted">${history.state === "empty" || history.state === "ok" ? "No recent runs were returned." : "No retained run rows are available."}</p>`;
    return `<article class="card automation-card"><div class="automation-card-head"><div><h4>${escapeHtml(name)}</h4><span class="automation-id">${escapeHtml(automation.id)}</span></div><span class="automation-summary ${enabled[1]}">${enabled[0]}</span></div>${automation.description ? `<p class="automation-description">${escapeHtml(automation.description)}</p>` : ""}<dl class="automation-definition-meta"><div><dt>Updated</dt><dd>${escapeHtml(readableTime(automation.updated_at || automation.created_at))}</dd></div><div><dt>History</dt><dd>${escapeHtml(historyState.label)}</dd></div></dl><div class="automation-history"><h5>Recent outcomes</h5>${historyNotice}${gap}${bounded}${recent}</div></article>`;
  }

  _map(nodes) {
    const sources = (this._data?.sources || []).map((source) => [
      source.source_id,
      source.name || source.source_id,
    ]);
    const visible = this._filteredMapNodes(nodes).length;
    const links = this._mapLinks();
    const trail = this._visiblePositionTrail();
    const trailCount = trail?.fixes?.length || 0;
    const empty = mapEmptyPresentation({
      loading: this._loading,
      hasSnapshot: Boolean(this._data),
      sourceCount: sources.length,
      error: Boolean(this._error),
      filtered: this._mapProtocol !== "all" || this._mapSource !== "all" || this._mapFreshness !== "all",
      nodes: visible,
      links: links.length,
      fixes: trailCount,
    });
    const filtered = this._mapProtocol !== "all" || this._mapSource !== "all" || this._mapFreshness !== "all";
    const state = empty ? `<div class="map-state ${empty.state}" role="status"><div><span class="map-state-label">Map status</span><h2>${empty.title}</h2><p class="muted">${empty.detail}</p>${filtered ? `<button id="map-reset-filters"><ha-icon icon="mdi:filter-remove-outline" aria-hidden="true"></ha-icon>Clear filters</button>` : ""}</div></div>` : "";
    const playback = trailCount > 1 ? `<button id="map-position-play"><ha-icon icon="mdi:${this._positionPlaying ? "pause" : "play"}" aria-hidden="true"></ha-icon>${this._positionPlaying ? "Pause" : "Play"}</button><input id="map-position-progress" aria-label="Position playback" type="range" min="0" max="${trailCount - 1}" value="${Math.min(this._positionIndex, trailCount - 1)}">` : "";
    const clear = this._positionTrail ? `<button id="map-position-clear"><ha-icon icon="mdi:close" aria-hidden="true"></ha-icon>Clear</button>` : "";
    const trailBad = this._positionTrail?.state === "permission_denied" || this._positionTrail?.state === "error";
    const mapStyle = mapStylePresentation(this._mapStyle);
    return `<link rel="stylesheet" href="/meshmonitor_panel/vendor/leaflet/leaflet.css"><section class="map-shell" aria-label="Mesh map">
      <div class="map-head"><div><h2>Mesh map</h2><p class="muted">Explore current positions, stored links, and movement history.</p></div><span class="badge">${visible} visible</span></div>
      <div class="map-toolbar" aria-label="Map controls">
        <div class="map-control-group filters"><span class="map-control-label">Filter</span><select id="map-protocol" aria-label="Node protocol"><option value="all">All positions (${nodes.length})</option><option value="meshtastic" ${this._mapProtocol === "meshtastic" ? "selected" : ""}>Meshtastic</option><option value="meshcore" ${this._mapProtocol === "meshcore" ? "selected" : ""}>MeshCore</option><option value="reticulum" ${this._mapProtocol === "reticulum" ? "selected" : ""}>Reticulum</option></select><select id="map-source" aria-label="Source"><option value="all">All sources</option>${sources.map(([id, name]) => `<option value="${escapeHtml(id)}" ${this._mapSource === id ? "selected" : ""}>${escapeHtml(name)}</option>`).join("")}</select><select id="map-freshness" aria-label="Last-heard age"><option value="all">Any age</option><option value="fresh" ${this._mapFreshness === "fresh" ? "selected" : ""}>Fresh ≤1h</option><option value="stale" ${this._mapFreshness === "stale" ? "selected" : ""}>Stale 1–24h</option><option value="old" ${this._mapFreshness === "old" ? "selected" : ""}>Old</option></select></div>
        <div class="map-control-row"><div class="map-control-group layers"><span class="map-control-label">Layers</span><button id="map-topology" class="${this._mapTopology ? "active" : ""}" aria-pressed="${this._mapTopology}"><ha-icon icon="mdi:vector-polyline" aria-hidden="true"></ha-icon>Topology</button><button id="map-neighbors" class="${this._mapNeighbors ? "active" : ""}" aria-pressed="${this._mapNeighbors}"><ha-icon icon="mdi:access-point-network" aria-hidden="true"></ha-icon>Neighbor SNR</button><button id="map-show-home" class="${this._mapShowHome ? "active" : ""}" aria-pressed="${this._mapShowHome}" ${homeLocation(this._hass) ? "" : "disabled"}><ha-icon icon="mdi:home-map-marker" aria-hidden="true"></ha-icon>Show Home</button></div><div class="map-control-group view"><span class="map-control-label">View</span><button id="map-fit"><ha-icon icon="mdi:crosshairs-gps" aria-hidden="true"></ha-icon>Fit</button><button id="map-home" ${homeLocation(this._hass) ? "" : "disabled"}><ha-icon icon="mdi:home" aria-hidden="true"></ha-icon>Home</button><button id="map-fullscreen" class="map-icon-button" aria-label="Toggle fullscreen" title="Toggle fullscreen"><ha-icon icon="mdi:fullscreen" aria-hidden="true"></ha-icon></button><select id="map-style" aria-label="Map style">${MAP_STYLES.map(({value,label}) => `<option value="${value}" ${value === mapStyle.value ? "selected" : ""}>${label}</option>`).join("")}</select></div></div>
        <div class="map-control-group history"><span class="map-control-label">Trail</span><select id="map-position-range" aria-label="Trail time range">${[[1,"1h"],[6,"6h"],[24,"24h"],[72,"3d"],[168,"7d"]].map(([hours,label]) => `<option value="${hours}" ${this._positionRange === hours ? "selected" : ""}>${label}</option>`).join("")}</select>${playback}${clear}</div>
      </div>
      <div class="map-canvas"><div id="mesh-map" class="map ${mapStyle.className}">${state}</div><span class="map-stat">${mapCountLabel(visible, links.length, trailCount)}</span></div>
      <div class="map-footer"><div class="map-legend" aria-label="Map legend"><span class="map-legend-item" style="color:var(--protocol-meshtastic)"><i class="legend-dot"></i>Meshtastic</span><span class="map-legend-item" style="color:var(--protocol-meshcore)"><i class="legend-dot"></i>MeshCore</span><span class="map-legend-item" style="color:var(--protocol-reticulum)"><i class="legend-dot"></i>Reticulum</span><span class="map-legend-item" style="color:#48a9ff"><i class="legend-line"></i>Topology</span><span class="map-legend-item" style="color:#d56cff"><i class="legend-line dashed"></i>Neighbor/SNR</span><span class="map-legend-item" style="color:#ffd166"><i class="legend-line"></i>Position trail</span></div><div class="map-tile-state muted">${mapStyle.detail}</div><div class="map-layer-status">${this._mapLayerStatus("topology")}${this._mapLayerStatus("neighbors")}<span id="position-trail-status" class="map-status ${trailBad ? "bad" : this._positionTrail?.state === "supported" ? "ok" : "quiet"}">${escapeHtml(this._positionTrailStatus())}</span></div></div>
    </section>`;
  }

  _visiblePositionTrail() {
    const trail = this._positionTrail;
    if (!trail || trail.state !== "supported") return null;
    return this._selectedMapSources().some(
      (source) =>
        source.source_id === trail.source_id && source.entry_id === trail.entry_id,
    )
      ? trail
      : null;
  }

  _positionTrailStatus() {
    if (this._positionLoading) return "Position trail: loading bounded history…";
    const trail = this._positionTrail;
    if (!trail) return "Position trail: choose a Meshtastic node marker or node-list action";
    if (trail.state === "permission_denied")
      return "Position trail: permission denied (private positions may require nodes_private:read)";
    if (trail.state === "not_available") return "Position trail: not available for this source";
    if (trail.state === "error") return `Position trail failed: ${trail.message}`;
    if (!trail.fixes.length)
      return `No stored positions for ${trail.node_name} in the last ${this._rangeLabel(trail.hours)}`;
    const index = Math.min(this._positionIndex, trail.fixes.length - 1);
    const fix = trail.fixes[index];
    const bounded = trail.total > trail.fixes.length ? ` · showing ${trail.fixes.length} of ${trail.total}` : "";
    return `${trail.node_name}: ${index + 1}/${trail.fixes.length} · ${readableTime(fix.timestamp)}${bounded}`;
  }

  _rangeLabel(hours) {
    return hours < 24 ? `${hours} hour${hours === 1 ? "" : "s"}` : `${hours / 24} day${hours === 24 ? "" : "s"}`;
  }

  _selectedMapSources() {
    return (this._data?.sources || []).filter(
      (source) =>
        (this._mapProtocol === "all" || source.protocol === this._mapProtocol) &&
        (this._mapSource === "all" || source.source_id === this._mapSource),
    );
  }

  _mapLayerStatus(kind) {
    const summary = mapLayerSummary(kind, this._selectedMapSources());
    return `<span class="map-status ${summary.tone}">${escapeHtml(summary.text)}</span>`;
  }

  _freshness(node) {
    const raw = nodeActivity(node).value;
    const value =
      typeof raw === "number"
        ? raw > 1e11
          ? raw
          : raw * 1000
        : new Date(raw).valueOf();
    if (!Number.isFinite(value)) return "old";
    const age = Date.now() - value;
    return age <= 3600000 ? "fresh" : age <= 86400000 ? "stale" : "old";
  }

  _filteredMapNodes(nodes) {
    return nodes.filter(
      (node) =>
        (this._mapProtocol === "all" || node.protocol === this._mapProtocol) &&
        (this._mapSource === "all" || node.source_id === this._mapSource) &&
        (this._mapFreshness === "all" ||
          this._freshness(node) === this._mapFreshness),
    );
  }

  _nodeKeys(value) {
    if (value === null || value === undefined || value === "") return [];
    const raw = String(value).toLowerCase();
    const keys = [raw];
    const number = raw.startsWith("!")
      ? Number.parseInt(raw.slice(1), 16)
      : /^\d+$/.test(raw)
        ? Number(raw)
        : Number.NaN;
    if (Number.isSafeInteger(number)) {
      keys.push(String(number));
      keys.push(`!${number.toString(16).padStart(8, "0")}`);
    }
    return [...new Set(keys)];
  }

  _nodePositionLookup(source) {
    const positions = new Map();
    const hidden = new Set(
      (source.nodes || [])
        .filter((node) => !nodeIsVisibleOnMap(node))
        .flatMap((node) => [node.id, node.node_num].flatMap((value) => this._nodeKeys(value))),
    );
    const add = (node) => {
      if ([node.id, node.node_num].flatMap((value) => this._nodeKeys(value)).some((key) => hidden.has(key))) return;
      if (node.latitude == null || node.longitude == null) return;
      const point = [Number(node.latitude), Number(node.longitude)];
      if (!point.every(Number.isFinite)) return;
      for (const value of [node.id, node.node_num])
        for (const key of this._nodeKeys(value)) positions.set(key, point);
    };
    for (const node of source.nodes || []) add(node);
    for (const node of source.topology?.nodes || []) add(node);
    return positions;
  }

  _mapLinks() {
    const links = [];
    for (const source of this._selectedMapSources()) {
      const positions = this._nodePositionLookup(source);
      const hidden = new Set(
        (source.nodes || [])
          .filter((node) => !nodeIsVisibleOnMap(node))
          .flatMap((node) => [node.id, node.node_num].flatMap((value) => this._nodeKeys(value))),
      );
      const isHidden = (value) => this._nodeKeys(value).some((key) => hidden.has(key));
      const resolve = (value) =>
        this._nodeKeys(value).map((key) => positions.get(key)).find(Boolean);
      if (this._mapTopology && source.topology?.state === "supported") {
        for (const edge of source.topology.edges) {
          const path = [edge.from_id, ...(edge.route || []), edge.to_id];
          if (path.some(isHidden)) continue;
          const points = path
            .map(resolve)
            .filter(Boolean)
            .filter((point, index, values) => index === 0 || point[0] !== values[index - 1][0] || point[1] !== values[index - 1][1]);
          if (points.length < 2) continue;
          const snr = edge.snr?.length ? ` · SNR ${edge.snr.join(" / ")} dB` : "";
          links.push({kind:"topology", points, tooltip:`${source.name}: stored topology${snr}`});
        }
      }
      if (this._mapNeighbors && source.neighbors?.state === "supported") {
        for (const link of source.neighbors.links) {
          if (isHidden(link.from_id ?? link.from_num) || isHidden(link.to_id ?? link.to_num)) continue;
          const directValues = [
            [link.from_latitude, link.from_longitude],
            [link.to_latitude, link.to_longitude],
          ];
          const direct = directValues.map((point) => point.map(Number));
          const points = directValues.flat().every((value) => value != null) && direct.every((point) => point.every(Number.isFinite))
            ? direct
            : [resolve(link.from_id ?? link.from_num), resolve(link.to_id ?? link.to_num)].filter(Boolean);
          if (points.length < 2) continue;
          const names = `${link.from_name || link.from_id || link.from_num || "unknown"} ↔ ${link.to_name || link.to_id || link.to_num || "unknown"}`;
          const values = [link.snr, link.reverse_snr].filter((value) => value != null);
          links.push({kind:"neighbors", points, tooltip:`${names}${values.length ? ` · SNR ${values.join(" / ")} dB` : ""}`});
        }
      }
    }
    return links;
  }

  _rememberMapView() {
    if (this._mapInstance) {
      this._mapView = {
        center: this._mapInstance.getCenter(),
        zoom: this._mapInstance.getZoom(),
      };
    }
  }
  _destroyMap() {
    if (this._mapInstance) {
      this._mapInstance.remove();
      this._mapInstance = null;
      this._mapLayer = null;
      this._mapLinkLayer = null;
      this._mapTrailLayer = null;
      this._mapHomeLayer = null;
    }
  }

  _initMap(nodes) {
    const element = this.shadowRoot?.querySelector("#mesh-map");
    if (!element || !window.L) return;
    const visible = this._filteredMapNodes(nodes);
    const links = this._mapLinks();
    const trail = this._visiblePositionTrail();
    if (!visible.length && !links.length && !trail?.fixes.length) return;
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    const map = window.L.map(element, {
      zoomControl: false,
      minZoom: 2,
      worldCopyJump: true,
      preferCanvas: true,
      fadeAnimation: !reducedMotion,
      markerZoomAnimation: !reducedMotion,
      zoomAnimation: !reducedMotion,
    });
    window.L.control.zoom({ position: "bottomright" }).addTo(map);
    this._mapInstance = map;
    this._mapNodes = visible;
    this._mapLinksVisible = links;
    if (mapStylePresentation(this._mapStyle).tiles)
      window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      }).addTo(map);
    map.createPane("markers");
    map.getPane("markers").style.zIndex = 650;
    map.createPane("mesh-links");
    map.getPane("mesh-links").style.zIndex = 410;
    map.createPane("position-trail");
    map.getPane("position-trail").style.zIndex = 430;
    if (this._mapView) map.setView(this._mapView.center, this._mapView.zoom);
    else this._fitMap();
    // Leaflet's Canvas renderer needs a settled view before the first stored
    // link and trail draw; otherwise an initial fit can leave overlays blank.
    this._renderMapLinks();
    this._renderPositionTrail();
    this._renderMapMarkers();
    this._renderHomeMarker();
    map.on("zoomend", () => this._renderMapMarkers());
  }

  _renderMapLinks() {
    const map = this._mapInstance;
    if (!map) return;
    this._mapLinkLayer = window.L.layerGroup().addTo(map);
    for (const link of this._mapLinksVisible || []) {
      const topology = link.kind === "topology";
      window.L.polyline(link.points, {
        pane: "mesh-links",
        color: topology ? "#48a9ff" : "#d56cff",
        weight: topology ? 3 : 2,
        opacity: topology ? 0.72 : 0.82,
        dashArray: topology ? null : "7 7",
      }).bindTooltip(escapeHtml(link.tooltip)).addTo(this._mapLinkLayer);
    }
  }

  _renderMapMarkers() {
    const map = this._mapInstance;
    if (!map) return;
    if (this._mapLayer) this._mapLayer.remove();
    this._mapLayer = window.L.layerGroup().addTo(map);
    const zoom = map.getZoom();
    const cell = zoom < 7 ? 70 : zoom < 11 ? 55 : 38;
    const buckets = new Map();
    for (const node of this._mapNodes) {
      const point = map.project([node.latitude, node.longitude], zoom);
      const key = `${Math.floor(point.x / cell)}:${Math.floor(point.y / cell)}`;
      if (!buckets.has(key)) buckets.set(key, []);
      buckets.get(key).push(node);
    }
    for (const group of buckets.values()) {
      if (group.length > 1) {
        const lat =
          group.reduce((sum, node) => sum + node.latitude, 0) / group.length;
        const lon =
          group.reduce((sum, node) => sum + node.longitude, 0) / group.length;
        const marker = window.L.marker([lat, lon], {
          pane: "markers",
          icon: window.L.divIcon({
            className: "",
            html: `<div class="map-cluster">${group.length}</div>`,
            iconSize: [34, 34],
            iconAnchor: [17, 17],
          }),
        }).addTo(this._mapLayer);
        marker.bindTooltip(`${group.length} mesh nodes`);
        marker.on("click", () => {
          if (map.getZoom() < 16) map.setView([lat, lon], map.getZoom() + 2);
          else
            map.fitBounds(
              window.L.latLngBounds(
                group.map((node) => [node.latitude, node.longitude]),
              ),
              { padding: [35, 35], maxZoom: 18 },
            );
        });
        continue;
      }
      const node = group[0];
      const freshness = this._freshness(node);
      const marker = window.L.marker([node.latitude, node.longitude], {
        pane: "markers",
        title: node.name,
        icon: window.L.divIcon({
          className: "",
          html: `<div class="map-marker ${escapeHtml(node.protocol)} ${freshness}"></div>`,
          iconSize: [18, 18],
          iconAnchor: [9, 9],
        }),
      }).addTo(this._mapLayer);
      const signal =
        node.rssi != null
          ? `${node.rssi} dBm`
          : node.snr != null
            ? `${node.snr} dB`
            : "—";
      const link = node.device_id
        ? `<p><a href="/config/devices/device/${encodeURIComponent(node.device_id)}">Open Home Assistant device</a></p>`
        : "";
      const nodeDetail = this._allNodes().some(
        (item) =>
          item.entry_id === node.entry_id &&
          item.source_id === node.source_id &&
          item.id === node.id,
      )
        ? `<p><button data-entry="${escapeHtml(node.entry_id)}" data-source="${escapeHtml(node.source_id)}" data-map-node-detail="${escapeHtml(node.id)}">View node details</button></p>`
        : "";
      const trail = node.protocol === "meshtastic"
        ? `<p><button data-entry="${escapeHtml(node.entry_id)}" data-source="${escapeHtml(node.source_id)}" data-position-node="${escapeHtml(node.id)}" data-node-name="${escapeHtml(node.name)}">Load ${this._rangeLabel(this._positionRange)} trail</button></p>`
        : "";
      const activity = nodeActivity(node);
      marker.bindPopup(
        `<strong>${escapeHtml(node.name)}</strong><p><span class="badge protocol-${escapeHtml(node.protocol)}">${escapeHtml(node.protocol)}</span> · ${escapeHtml(freshness)}</p><p>${escapeHtml(activity.label)}: ${escapeHtml(readableTime(activity.value))}<br>Battery: ${batteryMarkup(node.battery, node.voltage)}<br>Signal: ${escapeHtml(signal)}<br>Source: ${escapeHtml(node.source_id)}</p>${trail}${link}${nodeDetail}`,
      );
      if (
        this._mapFocusNode ===
        `${node.entry_id}\u0000${node.source_id}\u0000${node.id}`
      ) {
        marker.openPopup();
        this._mapFocusNode = null;
      }
    }
  }

  _renderHomeMarker() {
    const map = this._mapInstance;
    if (!map) return;
    if (this._mapHomeLayer) this._mapHomeLayer.remove();
    this._mapHomeLayer = null;
    const home = homeLocation(this._hass);
    if (!this._mapShowHome || !home) return;
    this._mapHomeLayer = window.L.layerGroup().addTo(map);
    window.L.marker([home.latitude, home.longitude], {
      pane: "markers",
      title: home.name,
      zIndexOffset: 1000,
      icon: window.L.divIcon({
        className: "",
        html: '<div class="map-home-marker"><ha-icon icon="mdi:home"></ha-icon></div>',
        iconSize: [34, 34],
        iconAnchor: [17, 17],
      }),
    })
      .bindTooltip(escapeHtml(home.name))
      .addTo(this._mapHomeLayer);
  }

  _renderPositionTrail() {
    const map = this._mapInstance;
    if (!map) return;
    if (this._mapTrailLayer) this._mapTrailLayer.remove();
    this._mapTrailLayer = window.L.layerGroup().addTo(map);
    const trail = this._visiblePositionTrail();
    if (!trail?.fixes.length) return;
    const last = Math.min(this._positionIndex, trail.fixes.length - 1);
    const fixes = trail.fixes.slice(0, last + 1);
    const points = fixes.map((fix) => [fix.latitude, fix.longitude]);
    if (points.length > 1)
      window.L.polyline(points, {
        pane: "position-trail",
        color: "#ffd166",
        weight: 4,
        opacity: 0.9,
      }).bindTooltip(`${escapeHtml(trail.node_name)} · bounded stored position trail`).addTo(this._mapTrailLayer);
    const fix = fixes[fixes.length - 1];
    const detail = [
      readableTime(fix.timestamp),
      fix.altitude == null ? null : `${fix.altitude} m`,
      fix.ground_speed == null ? null : `${fix.ground_speed} m/s`,
      fix.snr == null ? null : `SNR ${fix.snr} dB`,
    ].filter(Boolean).join(" · ");
    window.L.circleMarker([fix.latitude, fix.longitude], {
      pane: "position-trail",
      radius: 7,
      color: "#fff4c2",
      fillColor: "#ffd166",
      fillOpacity: 1,
      weight: 2,
    }).bindTooltip(`${escapeHtml(trail.node_name)}<br>${escapeHtml(detail)}`).addTo(this._mapTrailLayer);
  }

  _updatePositionControls() {
    const status = this.shadowRoot?.querySelector("#position-trail-status");
    if (status) status.textContent = this._positionTrailStatus();
    const progress = this.shadowRoot?.querySelector("#map-position-progress");
    if (progress) progress.value = String(this._positionIndex);
    const play = this.shadowRoot?.querySelector("#map-position-play");
    if (play) play.textContent = this._positionPlaying ? "Pause" : "Play";
  }

  _togglePositionPlayback() {
    const count = this._visiblePositionTrail()?.fixes.length || 0;
    if (count < 2) return;
    if (this._positionPlaying) {
      this._stopPositionPlayback();
      return;
    }
    if (this._positionIndex >= count - 1) this._positionIndex = 0;
    this._positionPlaying = true;
    this._updatePositionControls();
    this._positionPlayTimer = window.setInterval(() => {
      this._positionIndex += 1;
      this._renderPositionTrail();
      if (this._positionIndex >= count - 1) this._stopPositionPlayback();
      else this._updatePositionControls();
    }, 700);
  }

  _stopPositionPlayback() {
    window.clearInterval(this._positionPlayTimer);
    this._positionPlayTimer = null;
    this._positionPlaying = false;
    this._updatePositionControls();
  }

  async _loadPositionHistory(entryId, sourceId, nodeId, nodeName) {
    if (this._positionLoading || !sourceId || !nodeId) return;
    this._stopPositionPlayback();
    this._positionLoading = true;
    this._positionTrail = {
      state: "loading",
      entry_id: entryId,
      source_id: sourceId,
      node_id: nodeId,
      node_name: nodeName || nodeId,
      hours: this._positionRange,
      fixes: [],
      total: 0,
    };
    this._tab = "map";
    this._render();
    try {
      const result = await this._hass.callWS({
        type: "meshmonitor/position_history",
        entry_id: entryId,
        source_id: sourceId,
        node_id: nodeId,
        hours: this._positionRange,
      });
      const fixes = (result.fixes || []).filter((fix) =>
        [Number(fix.latitude), Number(fix.longitude)].every(Number.isFinite),
      ).map((fix) => ({
        ...fix,
        latitude: Number(fix.latitude),
        longitude: Number(fix.longitude),
      })).sort((a, b) => this._historyTime(a.timestamp) - this._historyTime(b.timestamp));
      this._positionTrail = {
        ...result,
        entry_id: entryId,
        source_id: sourceId,
        node_id: nodeId,
        node_name: nodeName || nodeId,
        hours: this._positionRange,
        fixes,
      };
      this._positionIndex = Math.max(0, fixes.length - 1);
    } catch (error) {
      this._positionTrail = {
        state: "error",
        entry_id: entryId,
        source_id: sourceId,
        node_id: nodeId,
        node_name: nodeName || nodeId,
        hours: this._positionRange,
        fixes: [],
        total: 0,
        message: error?.message || String(error),
      };
    } finally {
      this._positionLoading = false;
      this._render();
    }
  }

  _historyTime(value) {
    const number = Number(value);
    return Number.isFinite(number)
      ? number > 1e11 ? number : number * 1000
      : new Date(value).valueOf() || 0;
  }

  _fitMap() {
    const map = this._mapInstance;
    if (!map) return;
    const points = [
      ...(this._mapNodes || []).map((node) => [node.latitude, node.longitude]),
      ...(this._mapLinksVisible || []).flatMap((link) => link.points),
      ...(this._visiblePositionTrail()?.fixes || []).map((fix) => [fix.latitude, fix.longitude]),
    ];
    if (!points.length) return;
    const bounds = window.L.latLngBounds(points);
    map.fitBounds(bounds, { padding: [35, 35], maxZoom: 14 });
  }

  _focusHome() {
    const home = homeLocation(this._hass);
    if (!this._mapInstance || !home) return;
    this._mapInstance.setView([home.latitude, home.longitude], 14);
  }

  _nodes(nodes, sources = []) {
    if (this._loading && !this._data)
      return this._panelState("Nodes", "Loading node inventory…", "Reading the latest sanitized coordinator snapshots from Home Assistant.");
    if (!sources.length)
      return this._panelState(
        "Nodes",
        this._error ? "Node inventory is unavailable" : "Waiting for node data",
        this._error
          ? "The panel could not load a coordinator snapshot. Use Refresh after the connection recovers."
          : "No loaded MeshMonitor sources are visible yet. Configure or reload a source to populate the inventory.",
      );
    const query = this._query.toLowerCase();
    const filtered = sortNodes(
      nodes.filter(
        (node) =>
          `${node.name} ${node.id} ${node.protocol} ${node.role || ""} ${node.model || ""} ${nodeRoleModelLabel(node.role, node.model, node.protocol) || ""}`
            .toLowerCase()
            .includes(query) &&
          (this._nodeProtocol === "all" ||
            node.protocol === this._nodeProtocol) &&
          (this._nodeFavorite === "all" || node.favorite) &&
          (this._nodePosition === "all" ||
            (node.latitude != null && node.longitude != null)),
      ),
      this._nodeSort,
      this._nodeDirection,
    );
    const rows = filtered.length
      ? filtered
          .map((node) => {
            const time = relativeNodeActivity(node);
            const favoriteLabel = node.favorite
              ? `Remove ${node.name} from favorites`
              : `Add ${node.name} to favorites`;
            const favoriteTitle = node.favorites_enabled
              ? "Store favorite in MeshMonitor"
              : "Enable favorites in this source's integration options";
            const favoriteKey = `${node.entry_id}\u0000${node.source_id}\u0000${node.id}`;
            const favoritePending = this._favoritePending.has(favoriteKey);
            return `<tr class="node-row" data-entry="${escapeHtml(node.entry_id)}" data-source="${escapeHtml(node.source_id)}" data-node-detail="${escapeHtml(node.id)}" tabindex="0" role="button" aria-label="Open details for ${escapeHtml(node.name)}" aria-haspopup="dialog"><td class="node-favorite"><button data-entry="${escapeHtml(node.entry_id)}" data-source="${escapeHtml(node.source_id)}" data-favorite-node="${escapeHtml(node.id)}" data-favorite="${node.favorite}" aria-label="${escapeHtml(favoriteLabel)}" title="${favoriteTitle}" ${node.favorites_enabled && !favoritePending ? "" : "disabled"}>${node.favorite ? "★" : "☆"}</button></td><td class="node-name">${escapeHtml(node.name)}<span class="node-mobile-protocol"><span class="badge protocol-${escapeHtml(node.protocol)}">${escapeHtml(node.protocol)}</span></span></td><td class="node-protocol"><span class="badge protocol-${escapeHtml(node.protocol)}">${escapeHtml(node.protocol)}</span></td><td class="node-last-heard"><span class="last-heard ${time.state}" data-last-heard="${escapeHtml(nodeActivity(node).value ?? "")}" data-activity-label="${escapeHtml(time.activityLabel)}" title="${escapeHtml(time.title)}" aria-label="${escapeHtml(`${time.label}. ${time.title}`)}">${escapeHtml(time.label)}</span></td><td class="node-power">${nodeListBatteryMarkup(node.battery)}</td><td class="node-signal">${node.rssi != null ? `${node.rssi} dBm` : node.snr != null ? `${node.snr} dB` : "—"}</td><td class="node-hops">${node.hops ?? "—"}</td><td class="node-role">${escapeHtml(nodeRoleModelLabel(node.role, node.model, node.protocol) || "—")}</td></tr>`;
          })
          .join("")
      : `<tr><td colspan="8" class="map-empty">${nodes.length ? "No nodes match these filters." : "No nodes are available in the current source snapshots."}</td></tr>`;
    const sortHeader = (key, label, className) => {
      const active = this._nodeSort === key;
      const direction = active ? this._nodeDirection : "none";
      const indicator = active ? (direction === "asc" ? "▲" : "▼") : "";
      const nextDirection = active && direction === "asc" ? "descending" : "ascending";
      const ariaSort = direction === "none" ? "none" : direction === "asc" ? "ascending" : "descending";
      return `<th class="${className}" aria-sort="${ariaSort}"><button type="button" class="node-sort-button" data-node-sort-key="${key}" aria-label="Sort by ${label}, ${nextDirection}">${label}<span class="node-sort-indicator" aria-hidden="true">${indicator}</span></button></th>`;
    };
    return `<div class="toolbar"><div class="search-field"><input id="search" aria-label="Search nodes" value="${escapeHtml(this._query)}" placeholder="Search names, IDs, roles, or hardware"><button type="button" id="clear-node-search" class="search-clear" aria-label="Clear node search" title="Clear search" ${this._query ? "" : "hidden"}>×</button></div><select id="node-protocol" aria-label="Filter nodes by protocol"><option value="all">All protocols</option><option value="meshtastic" ${this._nodeProtocol === "meshtastic" ? "selected" : ""}>Meshtastic</option><option value="meshcore" ${this._nodeProtocol === "meshcore" ? "selected" : ""}>MeshCore</option></select><select id="node-favorite" aria-label="Filter favorite nodes"><option value="all">All nodes</option><option value="favorites" ${this._nodeFavorite !== "all" ? "selected" : ""}>Favorites only</option></select><select id="node-position" aria-label="Filter positioned nodes"><option value="all">Any position</option><option value="positioned" ${this._nodePosition !== "all" ? "selected" : ""}>Positioned only</option></select><select id="node-sort" aria-label="Sort nodes by">${[["name","Name"],["last_heard","Last seen"],["battery","Battery"],["signal","Signal"],["hops","Hops"],["protocol","Protocol"],["role","Role"]].map(([v,n])=>`<option value="${v}" ${this._nodeSort===v?"selected":""}>${n}</option>`).join("")}</select><select id="node-direction" aria-label="Node sort direction"><option value="asc" ${this._nodeDirection==="asc"?"selected":""}>Ascending</option><option value="desc" ${this._nodeDirection==="desc"?"selected":""}>Descending</option></select></div><div class="table nodes-table"><table><thead><tr><th class="node-favorite" aria-label="Favorite">★</th>${sortHeader("name", "Name", "node-name")}${sortHeader("protocol", "Protocol", "node-protocol")}${sortHeader("last_heard", "Last seen", "node-last-heard")}${sortHeader("battery", "Battery", "node-power")}${sortHeader("signal", "Signal", "node-signal")}${sortHeader("hops", "Hops", "node-hops")}${sortHeader("role", "Role", "node-role")}</tr></thead><tbody>${rows}</tbody></table></div><p class="muted">Showing ${filtered.length} of ${nodes.length} nodes. Select a row for details. Favorites stay first; sort preferences are saved in this browser.</p>`;
  }

  _trendCard(label, unit, points, extraClass = "") {
    const latest = points[points.length - 1];
    const values = points.map((point) => point.numeric_value);
    const minimum = Math.min(...values);
    const maximum = Math.max(...values);
    const suffix = unit ? ` ${unit}` : "";
    const value = `${latest.numeric_value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`;
    const range = `${minimum.toLocaleString(undefined, { maximumFractionDigits: 2 })}–${maximum.toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`;
    const chartLabel = `${label}: ${points.length} stored points, latest ${value}, range ${range}`;
    return `<article class="trend-card ${escapeHtml(extraClass)}"><div class="trend-card-head"><div><h4>${escapeHtml(label)}</h4><div class="trend-range">${points.length} point${points.length === 1 ? "" : "s"} · ${escapeHtml(range)}</div></div><span class="trend-value">${escapeHtml(value)}</span></div><svg class="trend-chart" viewBox="0 0 240 64" preserveAspectRatio="none" role="img" aria-label="${escapeHtml(chartLabel)}"><line class="grid-line" x1="0" x2="240" y1="32" y2="32"></line><polyline points="${sparklinePoints(points)}"></polyline></svg><div class="trend-range">Latest ${escapeHtml(readableTime(latest.timestamp))}</div></article>`;
  }

  _nodeHistoryStateMarkup(presentation) {
    return `<div class="node-history-state ${escapeHtml(presentation.state)}" role="status"><div><h4>${escapeHtml(presentation.title)}</h4><p class="muted">${escapeHtml(presentation.detail)}</p></div></div>`;
  }

  _nodeHistorySection(endpoint, label, content) {
    const presentation = nodeHistoryStatePresentation(endpoint, label);
    if (presentation) return this._nodeHistoryStateMarkup(presentation);
    return content || this._nodeHistoryStateMarkup(
      nodeHistoryStatePresentation({ state: "supported", points: [] }, label),
    );
  }

  _nodeDetailDrawer(nodes, sources) {
    if (!this._nodeDetail) return "";
    const node = nodes.find(
      (item) =>
        item.source_id === this._nodeDetail.source_id &&
        item.entry_id === this._nodeDetail.entry_id &&
        item.id === this._nodeDetail.node_id,
    );
    if (!node) return "";
    const source = sources.find(
      (item) => item.source_id === node.source_id && item.entry_id === node.entry_id,
    );
    const time = relativeNodeActivity(node);
    const telemetry = this._nodeHistory?.telemetry;
    const linkQuality = this._nodeHistory?.link_quality;
    const telemetryCards = telemetrySeries(telemetry?.points)
      .slice(0, 12)
      .map((series) =>
        this._trendCard(series.type, series.unit, series.points),
      )
      .join("");
    const linkPoints = normalizeHistoryPoints(linkQuality?.points, "quality");
    const linkCard = linkPoints.length
      ? this._trendCard("Link quality", "%", linkPoints, "link-quality")
      : "";
    const loadingState = {
      state: "loading",
      title: "Loading stored history…",
      detail: "Reading at most two fixed-window history endpoints from MeshMonitor.",
    };
    const historyBody = this._nodeHistoryLoading
      ? `${this._nodeHistoryStateMarkup(loadingState)}${this._nodeHistoryStateMarkup(loadingState)}`
      : this._nodeHistoryError
        ? this._nodeHistoryStateMarkup({
            state: "error",
            title: "Node history could not be loaded",
            detail: this._nodeHistoryError,
          })
        : `<div class="trend-list" aria-label="Telemetry history">${this._nodeHistorySection(telemetry, "Telemetry", telemetryCards)}</div><div class="trend-list" aria-label="Link-quality history">${this._nodeHistorySection(linkQuality, "Link quality", linkCard)}</div>`;
    const truncation = [telemetry, linkQuality].some((result) => result?.truncated)
      ? " The response reached the 1,000-point panel cap."
      : "";
    const presentation = nodeDetailPresentation(
      node,
      source,
      this._data?.can_send_messages === true,
    );
    const favoriteKey = `${node.entry_id}\u0000${node.source_id}\u0000${node.id}`;
    const favoritePending = this._favoritePending.has(favoriteKey);
    const requestPending = Boolean(this._nodeActionPending);
    const groups = presentation.groups.map((group) =>
      `<section class="node-detail-group${group.title === "Position" ? " position" : ""}"><h3>${escapeHtml(group.title)}</h3>${group.empty ? `<p class="node-detail-group-empty">Position has not been reported for this node.</p>` : `<dl class="node-detail-meta">${group.items.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join("")}</dl>`}</section>`,
    ).join("");
    const actions = [
      presentation.actions.message
        ? `<button id="node-detail-message" class="primary"><ha-icon icon="mdi:message-text-outline" aria-hidden="true"></ha-icon>Send message</button>`
        : "",
      presentation.actions.map
        ? `<button id="node-detail-map" class="primary"><ha-icon icon="mdi:map-marker-outline" aria-hidden="true"></ha-icon>View on map</button>`
        : "",
      presentation.actions.requests
        ? `<button data-node-request="traceroute" ${requestPending ? "disabled" : ""}><ha-icon icon="mdi:routes" aria-hidden="true"></ha-icon>${this._nodeActionPending === "traceroute" ? "Requesting…" : "Trace route"}</button>`
        : "",
      presentation.actions.requests
        ? `<button data-node-request="position" ${requestPending ? "disabled" : ""}><ha-icon icon="mdi:map-marker-question-outline" aria-hidden="true"></ha-icon>${this._nodeActionPending === "position" ? "Requesting…" : "Request position"}</button>`
        : "",
      presentation.actions.device
        ? `<a href="/config/devices/device/${encodeURIComponent(node.device_id)}"><ha-icon icon="mdi:home-assistant" aria-hidden="true"></ha-icon>Open HA device</a>`
        : "",
      presentation.actions.requests
        ? `<button data-node-request="nodeinfo" ${requestPending ? "disabled" : ""}><ha-icon icon="mdi:information-outline" aria-hidden="true"></ha-icon>${this._nodeActionPending === "nodeinfo" ? "Requesting…" : "Request node information"}</button>`
        : "",
      presentation.actions.requests
        ? `<button data-node-request="neighbors" ${requestPending ? "disabled" : ""}><ha-icon icon="mdi:account-network-outline" aria-hidden="true"></ha-icon>${this._nodeActionPending === "neighbors" ? "Requesting…" : "Request neighbor information"}</button>`
        : "",
      presentation.actions.ignore
        ? `<button id="node-detail-ignore" class="warning" ${requestPending ? "disabled" : ""}><ha-icon icon="mdi:${node.ignored ? "eye-outline" : "eye-off-outline"}" aria-hidden="true"></ha-icon>${node.ignored ? "Unignore node" : "Ignore node"}</button>`
        : "",
    ].filter(Boolean).join("");
    const history = presentation.monitored
      ? `<section class="node-history" aria-label="Monitored source diagnostics"><div class="node-history-head"><div><div class="section-eyebrow">Monitored source diagnostics</div><h3>Telemetry and link quality</h3></div><div class="node-history-controls"><select id="node-history-range" aria-label="Node history time range">${[[1,"1 hour"],[6,"6 hours"],[24,"24 hours"],[72,"3 days"],[168,"7 days"]].map(([value,label]) => `<option value="${value}" ${this._nodeHistoryHours === value ? "selected" : ""}>${label}</option>`).join("")}</select><button id="load-node-history" ${this._nodeHistoryLoading ? "disabled" : ""}>${this._nodeHistory ? "Refresh" : "Load history"}</button></div></div><p class="node-history-note muted">Stored diagnostics for this directly monitored source node.${escapeHtml(truncation)}</p>${historyBody}</section>`
      : "";
    const ignoreReview = this._nodeIgnoreReview
      ? `<section class="node-detail-group" role="alertdialog" aria-label="Confirm ignore change"><h3>${node.ignored ? "Unignore" : "Ignore"} ${escapeHtml(node.name)}?</h3><p>This changes MeshMonitor's server-only ignore state.</p><p class="muted">It does not sync the change to the radio.</p><div class="node-detail-actions"><button id="cancel-node-ignore">Cancel</button><button id="confirm-node-ignore" class="danger">${node.ignored ? "Unignore node" : "Ignore node"}</button></div></section>`
      : "";
    return `<div class="node-detail-scrim"><section class="node-detail" role="dialog" aria-modal="true" aria-labelledby="node-detail-title" tabindex="-1"><div class="node-detail-head"><div><span class="badge protocol-${escapeHtml(node.protocol)}">${escapeHtml(node.protocol)}</span><div class="node-detail-title-row"><h2 id="node-detail-title">${escapeHtml(node.name)}</h2>${presentation.actions.favorite ? `<button class="node-detail-favorite" data-entry="${escapeHtml(node.entry_id)}" data-source="${escapeHtml(node.source_id)}" data-favorite-node="${escapeHtml(node.id)}" data-favorite="${node.favorite}" aria-label="${node.favorite ? "Remove from favorites" : "Add to favorites"}" ${favoritePending ? "disabled" : ""}>${node.favorite ? "★" : "☆"}</button>` : ""}</div><p class="muted">${escapeHtml(node.id)} · ${escapeHtml(source?.name || node.source_id)}</p></div><button id="close-node-detail" class="node-detail-close" aria-label="Close node details">×</button></div><div class="node-detail-body"><div class="node-detail-summary"><div class="node-detail-stat"><span>${escapeHtml(time.activityLabel)}</span><strong class="last-heard ${time.state}" title="${escapeHtml(time.title)}">${escapeHtml(time.label)}</strong></div><div class="node-detail-stat power-stat"><span>Power</span><strong>${nodeDetailBatteryMarkup(node.battery, node.voltage)}</strong></div><div class="node-detail-stat"><span>RSSI</span><strong>${escapeHtml(presentation.signal.rssi || "Not reported")}</strong></div><div class="node-detail-stat"><span>SNR</span><strong>${escapeHtml(presentation.signal.snr || "Not reported")}</strong></div></div><div class="node-detail-groups">${groups}</div>${actions ? `<div class="node-detail-actions">${actions}</div>` : ""}${ignoreReview}${this._nodeActionStatus ? `<p class="node-detail-position-note" role="status">${escapeHtml(this._nodeActionStatus)}</p>` : ""}${history}</div></section></div>`;
  }

  _openNodeDetail(entryId, sourceId, nodeId) {
    this._nodeHistoryGeneration += 1;
    this._nodeDetail = { entry_id: entryId, source_id: sourceId, node_id: nodeId };
    this._nodeActionStatus = "";
    this._nodeActionPending = "";
    this._nodeIgnoreReview = false;
    this._nodeHistory = null;
    this._nodeHistoryLoading = false;
    this._nodeHistoryError = "";
    this._render();
    window.requestAnimationFrame(() =>
      this.shadowRoot?.querySelector("#close-node-detail")?.focus(),
    );
  }

  _closeNodeDetail(restoreFocus = true) {
    const detail = this._nodeDetail;
    this._nodeHistoryGeneration += 1;
    this._nodeDetail = null;
    this._nodeHistory = null;
    this._nodeHistoryLoading = false;
    this._nodeHistoryError = "";
    this._render();
    if (restoreFocus && detail)
      window.requestAnimationFrame(() => {
        const trigger = [...this.shadowRoot.querySelectorAll("[data-node-detail]")].find(
          (row) =>
            row.dataset.entry === detail.entry_id &&
            row.dataset.source === detail.source_id &&
            row.dataset.nodeDetail === detail.node_id,
        );
        trigger?.focus();
      });
  }

  _messageNodeFromDetail() {
    const detail = this._nodeDetail;
    const node = detail && this._allNodes().find(
      (item) =>
        item.entry_id === detail.entry_id &&
        item.source_id === detail.source_id &&
        item.id === detail.node_id,
    );
    if (!node) return;
    const key = `direct:${node.protocol}:${node.id}`;
    this._nodeDirectTarget = {
      key,
      type: "direct",
      protocol: node.protocol,
      name: node.name,
      detail: "Direct message",
      recipient: node.id,
    };
    this._closeNodeDetail(false);
    this._tab = "messages";
    this._selectConversation(key);
    window.requestAnimationFrame(() =>
      this.shadowRoot?.querySelector("#compose-text")?.focus(),
    );
  }

  _mapNodeFromDetail() {
    const detail = this._nodeDetail;
    const node = detail && this._allNodes().find(
      (item) =>
        item.entry_id === detail.entry_id &&
        item.source_id === detail.source_id &&
        item.id === detail.node_id,
    );
    if (!node || node.latitude == null || node.longitude == null) return;
    this._mapProtocol = node.protocol;
    this._mapSource = node.source_id;
    this._mapFreshness = "all";
    this._mapView = {
      center: [Number(node.latitude), Number(node.longitude)],
      zoom: 18,
    };
    this._mapFocusNode = `${node.entry_id}\u0000${node.source_id}\u0000${node.id}`;
    this._closeNodeDetail(false);
    this._tab = "map";
    this._render();
  }

  _nodeDetailFromMap(entryId, sourceId, nodeId) {
    const node = this._allNodes().find(
      (item) =>
        item.entry_id === entryId &&
        item.source_id === sourceId &&
        item.id === nodeId,
    );
    if (!node) return;
    this._tab = "nodes";
    this._openNodeDetail(entryId, sourceId, nodeId);
  }

  _nodeDetailKeydown(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      this._closeNodeDetail();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = [
      ...event.currentTarget.querySelectorAll(
        'button:not(:disabled),a[href],select:not(:disabled),[tabindex]:not([tabindex="-1"])',
      ),
    ];
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && this.shadowRoot.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && this.shadowRoot.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  async _loadNodeHistory() {
    if (!this._nodeDetail || this._nodeHistoryLoading) return;
    const detail = { ...this._nodeDetail };
    const generation = ++this._nodeHistoryGeneration;
    this._nodeHistoryLoading = true;
    this._nodeHistoryError = "";
    this._render();
    try {
      const result = await this._hass.callWS({
        type: "meshmonitor/node_history",
        entry_id: detail.entry_id,
        source_id: detail.source_id,
        node_id: detail.node_id,
        hours: this._nodeHistoryHours,
      });
      if (generation === this._nodeHistoryGeneration) this._nodeHistory = result;
    } catch (error) {
      if (generation === this._nodeHistoryGeneration)
        this._nodeHistoryError = error?.message || String(error);
    } finally {
      if (generation === this._nodeHistoryGeneration) {
        this._nodeHistoryLoading = false;
        this._render();
      }
    }
  }

  _refreshNodeTimes(now = Date.now()) {
    if (this._tab !== "nodes") return;
    this.shadowRoot?.querySelectorAll("[data-last-heard]").forEach((element) => {
      const activityLabel = element.dataset.activityLabel || "Last heard";
      const time = relativeNodeTime(element.dataset.lastHeard, now, activityLabel);
      element.textContent = time.label;
      element.title = time.title;
      element.setAttribute("aria-label", `${time.label}. ${time.title}`);
      element.className = `last-heard ${time.state}`;
    });
  }

  _messageTime(message) {
    return messageTimestampMs(message);
  }

  _unread(messages) {
    return messages.filter(
      (message) =>
        messagePresentation(message, this._messageReadAt(message), this._data?.sources || []).outgoing !== true &&
        this._messageTime(message) > this._messageReadAt(message),
    ).length;
  }

  _messageReadAt(message) {
    return this._conversationLastRead?.[this._conversationKey(message)] ?? this._lastRead;
  }

  _conversationKey(message) {
    // Conversation keys intentionally contain only protocol routing metadata.
    // Message bodies never enter localStorage or the Home Assistant registries.
    return messageConversationKey(message);
  }

  _toggleConversationPreference(kind, key) {
    if (!key || key === "all") return;
    const set = kind === "pinned" ? this._pinnedConversations : this._mutedConversations;
    if (set.has(key)) set.delete(key); else set.add(key);
    localStorage.setItem(`meshmonitor.messages.${kind}`, JSON.stringify([...set]));
    this._render();
  }

  _conversationCatalog(messages, sources) {
    // Seed the rail from the sanitized channel inventory so empty channels are
    // still useful destinations before the first message arrives.
    const catalog = messageConversationCatalog(
      messages,
      sources,
      this._pinnedConversations,
    );
    if (
      this._nodeDirectTarget &&
      !catalog.some((item) => item.key === this._nodeDirectTarget.key)
    )
      catalog.push(this._nodeDirectTarget);
    return catalog;
  }

  _selectConversation(key, keepReplyContext = false) {
    if (!key) return;
    if (key !== "all") this._markConversationRead(key);
    this._messageDrafts.set(this._conversation, this._composeText);
    this._conversation = key;
    this._composeText = this._messageDrafts.get(key) || "";
    this._composeSource = "";
    this._sendStatus = "";
    this._sendReview = null;
    if (!keepReplyContext) this._replyContext = null;
    localStorage.setItem("meshmonitor.messages.conversation", key);
    this._render();
  }

  _restoreNotificationDeepLink() {
    if (this._tab !== "messages" || !this._linkedMessageId) return;
    window.requestAnimationFrame(() => {
      const target = [...this.shadowRoot.querySelectorAll("[data-message-id]")]
        .find((item) => item.dataset.messageId === this._linkedMessageId);
      if (!target) return;
      target.scrollIntoView({block: "center"});
      target.setAttribute("tabindex", "-1");
      target.focus({preventScroll: true});
      target.classList.add("notification-target");
      window.setTimeout(() => target.classList.remove("notification-target"), 2400);
      this._linkedMessageId = "";
    });
  }

  _applyNotificationDeepLink() {
    const notificationLink = notificationDeepLink(window.location.search);
    if (!notificationLink) return;
    this._tab = "messages";
    this._conversation = notificationLink.conversation;
    this._linkedMessageId = notificationLink.messageId;
    localStorage.setItem("meshmonitor.messages.conversation", notificationLink.conversation);
    this._render();
  }

  _markConversationRead(key, readAt = Date.now()) {
    if (!key || key === "all") return;
    this._conversationLastRead[key] = readAt;
    localStorage.setItem(
      "meshmonitor.messages.lastReadByConversation",
      JSON.stringify(this._conversationLastRead),
    );
  }

  _activateMessageReply(replyKey) {
    let identity;
    try {
      identity = JSON.parse(decodeURIComponent(replyKey));
    } catch {
      return;
    }
    const message = (this._data?.messages || []).find(
      (item) =>
        String(item.entry_id || "") === String(identity[0] || "") &&
        String(item.id || "") === String(identity[1] || ""),
    );
    if (!message) return;
    const key = this._conversationKey(message);
    if (key.includes(":unknown")) {
      this._sendStatus = "This message has no stable reply destination.";
      this._render();
      return;
    }
    const presentation = messagePresentation(message, this._lastRead, this._data?.sources || []);
    this._selectConversation(key, true);
    this._replyContext = {
      sender: presentation.sender,
      body: presentation.body,
    };
    this._render();
    window.requestAnimationFrame(() =>
      this.shadowRoot.querySelector("#compose-text")?.focus(),
    );
  }

  async _loadNotificationSettings() {
    try {
      this._notificationSettings = await this._hass.callWS({
        type: "meshmonitor/notification_settings",
      });
    } catch (error) {
      this._notificationSettings = { unavailable: true, enabled: false, targets: [] };
      this._notificationError = error?.message || "Notification settings are unavailable.";
    }
  }

  async _saveNotificationSettings() {
    const enabled = Boolean(this.shadowRoot.querySelector("#notification-enabled")?.checked);
    const target = this.shadowRoot.querySelector("#notification-target")?.value || "";
    const scope = this.shadowRoot.querySelector("#notification-scope")?.value || "all";
    const includePreview = Boolean(this.shadowRoot.querySelector("#notification-preview")?.checked);
    if (enabled && !target) {
      this._notificationError = "Choose a Home Assistant notification target before enabling alerts.";
      this._render();
      return;
    }
    this._notificationSaving = true;
    this._notificationError = "";
    this._render();
    try {
      this._notificationSettings = await this._hass.callWS({
        type: "meshmonitor/update_notification_settings",
        enabled,
        target,
        scope,
        include_preview: includePreview,
      });
      this._notificationDialogOpen = false;
    } catch (error) {
      this._notificationError = error?.message || "Notification settings could not be saved.";
    } finally {
      this._notificationSaving = false;
      this._render();
    }
  }

  _notificationBell() {
    const enabled = Boolean(this._notificationSettings?.enabled);
    const label = enabled
      ? "Message notifications enabled"
      : "Message notifications disabled";
    const path = enabled
      ? "M12 22a2 2 0 0 0 2-2h-4a2 2 0 0 0 2 2Zm6-6v-5a6 6 0 0 0-4.5-5.81V4a1.5 1.5 0 0 0-3 0v1.19A6 6 0 0 0 6 11v5l-2 2v1h16v-1l-2-2Z"
      : "M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0";
    return `<button id="notification-bell" class="notification-bell ${enabled ? "enabled" : ""}" aria-label="${label}" aria-haspopup="dialog" title="${label}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${path}"/></svg></button>`;
  }

  _notificationDialog() {
    if (!this._notificationDialogOpen) return "";
    const settings = this._notificationSettings || {
      enabled: false, target: "", scope: "all", include_preview: false, targets: [],
    };
    const targets = Array.isArray(settings.targets) ? settings.targets : [];
    const targetChoices = targets.length
      ? `<label class="notification-field">Notification endpoint<select id="notification-target">${targets.map((target) => `<option value="${escapeHtml(target.id)}" ${settings.target === target.id ? "selected" : ""}>${escapeHtml(target.label)} — ${escapeHtml(target.entity_id)}</option>`).join("")}</select></label>`
      : `<p class="notification-empty"><strong>No notification targets found.</strong><br>Add a Home Assistant notify entity, then reopen this dialog.</p>`;
    const missingTarget = settings.target && settings.target_available === false
      ? `<p class="notification-error">The saved notification target is no longer available. Choose another target or disable alerts.</p>`
      : "";
    const enableDisabled = !targets.length && !settings.target ? "disabled" : "";
    return `<div class="notification-scrim"><section class="notification-dialog" role="dialog" aria-modal="true" aria-labelledby="notification-dialog-title"><div class="notification-dialog-head"><h2 id="notification-dialog-title">Message notifications</h2><button id="close-notification-dialog" aria-label="Close notification settings">×</button></div><div class="notification-dialog-body"><label class="notification-toggle"><input id="notification-enabled" type="checkbox" ${settings.enabled ? "checked" : ""} ${enableDisabled}>Notify me about new messages</label>${targetChoices}<label class="notification-field">Messages<select id="notification-scope"><option value="all" ${settings.scope === "all" ? "selected" : ""}>All incoming messages</option><option value="channel" ${settings.scope === "channel" ? "selected" : ""}>Channel messages only</option><option value="direct" ${settings.scope === "direct" ? "selected" : ""}>Direct messages only</option></select></label><label class="notification-toggle"><input id="notification-preview" type="checkbox" ${settings.include_preview ? "checked" : ""}>Include message preview</label><p class="notification-help">Works while this panel is closed. History, sent messages, and replays are excluded.</p>${missingTarget}${this._notificationError ? `<p class="notification-error" role="alert">${escapeHtml(this._notificationError)}</p>` : ""}</div><div class="notification-dialog-actions"><button id="cancel-notification-settings" ${this._notificationSaving ? "disabled" : ""}>Cancel</button><button id="save-notification-settings" class="primary" ${this._notificationSaving || settings.unavailable ? "disabled" : ""}>${this._notificationSaving ? "Saving…" : "Save"}</button></div></section></div>`;
  }

  _messages(messages, sourceEntries, messageStatus) {
    if (this._loading && !this._data)
      return this._panelState("Messages", "Loading conversations…", "Reading the bounded recent-message snapshot already held by Home Assistant.");
    if (!sourceEntries.length)
      return this._panelState(
        "Messages",
        this._error ? "Conversations are unavailable" : "Waiting for source data",
        this._error
          ? "The panel could not load a coordinator snapshot. Use Refresh after the connection recovers."
          : "No loaded MeshMonitor sources are visible yet. Configure or reload a source before using conversations.",
      );
    const query = this._messageQuery.toLowerCase();
    const messageSources = [
      ...new Map(
        messages
          .flatMap((message) => message.receptions || [])
          .map((reception) => [
            reception.source_id,
            reception.source_name || reception.source_id,
          ]),
      ).entries(),
    ];
    if (
      this._messageSource !== "all" &&
      !messageSources.some(([id]) => id === this._messageSource)
    )
      this._messageSource = "all";
    const nodes = this._allNodes();
    const favoriteIds = new Set(nodes.filter((node) => node.favorite).map((node) => node.id));
    const catalog = this._conversationCatalog(messages, sourceEntries);
    if (this._conversation !== "all" && !catalog.some((item) => item.key === this._conversation)) this._conversation = "all";
    const unreadCounts = conversationUnreadCounts(
      messages,
      Object.fromEntries(catalog.map((item) => [
        item.key,
        this._conversationLastRead[item.key] ?? this._lastRead,
      ])),
    );
    const filtered = sortMessagesChronologically(messages.filter(
      (message) =>
        (this._conversation === "all" || this._conversationKey(message) === this._conversation) &&
        (this._messageProtocol === "all" ||
          message.protocol === this._messageProtocol) &&
        (this._messageSource === "all" ||
          (message.receptions || []).some(
            (reception) => reception.source_id === this._messageSource,
          )) &&
        (this._messageScope === "all" ||
          (this._messageScope === "direct") ===
            (message.channel === -1 || message.channel == null)) &&
        `${message.from_name || ""} ${message.from_id || ""} ${message.channel_name || ""} ${message.text || ""}`
          .toLowerCase()
          .includes(query) && (!this._messageUnread || this._messageTime(message) > this._messageReadAt(message)) && (!this._messageFavorite || favoriteIds.has(message.from_id)),
    ));
    const selected = catalog.find((item) => item.key === this._conversation);
    this._pendingMessages = this._pendingMessages.filter((pending) => {
      if (pending.state !== "queued") return true;
      return !messages.some((message) =>
        messagePresentation(message, this._lastRead, this._data?.sources || []).outgoing === true &&
        this._conversationKey(message) === pending.conversationKey &&
        message.text === pending.body &&
        Math.abs(this._messageTime(message) - pending.createdAt) < 300000
      );
    });
    let previousDay = "";
    const timeline = filtered.map((message) => {
      const replyKey = encodeURIComponent(
        JSON.stringify([message.entry_id || "", message.id || ""]),
      );
      const presentation = messagePresentation(message, this._messageReadAt(message), this._data?.sources || []);
      const date = new Date(presentation.timestamp);
      const validDate = !Number.isNaN(date.valueOf()) && presentation.timestamp > 0;
      const day = validDate ? date.toLocaleDateString(undefined,{weekday:"short",month:"short",day:"numeric",year:"numeric"}) : "Unknown date";
      const divider = day !== previousDay ? `<div class="day-divider" role="separator" aria-label="${escapeHtml(day)}"><span>${escapeHtml(day)}</span></div>` : "";
      previousDay = day;
      const time = validDate ? date.toLocaleTimeString([],{hour:"numeric",minute:"2-digit"}) : "Unknown time";
      const favorite = !presentation.outgoing && favoriteIds.has(message.from_id);
      const provenance = presentation.sourceNames.join(", ");
      const destination = this._conversationKey(message);
      const openable = this._conversation === "all" && !destination.includes(":unknown");
      return `${divider}<article class="message ${escapeHtml(presentation.outgoing?"outgoing":"incoming")} ${presentation.unread?"unread":""} ${openable?"openable":""}" role="${openable?"button":"listitem"}" data-message-id="${escapeHtml(String(message.id || ""))}" ${openable?`tabindex="0" data-open-conversation="${escapeHtml(destination)}" aria-label="Open ${escapeHtml(message.channel_name || presentation.sender)} conversation"`:""}><div class="message-head"><div class="message-identity"><span class="message-sender">${favorite?"★ ":""}${escapeHtml(presentation.sender)}</span></div><time class="message-time" datetime="${validDate?escapeHtml(date.toISOString()):""}">${escapeHtml(time)}</time></div><div class="message-text">${escapeHtml(presentation.body)}</div><div class="message-meta"><span class="message-protocol ${escapeHtml(presentation.protocol)}">${escapeHtml(presentation.protocol)}</span><span title="${escapeHtml(provenance)}">${escapeHtml(presentation.sourceSummary)}</span>${presentation.deliveryState?`<span class="message-delivery">${escapeHtml(presentation.deliveryState)}</span>`:""}<button type="button" class="message-reply" data-reply-message="${replyKey}" aria-label="Reply to ${escapeHtml(presentation.sender)}">Reply</button></div></article>`;
    }).join("");
    const pendingTimeline = this._pendingMessages
      .filter((pending) => pending.conversationKey === this._conversation)
      .map((pending) => {
        const time = new Date(pending.createdAt).toLocaleTimeString([], {hour:"numeric", minute:"2-digit"});
        const stateLabel = pending.state === "sending" ? "Sending" : pending.state === "queued" ? "Queued" : "Not sent";
        return `<article class="message outgoing pending" role="listitem"><div class="message-head"><span class="message-sender">You</span><time class="message-time">${escapeHtml(time)}</time></div><div class="message-text">${escapeHtml(pending.body)}</div><div class="message-meta"><span>${escapeHtml(pending.sourceName)}</span><span class="message-send-state ${escapeHtml(pending.state)}" title="${pending.state === "queued" ? "Queued once by Home Assistant; radio delivery is not confirmed" : escapeHtml(pending.error || stateLabel)}">${escapeHtml(stateLabel)}</span></div></article>`;
      }).join("");
    const rail = ["channel","direct"].map((type) => `<div class="rail-heading">${type === "channel" ? "Channels" : "Direct messages"}</div>${catalog.filter((item)=>item.type===type).map((item)=>`<button class="conversation-item ${this._conversation===item.key?"active":""}" data-conversation="${escapeHtml(item.key)}" aria-pressed="${this._conversation===item.key}"><span class="conversation-icon">${type==="channel"?"#":"↔"}</span><span class="conversation-label"><strong>${this._pinnedConversations.has(item.key)?"★ ":""}${escapeHtml(item.name)}</strong><small>${escapeHtml(item.detail)}${this._mutedConversations.has(item.key)?" · muted":""}</small></span>${unreadCounts.get(item.key)?`<span class="unread-count" aria-label="${unreadCounts.get(item.key)} unread">${unreadCounts.get(item.key)}</span>`:""}<span class="badge protocol-${escapeHtml(item.protocol)}">${escapeHtml(item.protocol)}</span></button>`).join("")}`).join("");
    const picker = `<div class="conversation-picker-wrap"><select id="conversation-picker" class="conversation-picker" aria-label="Choose channel or conversation"><option value="all" ${this._conversation==="all"?"selected":""}>All messages</option>${catalog.map((item)=>`<option value="${escapeHtml(item.key)}" ${this._conversation===item.key?"selected":""}>${item.type==="channel"?"# ":"↔ "}${escapeHtml(item.name)}${unreadCounts.get(item.key)?` (${unreadCounts.get(item.key)} unread)`:""}</option>`).join("")}</select></div>`;
    const pinned = selected ? this._pinnedConversations.has(selected.key) : false;
    const muted = selected ? this._mutedConversations.has(selected.key) : false;
    const filterActive = Boolean(
      this._messageQuery ||
      this._messageProtocol !== "all" ||
      this._messageSource !== "all" ||
      this._messageScope !== "all" ||
      this._messageUnread ||
      this._messageFavorite,
    );
    const emptyState = messageStatus === "error"
      ? this._panelState("Conversation", "Stored history is unavailable", "MeshMonitor rejected or could not complete the first bounded history read. Refresh after access or connectivity recovers.")
      : filterActive
        ? this._panelState("Conversation", "No matching messages", "Clear the search or filters to see the rest of this bounded history.")
      : this._panelState("Conversation", "No messages here yet", "The stored history returned no messages for this conversation.");
    const statusNote = messageStatus === "partial"
      ? `<div class="conversation-alert" role="status">Some source histories are unavailable; visible messages are a partial result.</div>`
      : messageStatus === "stale"
        ? `<div class="conversation-alert" role="status">Showing the last successful stored history while refresh is unavailable.</div>`
        : "";
    const sourceFilter = messageSources.length > 1
      ? `<select id="message-source" aria-label="Filter messages by source"><option value="all">All sources</option>${messageSources.map(([id,name])=>`<option value="${escapeHtml(id)}" ${this._messageSource===id?"selected":""}>${escapeHtml(name)}</option>`).join("")}</select>`
      : "";
    return `<section class="conversation-shell"><aside class="conversation-rail" aria-label="Conversations"><div class="conversation-search"><div class="search-field"><input id="message-search" aria-label="Search visible messages" value="${escapeHtml(this._messageQuery)}" placeholder="Search messages"><button type="button" id="clear-message-search" class="search-clear" aria-label="Clear message search" title="Clear search" ${this._messageQuery ? "" : "hidden"}>×</button></div></div>${picker}<button class="conversation-item ${this._conversation==="all"?"active":""}" data-conversation="all" aria-pressed="${this._conversation==="all"}"><span class="conversation-icon">◎</span><span class="conversation-label"><strong>All messages</strong><small>${messages.length} recent</small></span></button>${rail}</aside><div class="conversation-pane"><div class="conversation-chrome">${statusNote}<div class="conversation-head"><div class="conversation-icon">${selected?.type==="channel"?"#":selected?"↔":"◎"}</div><div class="title"><h3>${escapeHtml(selected?.name || "All messages")}</h3><div class="muted">${escapeHtml(selected?.detail || "Meshtastic, MeshCore, and Reticulum")} · ${filtered.length} shown</div></div><div class="conversation-actions"><select id="message-protocol" aria-label="Filter messages by protocol"><option value="all">All protocols</option><option value="meshtastic" ${this._messageProtocol==="meshtastic"?"selected":""}>Meshtastic</option><option value="meshcore" ${this._messageProtocol==="meshcore"?"selected":""}>MeshCore</option><option value="reticulum" ${this._messageProtocol==="reticulum"?"selected":""}>Reticulum</option></select>${sourceFilter}${selected?`<button id="conversation-pin" aria-label="${pinned?"Unpin":"Pin"} ${escapeHtml(selected.name)}" aria-pressed="${pinned}" title="${pinned?"Unpin":"Pin"} conversation">${pinned?"★":"☆"}</button><button id="conversation-mute" aria-pressed="${muted}" title="${muted?"Unmute":"Mute"} conversation">${muted?"Unmute":"Mute"}</button>`:""}<button id="mark-read">Mark read</button></div></div></div><div class="messages" data-conversation="${escapeHtml(this._conversation)}" role="log" aria-label="${escapeHtml(selected?.name || "All messages")} conversation timeline" aria-busy="${this._loading}" tabindex="0">${timeline || (!pendingTimeline ? emptyState : "")}${pendingTimeline}</div>${this._compose(sourceEntries, selected)}</div></section>`;
  }

  _channels(sources) {
    const rows = sources.flatMap((source) => (source.channels || []).map((channel) => ({...channel, source_name:source.name, protocol:source.protocol})));
    return rows.length ? `<div class="table"><table><thead><tr><th>Source</th><th>Protocol</th><th>Channel</th><th>Role/scope</th><th>Uplink</th><th>Downlink</th><th>Position precision</th><th>Encryption</th></tr></thead><tbody>${rows.map((channel)=>`<tr><td>${escapeHtml(channel.source_name)}</td><td><span class="badge protocol-${escapeHtml(channel.protocol)}">${escapeHtml(channel.protocol)}</span></td><td>${escapeHtml(channel.name)}</td><td>${escapeHtml(channel.role || channel.scope || "—")}</td><td>${channel.uplink_enabled == null ? "—" : channel.uplink_enabled ? "Yes" : "No"}</td><td>${channel.downlink_enabled == null ? "—" : channel.downlink_enabled ? "Yes" : "No"}</td><td>${channel.position_precision ?? "—"}</td><td>${channel.has_key == null ? "Unknown" : channel.has_key ? "Key configured" : "No key"}</td></tr>`).join("")}</tbody></table></div><p class="muted">Read-only channel inventory. Keys and raw channel payloads never leave Home Assistant.</p>` : `<div class="card"><h3>No visible channels</h3><p class="muted">This account may not have channel read access.</p></div>`;
  }

  async _setFavorite(entryId, sourceId, nodeId, favorite) {
    const favoriteKey = `${entryId}\u0000${sourceId}\u0000${nodeId}`;
    if (this._favoritePending.has(favoriteKey)) return;
    const node = this._allNodes().find(
      (item) => item.entry_id === entryId && item.source_id === sourceId && item.id === nodeId,
    );
    if (!node) return;
    const previous = Boolean(node.favorite);
    node.favorite = favorite;
    this._favoritePending.add(favoriteKey);
    this._favoriteOverrides.set(favoriteKey, favorite);
    this._error = "";
    this._render();
    try {
      await this._hass.callWS({type:"meshmonitor/set_favorite", entry_id:entryId, source_id:sourceId, node_id:nodeId, favorite});
      this._favoritePending.delete(favoriteKey);
      this._render();
    } catch (error) {
      node.favorite = previous;
      this._favoritePending.delete(favoriteKey);
      this._favoriteOverrides.delete(favoriteKey);
      this._error = `Favorite change blocked: ${error?.message || String(error)}`;
      this._render();
    }
  }

  async _requestNodeAction(action) {
    if (this._nodeActionPending || !this._nodeDetail) return;
    const detail = { ...this._nodeDetail };
    const labels = {
      traceroute: "Traceroute request",
      position: "Position request",
      nodeinfo: "Node-information request",
      neighbors: "Neighbor-information request",
    };
    this._nodeActionPending = action;
    this._nodeActionStatus = `${labels[action] || "Node request"} is being submitted…`;
    this._render();
    try {
      const result = await this._hass.callWS({
        type: "meshmonitor/request_node_action",
        entry_id: detail.entry_id,
        source_id: detail.source_id,
        node_id: detail.node_id,
        action,
      });
      if (this._nodeDetail?.entry_id === detail.entry_id && this._nodeDetail?.node_id === detail.node_id)
        this._nodeActionStatus = result.accepted
          ? `${labels[action]} accepted. This does not confirm that the node replied.`
          : `${labels[action]} was not accepted.`;
    } catch (error) {
      if (this._nodeDetail?.entry_id === detail.entry_id && this._nodeDetail?.node_id === detail.node_id)
        this._nodeActionStatus = `${labels[action]} blocked: ${error?.message || String(error)}`;
    } finally {
      this._nodeActionPending = "";
      this._render();
    }
  }

  async _setNodeIgnored() {
    if (this._nodeActionPending || !this._nodeDetail) return;
    const detail = { ...this._nodeDetail };
    const node = this._allNodes().find(
      (item) => item.entry_id === detail.entry_id && item.source_id === detail.source_id && item.id === detail.node_id,
    );
    if (!node) return;
    const ignored = !node.ignored;
    this._nodeIgnoreReview = false;
    this._nodeActionPending = "ignore";
    this._nodeActionStatus = `${ignored ? "Ignoring" : "Unignoring"} node in MeshMonitor…`;
    this._render();
    try {
      await this._hass.callWS({
        type: "meshmonitor/set_node_ignored",
        entry_id: detail.entry_id,
        source_id: detail.source_id,
        node_id: detail.node_id,
        ignored,
      });
      node.ignored = ignored;
      this._nodeActionStatus = `${node.name} is ${ignored ? "ignored" : "no longer ignored"} in MeshMonitor.`;
      await this._load();
    } catch (error) {
      this._nodeActionStatus = `Ignore change blocked: ${error?.message || String(error)}`;
    } finally {
      this._nodeActionPending = "";
      this._render();
    }
  }

  _compose(sources, conversation) {
    const locked = (title, detail) =>
      `<div class="reply-placeholder" aria-disabled="true"><div><strong>${escapeHtml(title)}</strong><span>${escapeHtml(detail)}</span></div><div class="reply-state">Locked</div></div>`;
    if (!conversation)
      return locked(
        "Choose a conversation to write",
        "All messages is not a destination. Select one exact channel or direct conversation.",
      );
    if (this._data?.can_send_messages !== true)
      return locked(
        "Administrator access required",
        "Only a Home Assistant administrator can review or send a message.",
      );
    const choices = conversationSourceChoices(conversation, sources);
    const enabled = choices.filter((choice) => choice.enabled);
    if (!enabled.length) {
      const detail = choices.length
        ? choices.map((choice) => `${choice.source.name}: ${choice.reason}`).join(" · ")
        : "No exact, fresh source can resolve this protocol destination.";
      return locked("This conversation is not sendable", detail);
    }
    if (!enabled.some(({ source }) => sourceSelectionKey(source) === this._composeSource))
      this._composeSource = sourceSelectionKey(enabled[0].source);
    const source = enabled.find(
      ({ source: item }) => sourceSelectionKey(item) === this._composeSource,
    )?.source;
    const validation = messageDraftValidation(
      this._composeText,
      conversation.protocol,
      conversation.type,
    );
    const destination = conversation.type === "channel"
      ? `Channel ${conversation.channel} · ${conversation.name}`
      : `${conversation.name} · ${conversation.recipient}`;
    const reply = this._replyContext
      ? `<div class="reply-context"><strong>Replying to ${escapeHtml(this._replyContext.sender)}</strong><span>${escapeHtml(this._replyContext.body)}</span><button id="cancel-reply-context" aria-label="Cancel quoted reply context">×</button></div>`
      : "";
    return `<section class="compose" aria-label="Message composer"><div class="compose-top"><label>Send via <select id="compose-source" aria-label="Exact outbound source">${enabled.map(({source:item}) => `<option value="${escapeHtml(sourceSelectionKey(item))}" ${sourceSelectionKey(item) === this._composeSource ? "selected" : ""}>${escapeHtml(item.name)} · ${escapeHtml(item.source_id)}</option>`).join("")}</select></label><span class="compose-route" title="${escapeHtml(destination)}">${escapeHtml(conversation.protocol)} · ${escapeHtml(destination)}</span></div>${reply}<div class="compose-body"><textarea id="compose-text" aria-label="Message body" placeholder="Write a message. Enter adds a new line; it never sends.">${escapeHtml(this._composeText)}</textarea><div class="compose-action"><span id="compose-count" class="compose-count muted">${validation.bytes} / ${validation.limit} bytes</span><button id="compose-send" ${this._sending || !validation.valid ? "disabled" : ""}>${this._sending ? "Sending…" : "Send"}</button></div></div>${this._sendStatus ? `<div class="send-status ${this._sendStatusAmbiguous ? "ambiguous" : ""}" role="status" aria-live="polite">${escapeHtml(this._sendStatus)}</div>` : ""}<div class="muted" style="margin-top:5px;font-size:9px">A check means the outgoing message appeared in stored MeshMonitor history; it does not prove radio delivery. No automatic retries.</div></section>`;
  }

  async _sendMessage() {
    if (this._sending) return;
    const sources = this._data?.sources || [];
    const conversation = this._conversationCatalog(
      this._data?.messages || [],
      sources,
    ).find((item) => item.key === this._conversation);
    const source = conversationSourceChoices(conversation, sources)
      .filter((choice) => choice.enabled)
      .map((choice) => choice.source)
      .find((item) => sourceSelectionKey(item) === this._composeSource);
    const validation = messageDraftValidation(
      this._composeText,
      conversation?.protocol,
      conversation?.type,
    );
    if (!conversation || !source || !validation.valid) {
      this._sendStatus = "The exact route or message is no longer valid. Nothing was sent.";
      this._sendStatusAmbiguous = false;
      this._render();
      return;
    }
    const body = this._composeText;
    const pending = {
      id: messageSendNonce(),
      conversationKey: conversation.key,
      body,
      sourceName: source.name,
      createdAt: Date.now(),
      state: "sending",
      error: "",
    };
    this._pendingMessages.push(pending);
    this._sending = true;
    this._composeText = "";
    this._messageDrafts.delete(this._conversation);
    this._replyContext = null;
    this._sendStatus = "";
    this._sendStatusAmbiguous = false;
    this._render();
    try {
      const request = {
        type: "meshmonitor/send_message",
        entry_id: source.entry_id,
        source_id: source.source_id,
        protocol: conversation.protocol,
        text: body,
        nonce: pending.id,
        confirm: "SEND",
      };
      if (conversation.type === "direct") request.destination = conversation.recipient;
      else request.channel = conversation.channel;
      // HA accepts the reviewed command immediately and owns the single
      // background transaction, so browser command deadlines cannot cancel a
      // radio handoff already authorized by the user.
      const result = await this._hass.callWS(request);
      if (result.accepted) {
        pending.state = "queued";
        this._render();
        try {
          await this._load();
        } catch (_error) {
          // The normal polling cycle will reconcile stored history later.
        }
      } else {
        pending.state = "failed";
        pending.error = "MeshMonitor did not accept this message. No retry was made.";
        this._sendStatus = pending.error;
      }
    } catch (error) {
      const presentation = sendErrorPresentation(error);
      pending.state = "failed";
      pending.error = presentation.message;
      this._sendStatus = presentation.message;
      this._sendStatusAmbiguous = presentation.ambiguous;
    } finally {
      this._sending = false;
      this._render();
    }
  }

  _meshMonitorSourceLinks(source) {
    const links = source.meshmonitor_links || {};
    const anchor = (url, label) => url
      ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${label} ↗</a>`
      : "";
    return `<p class="muted">${[
      anchor(links.details, "Open details"),
      anchor(links.configuration, "Administration"),
    ].filter(Boolean).join(" · ")}</p>`;
  }
}

if (!customElements.get("meshmonitor-panel-20260829-0803")) {
  customElements.define("meshmonitor-panel-20260829-0803", MeshMonitorPanel);
}
import "./vendor/leaflet/leaflet.js";
