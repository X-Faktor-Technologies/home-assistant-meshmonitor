import test from "node:test";
import assert from "node:assert/strict";

import {serverCardPresentation} from "../../custom_components/meshmonitor/frontend/server-view.js";

const NOW = new Date("2026-08-20T22:00:00Z").valueOf();

test("server cards expose installed and latest versions per exact server", () => {
  const result = serverCardPresentation({
    health: {state: "ok", value: {status: "ok", version: "4.14.1"}},
    version: {
      state: "ok",
      last_attempt_at: "2026-08-20T21:59:00Z",
      value: {
        update_available: true,
        current_version: "4.14.1",
        latest_version: "4.14.2",
        release_url: "https://github.com/Yeraze/meshmonitor/releases/tag/v4.14.2",
      },
    },
  }, NOW);

  assert.equal(result.installed, "4.14.1");
  assert.equal(result.latest, "4.14.2");
  assert.equal(result.updateLabel, "Update available");
  assert.equal(result.healthLabel, "Healthy");
  assert.equal(result.checked, "Checked 1 min ago");
});

test("failed checks never claim that a server is current", () => {
  const result = serverCardPresentation({
    health: {state: "error", stale: true, value: {status: "ok", version: "4.14.1"}},
    version: {
      state: "error",
      stale: true,
      last_attempt_at: "2026-08-20T20:00:00Z",
      value: {update_available: false, latest_version: "4.14.1"},
    },
  }, NOW);

  assert.equal(result.healthLabel, "Health stale");
  assert.equal(result.updateLabel, "Update check stale");
  assert.notEqual(result.updateLabel, "Up to date");
});

test("pending and unsupported results remain explicit", () => {
  const pending = serverCardPresentation({health: {}, version: {}}, NOW);
  const unsupported = serverCardPresentation({
    health: {state: "ok", value: {status: "ok", version: "4.14.1"}},
    version: {state: "not_checked"},
  }, NOW);

  assert.equal(pending.healthLabel, "Checking");
  assert.equal(pending.latest, "Unknown");
  assert.equal(unsupported.updateLabel, "Update check unavailable");
});
