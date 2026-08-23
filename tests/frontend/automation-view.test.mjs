import assert from "node:assert/strict";
import test from "node:test";

import {
  automationOverviewSummary,
  automationRunPresentation,
  automationStatePresentation,
  sortedAutomationRuns,
} from "../../custom_components/meshmonitor/frontend/automation-view.js";

test("automation list lifecycle states remain explicit", () => {
  assert.equal(automationStatePresentation("pending").label, "Loading");
  assert.match(
    automationStatePresentation("permission_denied").detail,
    /automations:read/,
  );
  assert.equal(automationStatePresentation("unsupported").label, "Not available");
  assert.equal(automationStatePresentation("authentication_error").tone, "bad");
  assert.match(
    automationStatePresentation("error", true).detail,
    /last retained bounded data/,
  );
});

test("overview summary distinguishes disabled, empty, populated, and failed groups", () => {
  assert.deepEqual(automationOverviewSummary([]), {
    state: "disabled",
    tone: "quiet",
    label: "Off",
    automationCount: 0,
    enabledCount: 0,
    runCount: 0,
  });
  assert.equal(
    automationOverviewSummary([{ state: "empty", automations: [] }]).state,
    "empty",
  );
  const populated = automationOverviewSummary([
    {
      state: "ok",
      automations: [
        { enabled: true, history: { runs: [{ id: "run-1" }] } },
        { enabled: false, history: { runs: [] } },
      ],
    },
  ]);
  assert.deepEqual(
    [populated.state, populated.automationCount, populated.enabledCount, populated.runCount],
    ["ok", 2, 1, 1],
  );
  assert.equal(
    automationOverviewSummary([
      { state: "ok", automations: [] },
      { state: "permission_denied", automations: [] },
    ]).state,
    "permission_denied",
  );
});

test("recent runs sort newest first with unknown timestamps last and stable IDs", () => {
  const sorted = sortedAutomationRuns([
    { id: "run-z", updated_at: null },
    { id: "run-b", updated_at: "2026-08-17T04:00:00Z" },
    { id: "run-a", updated_at: "2026-08-17T04:00:00Z" },
    { id: "run-c", started_at: 1_787_000_000 },
  ]);
  assert.deepEqual(sorted.map((run) => run.id), ["run-c", "run-a", "run-b", "run-z"]);
});

test("run presentation treats only terminal outcomes as semantic success or failure", () => {
  assert.deepEqual(automationRunPresentation({ status: "completed", updated_at: 5 }), {
    status: "completed",
    label: "completed",
    tone: "ok",
    timestamp: 5,
  });
  assert.equal(automationRunPresentation({ status: "failed" }).tone, "bad");
  assert.equal(automationRunPresentation({ status: "waiting_for_node" }).tone, "quiet");
  assert.equal(automationRunPresentation({ status: "" }).label, "unknown");
});
