import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  PANEL_TABS,
  adjacentPanelTab,
  notificationDeepLink,
  normalizePanelTab,
} from "../../custom_components/meshmonitor/frontend/panel-navigation.js";

test("panel tabs preserve the approved daily views", () => {
  assert.deepEqual(
    PANEL_TABS.map(({ value, label }) => [value, label]),
    [
      ["overview", "Overview"],
      ["messages", "Messages"],
      ["nodes", "Nodes"],
      ["map", "Map"],
    ],
  );
  assert.equal(normalizePanelTab("sources"), "overview");
  assert.equal(normalizePanelTab("routes"), "nodes");
});

test("arrow, Home, and End keys move through tabs with wrapping", () => {
  assert.equal(adjacentPanelTab("overview", "ArrowLeft"), "map");
  assert.equal(adjacentPanelTab("map", "ArrowRight"), "overview");
  assert.equal(adjacentPanelTab("nodes", "Home"), "overview");
  assert.equal(adjacentPanelTab("nodes", "End"), "map");
  assert.equal(adjacentPanelTab("nodes", "Enter"), null);
});

test("notification deep links validate and retain bounded message identity", () => {
  assert.deepEqual(
    notificationDeepLink("?tab=messages&conversation=direct%3Ameshtastic%3A%211234abcd&message=msg-1"),
    {conversation: "direct:meshtastic:!1234abcd", messageId: "msg-1"},
  );
  assert.equal(notificationDeepLink("?tab=nodes&conversation=direct%3Amesh%3Anode"), null);
  assert.equal(notificationDeepLink("?tab=messages&conversation=invalid"), null);
  assert.equal(
    notificationDeepLink(`?tab=messages&conversation=channel%3Ameshcore%3A0&message=${"x".repeat(300)}`).messageId.length,
    240,
  );
});

test("tab DOM is accessible and Overview retains concise source health", () => {
  const panel = readFileSync(
    new URL(
      "../../custom_components/meshmonitor/frontend/meshmonitor-panel.js",
      import.meta.url,
    ),
    "utf8",
  );

  assert.match(panel, /role="tablist"/);
  assert.match(panel, /role="tab" aria-controls="panel-view" aria-selected=/);
  assert.match(panel, /role="tabpanel"[^>]+tabindex="0"/);
  assert.match(panel, /id="sidebar-toggle"[^>]+aria-label="Open Home Assistant sidebar"/);
  assert.match(panel, /new CustomEvent\("hass-toggle-menu"/);
  assert.match(panel, /\.sidebar-toggle\{display:flex\}/);
  assert.match(panel, /class="overview-source-head"/);
  assert.match(panel, /class="source-detail-column"/);
  assert.match(panel, /hardwareModelLabel\(device\.model \|\| device\.device_type, source\.protocol\)/);
  assert.match(panel, /nodeRoleModelLabel\(node\.role, node\.model, node\.protocol\)/);
  assert.match(panel, /class="battery-value \$\{battery\.tone\}"/);
  assert.match(panel, /\.node-detail-meta dd \{[^}]*font-size:15px;[^}]*line-height:1\.4;/);
  assert.match(panel, /margin:13px 0; padding:0 0 0 16px; border-left:1px solid var\(--divider-color\)/);
  assert.doesNotMatch(panel, /Open details ↗|Administration ↗|<p>Source ID:/);
  assert.doesNotMatch(panel, /data-tab="sources"|_sources\(/);
});

test("registered panel element and browser module stay version-aligned", () => {
  const panel = readFileSync(
    new URL("../../custom_components/meshmonitor/frontend/meshmonitor-panel.js", import.meta.url),
    "utf8",
  );
  const registration = readFileSync(
    new URL("../../custom_components/meshmonitor/panel.py", import.meta.url),
    "utf8",
  );
  const element = registration.match(/PANEL_ELEMENT = "([^"]+)"/)?.[1];

  assert.ok(element);
  assert.match(panel, new RegExp(`customElements\\.get\\("${element}"`));
  assert.match(panel, new RegExp(`customElements\\.define\\("${element}"`));
});

test("Overview warnings identify and navigate to exact source cards", () => {
  const panel = readFileSync(
    new URL(
      "../../custom_components/meshmonitor/frontend/meshmonitor-panel.js",
      import.meta.url,
    ),
    "utf8",
  );

  assert.match(panel, /data-overview-entry=/);
  assert.match(panel, /data-overview-source=/);
  assert.match(panel, /data-overview-card-entry=/);
  assert.match(panel, /data-overview-card-source=/);
  assert.match(panel, /scrollIntoView\(\{behavior: "smooth", block: "center"\}\)/);
  assert.match(panel, /<h2>Overview<\/h2>/);
  assert.doesNotMatch(panel, /Daily mesh console/);
  assert.match(panel, /class="overview-state \$\{summary\.state\}"/);
  assert.match(panel, /\$\{escapeHtml\(health\.badge\)\}/);
  assert.doesNotMatch(panel, /\$\{escapeHtml\(health\.detail\)\}/);
});

test("Overview source cards share available rows without detached protocol pills", () => {
  const panel = readFileSync(
    new URL(
      "../../custom_components/meshmonitor/frontend/meshmonitor-panel.js",
      import.meta.url,
    ),
    "utf8",
  );

  assert.match(
    panel,
    /\.overview-sources \{ display:grid; grid-template-columns:repeat\(auto-fit,minmax\(min\(100%,420px\),1fr\)\)/,
  );
  assert.match(panel, /\.overview-source:only-child \{ max-width:720px; \}/);
  assert.doesNotMatch(panel, /<div class="overview-protocols">/);
});

test("Overview server section uses scalable and plain-language labels", () => {
  const panel = readFileSync(
    new URL(
      "../../custom_components/meshmonitor/frontend/meshmonitor-panel.js",
      import.meta.url,
    ),
    "utf8",
  );

  assert.match(panel, /<h2>MeshMonitor server\(s\)<\/h2>/);
  assert.match(panel, /<span class="section-eyebrow">Server name<\/span>/);
  assert.doesNotMatch(panel, /<h2>MeshMonitor servers<\/h2>/);
  assert.doesNotMatch(panel, /<span class="section-eyebrow">MeshMonitor server<\/span>/);
});
