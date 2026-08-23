import assert from "node:assert/strict";
import test from "node:test";

import {
  reticulumCardPresentation,
  sourceCardPresentation,
} from "../../custom_components/meshmonitor/frontend/source-view.js";

const NOW = Date.parse("2026-08-16T16:30:00.000Z");

test("source presentation keeps availability, connection, and optional errors distinct", () => {
  assert.equal(
    sourceCardPresentation({available: false, connected: true, fetched_at: NOW}, NOW).state,
    "unavailable",
  );
  assert.equal(
    sourceCardPresentation({available: true, connected: false, fetched_at: NOW}, NOW).state,
    "disconnected",
  );
  assert.equal(
    sourceCardPresentation({available: true, connected: true, errors: ["topology"], fetched_at: NOW}, NOW).state,
    "partial",
  );
  assert.equal(
    sourceCardPresentation({available: true, connected: true, errors: [], fetched_at: NOW}, NOW).state,
    "reporting",
  );
});

test("source presentation preserves honest unknown values and exact snapshot detail", () => {
  const presentation = sourceCardPresentation(
    {available: true, connected: null, fetched_at: NOW - 2 * 60_000},
    NOW,
  );

  assert.equal(presentation.connection, "Unknown");
  assert.equal(presentation.state, "unknown");
  assert.equal(presentation.updated.label, "Last reported: 2 min ago");
  assert.equal(
    presentation.updated.title,
    "Last reported: 2026-08-16T16:28:00.000Z",
  );
});

test("missing error collections never become invented failures", () => {
  const presentation = sourceCardPresentation(
    {available: true, connected: true, fetched_at: NOW},
    NOW,
  );

  assert.deepEqual(presentation.errors, []);
  assert.equal(presentation.tone, "ok");
});

test("stale snapshots remain distinct from disconnected and partial sources", () => {
  const presentation = sourceCardPresentation(
    {available: true, connected: true, errors: [], fetched_at: NOW - 301_000},
    NOW,
  );

  assert.equal(presentation.state, "stale");
  assert.equal(presentation.stateLabel, "Stale snapshot");
  assert.equal(presentation.tone, "bad");
});

test("Reticulum cards use protocol-native inventory and identity fields", () => {
  assert.deepEqual(reticulumCardPresentation({
    protocol: "reticulum",
    available: true,
    connected: true,
    fetched_at: NOW,
    reticulum: {
      destination_count: 3,
      interface_count: 4,
      rns_version: "1.4.2",
      bridge_version: "0.1.0",
      mode: "attach",
      identity_name: "MeshMonitor Synthetic RNS",
      identity_hash: "20914cb776e9d9e60418354ea6986238",
    },
  }), {
    stats: [
      {label: "destinations", value: 3},
      {label: "interfaces", value: 4},
    ],
    primary: [
      ["Connection", "Connected"],
      ["RNS", "1.4.2"],
      ["Bridge", "0.1.0"],
    ],
    secondary: [
      ["Mode", "Attach"],
      ["LXMF identity", "MeshMonitor Synthetic RNS"],
      ["Destination", "20914cb776e9d9e60418354ea6986238"],
    ],
  });
  assert.equal(reticulumCardPresentation({protocol: "meshtastic"}), null);
});
