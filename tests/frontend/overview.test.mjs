import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";

import {
  overviewAttentionItems,
  overviewHealthPresentation,
  overviewLifecyclePresentation,
  overviewSummary,
  relativeSnapshotTime,
  sourceHealthPresentation,
} from "../../custom_components/meshmonitor/frontend/overview.js";

const NOW = Date.parse("2026-08-16T15:30:00.000Z");

test("source detail divider shares the same center line as the stats divider", () => {
  const panel = readFileSync(
    new URL("../../custom_components/meshmonitor/frontend/meshmonitor-panel.js", import.meta.url),
    "utf8",
  );

  assert.match(
    panel,
    /\.source-detail-column \{[^}]*padding:13px 16px 4px 0;/,
  );
  assert.match(
    panel,
    /\.source-detail-column \+ \.source-detail-column \{[^}]*margin:13px 0;[^}]*padding:0 0 0 16px;[^}]*border-left:1px solid var\(--divider-color\);/,
  );
});

test("protocol identity colors are centralized and distinct from health colors", () => {
  const panel = readFileSync(
    new URL("../../custom_components/meshmonitor/frontend/meshmonitor-panel.js", import.meta.url),
    "utf8",
  );

  assert.match(panel, /--protocol-meshtastic:#2e9b63/);
  assert.match(panel, /--protocol-meshcore:#8b5cf6/);
  assert.match(panel, /style="color:var\(--protocol-meshcore\)"[^>]*><i class="legend-dot"><\/i>MeshCore/);
  assert.doesNotMatch(panel, /style="color:#ffad3d"[^>]*>.*MeshCore/);
  assert.match(panel, /--protocol-reticulum:#3b82f6/);
  assert.match(panel, /source-view\.js\?v=20260822-1242/);
  assert.match(panel, /\.overview-source\.reticulum \.overview-source-head/);
  assert.match(panel, /\.message-protocol\.reticulum::before/);
  assert.match(panel, /\.map-marker\.reticulum/);
  assert.match(panel, /\.ok \{ color:var\(--success-color/);
});

test("overview keeps automation data compact inside server cards", () => {
  const panel = readFileSync(
    new URL("../../custom_components/meshmonitor/frontend/meshmonitor-panel.js", import.meta.url),
    "utf8",
  );

  assert.match(panel, /class="server-automation"/);
  assert.match(panel, /group\.entry_ids \|\| \[\]\)\.includes\(server\.entry_id\)/);
  assert.doesNotMatch(panel, /\$\{this\._automationSection\(/);
});

test("node and message searches expose accessible clear controls", () => {
  const panel = readFileSync(
    new URL("../../custom_components/meshmonitor/frontend/meshmonitor-panel.js", import.meta.url),
    "utf8",
  );

  assert.match(panel, /id="clear-node-search"[^>]*aria-label="Clear node search"/);
  assert.match(panel, /id="clear-message-search"[^>]*aria-label="Clear message search"/);
  assert.match(panel, /sortHeader\("role", "Role", "node-role"\)/);
  assert.doesNotMatch(panel, /Role\/model/);
});

test("mixed connected and disconnected sources report one of two", () => {
  const sources = [
    {protocol: "meshtastic", available: true, connected: true, errors: [], fetched_at: NOW},
    {protocol: "meshcore", available: true, connected: false, errors: [], fetched_at: NOW},
  ];
  const nodes = [
    {last_heard: NOW - 120000, latitude: 35, longitude: -82},
    {last_heard: NOW - 3 * 3600000, latitude: null, longitude: null},
    {last_heard: null, latitude: 36, longitude: -83},
  ];

  const summary = overviewSummary(sources, nodes, NOW);
  assert.deepEqual(summary, {
    reporting: 1,
    attention: 1,
    recent: 1,
    positioned: 2,
    protocols: ["meshcore", "meshtastic"],
    sourceCount: 2,
    nodeCount: 3,
    stateCounts: {
      reporting: 1,
      partial: 0,
      disconnected: 1,
      unavailable: 0,
      stale: 0,
      unknown: 0,
    },
    state: "attention",
  });
  assert.deepEqual(overviewHealthPresentation(summary), {
    headline: "Your mesh needs attention",
    detail: "1 of 2 sources is not currently reporting: 1 disconnected.",
    badge: "1/2 reporting",
    ariaLabel: "1 of 2 sources currently reporting; 1 needs attention: 1 disconnected",
  });
});

test("all connected, current, complete sources report two of two", () => {
  const summary = overviewSummary([
    {available: true, connected: true, errors: [], fetched_at: NOW},
    {available: true, connected: true, errors: [], fetched_at: NOW - 60_000},
  ], [], NOW);

  assert.equal(summary.reporting, 2);
  assert.equal(summary.attention, 0);
  assert.equal(summary.state, "healthy");
  assert.equal(overviewHealthPresentation(summary).badge, "2/2 reporting");
  assert.equal(overviewHealthPresentation(summary).headline, "All sources are reporting");
});

test("stale, partial, unavailable, and unknown sources never count as reporting", () => {
  const sources = [
    {available: true, connected: true, errors: [], fetched_at: NOW - 301_000},
    {available: true, connected: true, errors: ["telemetry"], fetched_at: NOW},
    {available: false, connected: true, errors: [], fetched_at: NOW},
    {available: true, connected: null, errors: [], fetched_at: NOW},
    {available: true, connected: true, errors: [], fetched_at: null},
    {available: true, connected: true, errors: [], fetched_at: NOW + 120_000},
  ];
  const summary = overviewSummary(sources, [], NOW);

  assert.equal(summary.reporting, 0);
  assert.deepEqual(summary.stateCounts, {
    reporting: 0,
    partial: 1,
    disconnected: 0,
    unavailable: 1,
    stale: 1,
    unknown: 3,
  });
  assert.equal(
    overviewHealthPresentation(summary).detail,
    "6 of 6 sources are not currently reporting: 1 unavailable, 1 stale, 1 partial, 3 unknown.",
  );
});

test("attention items identify the exact source and useful review reason", () => {
  const items = overviewAttentionItems([
    {entry_id: "entry-a", source_id: "source-a", name: "Garage", available: true, connected: false, fetched_at: NOW},
    {entry_id: "entry-b", source_id: "source-b", name: "Roof", available: true, connected: true, errors: ["telemetry"], fetched_at: NOW},
    {entry_id: "entry-c", source_id: "source-c", name: "Healthy", available: true, connected: true, errors: [], fetched_at: NOW},
  ], NOW);

  assert.deepEqual(items, [
    {entryId: "entry-a", sourceId: "source-a", name: "Garage", state: "disconnected", stateLabel: "Disconnected", reason: "Disconnected"},
    {entryId: "entry-b", sourceId: "source-b", name: "Roof", state: "partial", stateLabel: "Partial data", reason: "Partial data: telemetry"},
  ]);
});

test("stale attention explains last-reported age instead of saying needs review", () => {
  assert.equal(
    overviewAttentionItems([
      {name: "Attic", available: true, connected: true, errors: [], fetched_at: NOW - 11 * 60000, stale_after_seconds: 300},
    ], NOW)[0].reason,
    "Last reported: 11 min ago",
  );
});

test("configured polling interval determines stale snapshot boundary", () => {
  const source = {
    available: true,
    connected: true,
    errors: [],
    fetched_at: NOW - 360_000,
    stale_after_seconds: 600,
  };

  assert.equal(sourceHealthPresentation(source, NOW).state, "reporting");
  assert.equal(
    sourceHealthPresentation({...source, fetched_at: NOW - 601_000}, NOW).state,
    "stale",
  );
});

test("future and invalid last-heard values are not reported as recent", () => {
  const nodes = [
    {last_heard: NOW + 60000},
    {last_heard: "not-a-time"},
    {last_heard: NOW - 3600000},
  ];

  assert.equal(overviewSummary([], nodes, NOW).recent, 1);
});

test("healthy and empty source states remain distinct", () => {
  assert.equal(overviewSummary([], [], NOW).state, "empty");
  assert.equal(
    overviewSummary(
      [{protocol: "meshtastic", available: true, connected: true, errors: [], fetched_at: NOW}],
      [],
      NOW,
    ).state,
    "healthy",
  );
});

test("loading, empty, and failed first reads do not invent health counts", () => {
  assert.equal(
    overviewLifecyclePresentation({loading: true, hasSnapshot: false}).state,
    "loading",
  );
  assert.equal(
    overviewLifecyclePresentation({hasSnapshot: true, sourceCount: 0}).state,
    "empty",
  );
  assert.equal(
    overviewLifecyclePresentation({error: true, sourceCount: 0}).state,
    "unavailable",
  );
  assert.equal(overviewLifecyclePresentation({sourceCount: 1}), null);
});

test("last-reported age keeps exact timestamp detail and identifies invalid clocks", () => {
  assert.deepEqual(relativeSnapshotTime(NOW - 2 * 60000, NOW), {
    label: "Last reported: 2 min ago",
    title: "Last reported: 2026-08-16T15:28:00.000Z",
  });
  assert.equal(relativeSnapshotTime(null, NOW).label, "Last reported: unknown");
  assert.equal(
    relativeSnapshotTime(NOW + 2 * 60000, NOW).label,
    "Last reported: timestamp is in the future",
  );
});
