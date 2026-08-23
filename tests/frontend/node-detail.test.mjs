import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  batteryPresentation,
  hardwareModelLabel,
  isMonitoredSourceNode,
  nodeDetailPresentation,
  nodeHistoryStatePresentation,
  nodeRoleLabel,
  nodeRoleModelLabel,
  normalizeHistoryPoints,
  sparklinePoints,
  telemetrySeries,
} from "../../custom_components/meshmonitor/frontend/node-detail.js";

test("protocol role enums are readable and future values stay honest", () => {
  assert.equal(nodeRoleLabel(0, "meshtastic"), "Client");
  assert.equal(nodeRoleLabel("ROUTER_LATE", "meshtastic"), "Router late");
  assert.equal(nodeRoleLabel(1, "meshcore"), "Companion");
  assert.equal(nodeRoleLabel("3", "meshcore"), "Room server");
  assert.equal(nodeRoleLabel(99, "meshcore"), "Unknown (99)");
  assert.equal(nodeRoleModelLabel(null, 110, "meshtastic"), "Heltec V4");
  assert.equal(nodeRoleModelLabel(2, 110, "meshtastic"), "Router");
});

test("battery presentation uses HA icons and honest percentage thresholds", () => {
  assert.deepEqual(batteryPresentation(82, 4.12), {
    icon: "mdi:battery-80",
    tone: "high",
    label: "82% · 4.12 V",
    percentLabel: "82%",
    voltageLabel: "4.12 V",
  });
  assert.equal(batteryPresentation(45).tone, "medium");
  assert.equal(batteryPresentation(12).tone, "low");
  assert.equal(batteryPresentation(3).icon, "mdi:battery-outline");
  assert.deepEqual(batteryPresentation(null, 3.98), {
    icon: "mdi:battery",
    tone: "neutral",
    label: "3.98 V",
    percentLabel: null,
    voltageLabel: "3.98 V",
  });
  assert.equal(batteryPresentation(null, null), null);
});

test("monitored diagnostics belong only to the exact local source node", () => {
  const source = { local_node_id: "!ABC123", name: "Roof radio" };
  assert.equal(isMonitoredSourceNode({ id: "abc123" }, source), true);
  assert.equal(
    isMonitoredSourceNode({ id: "!000004d2" }, { local_node_id: "1234" }),
    false,
  );
  assert.equal(
    isMonitoredSourceNode({ id: "!4d2" }, { local_node_id: "1234" }),
    true,
  );
  assert.equal(isMonitoredSourceNode({ id: "remote" }, source), false);
  assert.equal(isMonitoredSourceNode({ id: "abc123" }, {}), false);
});

test("node details maximize reported values without placeholder clutter", () => {
  const presentation = nodeDetailPresentation(
    {
      id: "!1234",
      short_name: "NODE",
      battery: 82,
      voltage: 4.12,
      rssi: -109,
      snr: 7.5,
      role: "CLIENT",
      model: "T-Beam",
      firmware: "2.7.0",
      hops: 2,
      latitude: 40.123456,
      longitude: -74.987654,
      altitude: 123.45,
      favorites_enabled: true,
      device_id: "device-1",
    },
    {
      name: "Attic source",
      local_node_id: "!local",
      transmit_enabled: true,
      available: true,
      connected: true,
    },
    true,
  );
  assert.equal(presentation.monitored, false);
  assert.equal(presentation.power, "82% · 4.12 V");
  assert.deepEqual(presentation.signal, { rssi: "-109 dBm", snr: "7.5 dB" });
  assert.deepEqual(presentation.actions, {
    favorite: true,
    message: true,
    map: true,
    requests: false,
    ignore: false,
    device: true,
    remove: false,
    removeEnabled: false,
  });
  assert.deepEqual(
    presentation.groups.map((group) => group.title),
    ["Identity", "Radio and network", "Position"],
  );
  assert.equal(
    presentation.groups.flatMap((group) => group.items).some(([, value]) => value === "Unknown"),
    false,
  );
  assert.deepEqual(
    presentation.groups.find((group) => group.title === "Position").items,
    [
      ["Latitude", "40.12346"],
      ["Longitude", "-74.98765"],
      ["Altitude", "123.5 m"],
    ],
  );
  assert.deepEqual(
    presentation.groups.find((group) => group.title === "Radio and network").items[0],
    ["Role", "Client"],
  );
});

test("Meshtastic numeric hardware models are readable and unknown values stay honest", () => {
  assert.equal(hardwareModelLabel("16", "meshtastic"), "LilyGO T3S3");
  assert.equal(hardwareModelLabel("110", "meshtastic"), "Heltec V4");
  assert.equal(hardwareModelLabel(999, "meshtastic"), "Unknown (999)");
  assert.equal(hardwareModelLabel("T-Beam", "meshtastic"), "T-Beam");
  assert.equal(hardwareModelLabel("Companion", "meshcore"), "Companion");
});

test("primary actions are capability driven and local nodes cannot message themselves", () => {
  const node = { id: "local", latitude: null, longitude: null };
  const source = {
    local_node_id: "local",
    transmit_enabled: true,
    available: true,
    connected: true,
  };
  const presentation = nodeDetailPresentation(node, source, true);
  assert.equal(presentation.monitored, true);
  assert.equal(presentation.actions.message, false);
  assert.equal(presentation.actions.map, false);
  assert.equal(presentation.actions.favorite, false);
  assert.equal(presentation.actions.device, false);
  assert.deepEqual(
    presentation.groups.map((group) => group.title),
    ["Identity", "Position"],
  );
  assert.deepEqual(presentation.groups.at(-1), {
    title: "Position",
    items: [],
    empty: true,
  });
});

