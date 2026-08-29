import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  MAP_STYLE_STORAGE,
  MAP_SHOW_HOME_STORAGE,
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

test("MeshMonitor-hidden nodes are excluded only from map presentation", () => {
  assert.equal(nodeIsVisibleOnMap({ hidden_from_map: true }), false);
  assert.equal(nodeIsVisibleOnMap({ hidden_from_map: false }), true);
  assert.equal(nodeIsVisibleOnMap({}), true);
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

test("home visibility is off by default and persists in browser storage", () => {
  const values = new Map();
  const storage = {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };

  assert.equal(readShowHome(storage), false);
  assert.equal(persistShowHome(storage, true), true);
  assert.equal(values.get(MAP_SHOW_HOME_STORAGE), "true");
  assert.equal(readShowHome(storage), true);
  assert.equal(persistShowHome(storage, false), false);
  assert.equal(readShowHome(storage), false);
});

test("home location prefers zone.home and falls back to HA configuration", () => {
  assert.deepEqual(
    homeLocation({
      config: { latitude: 10, longitude: 20 },
      states: {
        "zone.home": {
          attributes: {
            latitude: 30,
            longitude: 40,
            friendly_name: "Our Home",
          },
        },
      },
    }),
    { latitude: 30, longitude: 40, name: "Our Home" },
  );
  assert.deepEqual(
    homeLocation({ config: { latitude: 10, longitude: 20 }, states: {} }),
    { latitude: 10, longitude: 20, name: "Home" },
  );
  assert.equal(
    homeLocation({ config: { latitude: 91, longitude: 20 }, states: {} }),
    null,
  );
});

test("map polish includes Reticulum positions, clear filters, and accessible icon controls", () => {
  const panel = readFileSync(
    new URL("../../custom_components/meshmonitor/frontend/meshmonitor-panel.js", import.meta.url),
    "utf8",
  );

  assert.match(panel, /_allMapNodes\(\)/);
  assert.match(panel, /source\.reticulum\?\.peers/);
  assert.match(panel, /value="reticulum"[\s\S]+Reticulum/);
  assert.match(panel, /id="map-reset-filters"/);
  assert.match(panel, /mdi:filter-remove-outline/);
  assert.match(panel, /mdi:crosshairs-gps/);
  assert.match(panel, /--protocol-reticulum/);
  assert.match(panel, /\.filter\(nodeIsVisibleOnMap\)/);
  assert.match(panel, /path\.some\(isHidden\)/);
  assert.match(panel, /isHidden\(link\.from_id/);
  assert.match(panel, /id="map-show-home"/);
  assert.match(panel, /id="map-home"/);
  assert.match(panel, /_renderHomeMarker\(\)/);
  assert.match(panel, /_focusHome\(\)/);
});

test("map node popup opens the matching panel node details instead of MeshMonitor", () => {
  const panel = readFileSync(
    new URL("../../custom_components/meshmonitor/frontend/meshmonitor-panel.js", import.meta.url),
    "utf8",
  );

  assert.match(panel, />View node details<\/button>/);
  assert.match(panel, /data-map-node-detail/);
  assert.match(panel, /_nodeDetailFromMap\(/);
  assert.doesNotMatch(panel, /Open source nodes in MeshMonitor/);
});
