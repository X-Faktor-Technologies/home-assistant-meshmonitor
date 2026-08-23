import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  relativeNodeTime,
  sortNodes,
} from "../../custom_components/meshmonitor/frontend/node-table.js";

const NOW = Date.parse("2026-08-16T14:30:00.000Z");

test("relative time is concise and preserves exact timestamp detail", () => {
  assert.deepEqual(relativeNodeTime(NOW - 120000, NOW), {
    label: "2 min",
    title: "Last seen: 2026-08-16T14:28:00.000Z",
    state: "fresh",
  });
  assert.equal(relativeNodeTime(NOW - 3600000, NOW).label, "1 hour");
  assert.equal(relativeNodeTime(NOW - 3 * 3600000, NOW).label, "3 hours");
  assert.equal(relativeNodeTime(NOW - 86400000, NOW).label, "1 day");
  assert.deepEqual(relativeNodeTime(NOW - 4 * 86400000, NOW), {
    label: "4 days",
    title: "Last seen: 2026-08-12T14:30:00.000Z",
    state: "stale",
  });
});

test("relative time identifies unknown and future timestamps honestly", () => {
  assert.equal(relativeNodeTime(null, NOW).state, "unknown");
  assert.equal(relativeNodeTime("not-a-date", NOW).label, "Unknown");
  assert.equal(relativeNodeTime(NOW + 60000, NOW).label, "Now");
  assert.deepEqual(relativeNodeTime(NOW + 60001, NOW), {
    label: "Unavailable",
    title: "Last seen timestamp is unavailable because 2026-08-16T14:31:00.001Z is more than 1 minute ahead of this browser",
    state: "unknown",
  });
});

test("favorites stay first while active sort applies within both groups", () => {
  const nodes = [
    { id: "ordinary-new", name: "Ordinary new", last_heard: NOW - 1000 },
    { id: "favorite-old", name: "Favorite old", last_heard: NOW - 4000, favorite: true },
    { id: "ordinary-old", name: "Ordinary old", last_heard: NOW - 5000 },
    { id: "favorite-new", name: "Favorite new", last_heard: NOW - 2000, favorite: true },
  ];
  assert.deepEqual(
    sortNodes(nodes, "last_heard", "desc").map((node) => node.id),
    ["favorite-new", "favorite-old", "ordinary-new", "ordinary-old"],
  );
  assert.deepEqual(
    sortNodes(nodes, "last_heard", "asc").map((node) => node.id),
    ["favorite-old", "favorite-new", "ordinary-old", "ordinary-new"],
  );
});

test("favorite changes reposition immediately and ties are deterministic", () => {
  const nodes = [
    { id: "bravo", source_id: "source-b", name: "Same", last_heard: NOW },
    { id: "alpha", source_id: "source-a", name: "Same", last_heard: NOW },
  ];
  assert.deepEqual(
    sortNodes(nodes, "last_heard", "desc").map((node) => node.id),
    ["alpha", "bravo"],
  );
  nodes[0].favorite = true;
  assert.deepEqual(
    sortNodes(nodes, "last_heard", "desc").map((node) => node.id),
    ["bravo", "alpha"],
  );
});

test("missing values remain last in either direction", () => {
  const nodes = [
    { id: "unknown", name: "Unknown", last_heard: null },
    { id: "known", name: "Known", last_heard: NOW },
  ];
  for (const direction of ["asc", "desc"])
    assert.deepEqual(
      sortNodes(nodes, "last_heard", direction).map((node) => node.id),
      ["known", "unknown"],
    );
});

test("materially future last-heard values are unavailable for ordering", () => {
  const nodes = [
    { id: "future", name: "Future", last_heard: NOW + 60001 },
    { id: "skew", name: "Allowed skew", last_heard: NOW + 60000 },
    { id: "known", name: "Known", last_heard: NOW - 1000 },
    { id: "missing", name: "Missing", last_heard: null },
  ];
  for (const direction of ["asc", "desc"])
    assert.deepEqual(
      sortNodes(nodes, "last_heard", direction, NOW).map((node) => node.id),
      direction === "asc"
        ? ["known", "skew", "future", "missing"]
        : ["skew", "known", "future", "missing"],
    );
});

test("node rows replace the Details column and remain mouse and keyboard accessible", () => {
  const panel = readFileSync(
    new URL("../../custom_components/meshmonitor/frontend/meshmonitor-panel.js", import.meta.url),
    "utf8",
  );

  assert.match(panel, /<tr class="node-row"[^>]+data-node-detail=/);
  assert.match(panel, /tabindex="0" role="button"[^>]+aria-haspopup="dialog"/);
  assert.match(panel, /event\.target !== event\.currentTarget/);
  assert.match(panel, /event\.key !== "Enter" && event\.key !== " "/);
  assert.doesNotMatch(panel, /<th class="node-details-column">Details<\/th>/);
  assert.doesNotMatch(panel, /class="node-details-column"/);
});

test("favorite changes render optimistically and roll back failed writes", () => {
  const panel = readFileSync(
    new URL("../../custom_components/meshmonitor/frontend/meshmonitor-panel.js", import.meta.url),
    "utf8",
  );
  const method = panel.slice(
    panel.indexOf("async _setFavorite("),
    panel.indexOf("\n  _compose(", panel.indexOf("async _setFavorite(")),
  );

  assert.ok(method.indexOf("node.favorite = favorite") < method.indexOf("await this._hass.callWS"));
  assert.match(method, /this\._favoritePending\.add\(favoriteKey\);\s*this\._favoriteOverrides\.set\(favoriteKey, favorite\);\s*this\._error = "";\s*this\._render\(\);/);
  assert.match(method, /catch \(error\) \{\s*node\.favorite = previous;/);
  assert.match(method, /this\._favoriteOverrides\.delete\(favoriteKey\);/);
  assert.match(panel, /event\.stopPropagation\(\);\s*this\._setFavorite/);
  assert.match(panel, /this\._applyFavoriteOverrides\(data\);\s*this\._data = data;/);
});

test("node list omits voltage while the details Power card retains it", () => {
  const panel = readFileSync(
    new URL("../../custom_components/meshmonitor/frontend/meshmonitor-panel.js", import.meta.url),
    "utf8",
  );

  assert.match(panel, /class="node-power">\$\{nodeListBatteryMarkup\(node\.battery\)\}/);
  assert.doesNotMatch(panel, /class="node-power">\$\{batteryMarkup\(node\.battery, node\.voltage\)\}/);
  assert.match(panel, /class="node-detail-stat power-stat"/);
  assert.match(panel, /nodeDetailBatteryMarkup\(node\.battery, node\.voltage\)/);
  assert.match(panel, /\.power-primary \{ font-size:20px;/);
  assert.match(panel, /\.power-voltage \{[^}]+font-size:12px;/);
});