test("local-only removal is Meshtastic-only, remote-only, and independently gated", () => {
  const remote = nodeDetailPresentation(
    { id: "!1234abcd" },
    { protocol: "meshtastic", local_node_id: "!ffffffff", node_removal_enabled: true },
  );
  assert.equal(remote.actions.remove, true);
  assert.equal(remote.actions.removeEnabled, true);
  const disabled = nodeDetailPresentation(
    { id: "!1234abcd" },
    { protocol: "meshtastic", local_node_id: "!ffffffff", node_removal_enabled: false },
  );
  assert.equal(disabled.actions.remove, true);
  assert.equal(disabled.actions.removeEnabled, false);
  assert.equal(
    nodeDetailPresentation({ id: "!1234abcd" }, { protocol: "meshcore" }).actions.remove,
    false,
  );
  assert.equal(
    nodeDetailPresentation(
      { id: "!1234abcd" },
      { protocol: "meshtastic", local_node_id: "!1234abcd", node_removal_enabled: true },
    ).actions.remove,
    false,
  );
});

test("manual request and ignore actions are capability driven", () => {
  const active = nodeDetailPresentation(
    { id: "!1234abcd" },
    {
      protocol: "meshtastic",
      local_node_id: "!ffffffff",
      transmit_enabled: true,
      available: true,
      connected: true,
      node_management_enabled: true,
    },
  );
  assert.equal(active.actions.requests, true);
  assert.equal(active.actions.ignore, true);
  const meshcore = nodeDetailPresentation(
    { id: "contact" },
    { protocol: "meshcore", transmit_enabled: true, available: true, connected: true },
  );
  assert.equal(meshcore.actions.requests, false);
  assert.equal(meshcore.actions.ignore, false);
});

test("drawer renders capability actions and gates diagnostics to monitored nodes", () => {
  const panel = readFileSync(
    new URL("../../custom_components/meshmonitor/frontend/meshmonitor-panel.js", import.meta.url),
    "utf8",
  );
  assert.match(panel, /presentation\.actions\.message[\s\S]+node-detail-message/);
  assert.match(panel, /node-detail-message">Send Message<\/button>/);
  assert.match(panel, /data-node-request="traceroute"[\s\S]+Trace Route/);
  assert.match(panel, /data-node-request="position"[\s\S]+Request Position/);
  assert.match(panel, /Request Node Information[\s\S]+Request Neighbor Information/);
  assert.match(panel, /id="node-detail-ignore"[\s\S]+Ignore Node/);
  assert.match(panel, /does not confirm that the node replied/);
  assert.match(panel, /<span>RSSI<\/span>[\s\S]+<span>SNR<\/span>/);
  assert.match(panel, /presentation\.actions\.map[\s\S]+node-detail-map/);
  assert.match(panel, /presentation\.actions\.device[\s\S]+Open HA device/);
  assert.match(panel, /presentation\.actions\.remove[\s\S]+Remove from MeshMonitor/);
  assert.match(panel, /It does not purge the node from the radio/);
  assert.match(panel, /\.node-detail-group\.position \{ grid-column:1\/-1; \}/);
  assert.match(panel, /\.node-detail-group\.position \.node-detail-meta \{ grid-template-columns:repeat\(3,minmax\(0,1fr\)\)/);
  assert.match(panel, /group\.empty[\s\S]+Position has not been reported for this node\./);
  assert.doesNotMatch(panel, /!presentation\.positioned[\s\S]+Position has not been reported/);
  assert.match(panel, /const history = presentation\.monitored/);
  assert.doesNotMatch(
    panel,
    /<section class="node-history" aria-label="Stored node history">/,
  );
});

test("node history states distinguish idle, empty, denied, unavailable, and error", () => {
  assert.equal(nodeHistoryStatePresentation(null, "Telemetry").state, "idle");
  assert.equal(
    nodeHistoryStatePresentation({ state: "supported", points: [] }, "Telemetry")
      .state,
    "empty",
  );
  assert.equal(
    nodeHistoryStatePresentation({ state: "permission_denied" }, "Telemetry")
      .state,
    "permission_denied",
  );
  assert.equal(
    nodeHistoryStatePresentation({ state: "not_available" }, "Telemetry").state,
    "not_available",
  );
  assert.equal(
    nodeHistoryStatePresentation({ state: "error" }, "Telemetry").state,
    "error",
  );
  assert.equal(
    nodeHistoryStatePresentation(
      { state: "supported", points: [{ value: 4.1 }] },
      "Telemetry",
    ),
    null,
  );
});

test("history shaping removes invalid values and sorts deterministically", () => {
  const points = normalizeHistoryPoints(
    [
      { timestamp: 3000, value: "4.2" },
      { timestamp: "invalid", value: 9 },
      { timestamp: 1000, value: 4.0 },
      { timestamp: 2000, value: null },
    ],
    "value",
  );
  assert.deepEqual(
    points.map((point) => point.numeric_value),
    [4, 4.2],
  );
  assert.match(sparklinePoints(points), /^0\.0,/);
  assert.match(sparklinePoints(points), /240\.0,/);
});

test("telemetry groups remain stable by API type and unit", () => {
  const series = telemetrySeries([
    { type: "voltage", unit: "V", timestamp: 2, value: 4.1 },
    { type: "battery", unit: "%", timestamp: 2, value: 80 },
    { type: "voltage", unit: "V", timestamp: 1, value: 4.0 },
  ]);
  assert.deepEqual(
    series.map((item) => [item.type, item.unit, item.points.length]),
    [
      ["battery", "%", 1],
      ["voltage", "V", 2],
    ],
  );
  assert.equal(sparklinePoints(series[0].points), "0.0,32.0");
});
