import test from "node:test";
import assert from "node:assert/strict";

import {
  MAP_STYLE_STORAGE,
  mapCountLabel,
  mapEmptyPresentation,
  mapLayerSummary,
  mapStylePresentation,
  persistMapStyle,
  readMapStyle,
} from "../../custom_components/meshmonitor/frontend/map-view.js";

const empty = (overrides = {}) => ({
  loading: false,
  hasSnapshot: true,
  sourceCount: 1,
  error: false,
  filtered: false,
  nodes: 0,
  links: 0,
  fixes: 0,
  ...overrides,
});

test("map counts use concise deterministic plurals", () => {
  assert.equal(mapCountLabel(1, 0, 1), "1 node · 0 links · 1 fix");
  assert.equal(mapCountLabel(6, 5, 0), "6 nodes · 5 links");
});

test("map lifecycle states distinguish loading, failure, filters, and no positions", () => {
  assert.equal(
    mapEmptyPresentation(empty({ loading: true, hasSnapshot: false })).state,
    "loading",
  );
  assert.equal(
    mapEmptyPresentation(empty({ error: true, hasSnapshot: false })).state,
    "failed",
  );
  assert.match(mapEmptyPresentation(empty({ filtered: true })).title, /filters/);
  assert.match(mapEmptyPresentation(empty()).title, /No positioned/);
  assert.equal(mapEmptyPresentation(empty({ nodes: 1 })), null);
});

test("map layer summaries retain empty, unavailable, and partial-failure states", () => {
  assert.deepEqual(
    mapLayerSummary("topology", [
      { topology: { state: "not_available", edges: [] } },
    ]),
    { tone: "quiet", text: "Topology: not available for selected sources" },
  );
  assert.deepEqual(
    mapLayerSummary("neighbors", [
      { neighbors: { state: "supported", links: [] } },
    ]),
    { tone: "quiet", text: "No stored neighbor links" },
  );
  assert.deepEqual(
    mapLayerSummary("topology", [
      { topology: { state: "supported", edges: [{}, {}] } },
      { topology: { state: "error", edges: [] } },
    ]),
    { tone: "bad", text: "2 stored topology edges · 1 source read failed" },
  );
});

test("map styles retain a neutral default and migrate legacy privacy mode", () => {
  const values = new Map();
  const storage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };

  assert.equal(readMapStyle(storage), "neutral-dark");
  values.set("meshmonitor.map.privacy", "true");
  assert.equal(readMapStyle(storage), "tiles-off");
  assert.equal(persistMapStyle(storage, "standard"), "standard");
  assert.equal(values.get(MAP_STYLE_STORAGE), "standard");
  assert.equal(values.has("meshmonitor.map.privacy"), false);
  assert.equal(readMapStyle(storage), "standard");
});

test("map style presentation enables tiles only for the two tile styles", () => {
  assert.deepEqual(mapStylePresentation("standard"), {
    value: "standard",
    tiles: true,
    className: "standard-tiles",
    detail: "Standard OpenStreetMap · © contributors",
  });
  assert.equal(mapStylePresentation("neutral-dark").tiles, true);
  assert.equal(mapStylePresentation("neutral-dark").className, "neutral-dark-tiles");
  assert.match(mapStylePresentation("neutral-dark").detail, /Near-black/);
  assert.equal(mapStylePresentation("tiles-off").tiles, false);
  assert.equal(mapStylePresentation("invalid").value, "neutral-dark");
});
