export const MAP_STYLE_STORAGE = "meshmonitor.map.style";
export const MAP_STYLES = Object.freeze([
  Object.freeze({ value: "standard", label: "Standard" }),
  Object.freeze({ value: "neutral-dark", label: "Neutral dark" }),
  Object.freeze({ value: "tiles-off", label: "Tiles off / privacy" }),
]);

const MAP_STYLE_VALUES = new Set(MAP_STYLES.map(({ value }) => value));

export const nodeIsVisibleOnMap = (node) => node?.hidden_from_map !== true;

export const normalizeMapStyle = (value, legacyPrivacy = null) => {
  if (MAP_STYLE_VALUES.has(value)) return value;
  return legacyPrivacy === "true" ? "tiles-off" : "neutral-dark";
};

export const readMapStyle = (storage) =>
  normalizeMapStyle(
    storage.getItem(MAP_STYLE_STORAGE),
    storage.getItem("meshmonitor.map.privacy"),
  );

export const persistMapStyle = (storage, value) => {
  const style = normalizeMapStyle(value);
  storage.setItem(MAP_STYLE_STORAGE, style);
  storage.removeItem("meshmonitor.map.privacy");
  return style;
};

export const mapStylePresentation = (style) => {
  const value = normalizeMapStyle(style);
  if (value === "standard")
    return {
      value,
      tiles: true,
      className: "standard-tiles",
      detail: "Standard OpenStreetMap · © contributors",
    };
  if (value === "tiles-off")
    return {
      value,
      tiles: false,
      className: "tiles-off",
      detail: "Privacy mode · no external tiles",
    };
  return {
    value,
    tiles: true,
    className: "neutral-dark-tiles",
    detail: "Near-black Neutral dark OpenStreetMap · © contributors",
  };
};

export const mapCountLabel = (nodes, links, fixes) => {
  const parts = [
    `${nodes} node${nodes === 1 ? "" : "s"}`,
    `${links} link${links === 1 ? "" : "s"}`,
  ];
  if (fixes) parts.push(`${fixes} fix${fixes === 1 ? "" : "es"}`);
  return parts.join(" · ");
};

export const mapEmptyPresentation = ({
  loading,
  hasSnapshot,
  sourceCount,
  error,
  filtered,
  nodes,
  links,
  fixes,
}) => {
  if (nodes || links || fixes) return null;
  if (loading && !hasSnapshot)
    return {
      state: "loading",
      title: "Loading map content…",
      detail: "Reading the latest sanitized coordinator snapshots from Home Assistant.",
    };
  if (error && !hasSnapshot)
    return {
      state: "failed",
      title: "Map data is unavailable",
      detail: "The panel could not load a coordinator snapshot. Use Refresh after the connection recovers.",
    };
  if (!hasSnapshot || !sourceCount)
    return {
      state: "empty",
      title: "Waiting for map data",
      detail: "No loaded MeshMonitor sources are visible yet.",
    };
  if (filtered)
    return {
      state: "empty",
      title: "Nothing matches these filters",
      detail: "Try another protocol, source, or last-heard range.",
    };
  return {
    state: "empty",
    title: "No positioned mesh content yet",
    detail: "Nodes need stored coordinates before they can appear here. Stored links also need two positioned endpoints.",
  };
};

export const mapLayerSummary = (kind, sources) => {
  const available = sources.filter(
    (source) => source[kind]?.state !== "not_available",
  );
  const name = kind === "topology" ? "Topology" : "Neighbor/SNR";
  if (!available.length)
    return { tone: "quiet", text: `${name}: not available for selected sources` };
  const failures = available.filter(
    (source) => source[kind]?.state === "error",
  ).length;
  const count = available.reduce(
    (total, source) =>
      total +
      (kind === "topology"
        ? source.topology?.edges?.length || 0
        : source.neighbors?.links?.length || 0),
    0,
  );
  const records = kind === "topology" ? "topology edges" : "neighbor links";
  return {
    tone: failures ? "bad" : count ? "ok" : "quiet",
    text: `${count ? `${count} stored ${records}` : `No stored ${records}`}${failures ? ` · ${failures} source read failed` : ""}`,
  };
};
