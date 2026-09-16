export const MAP_STYLE_STORAGE = "meshmonitor.map.style";
export const MAP_SHOW_HOME_STORAGE = "meshmonitor.map.showHome";
export const MAP_STYLES = Object.freeze([
  Object.freeze({ value: "esri-dark", label: "Dark gray" }),
  Object.freeze({ value: "esri-light", label: "Light gray" }),
  Object.freeze({ value: "esri-streets", label: "Streets" }),
  Object.freeze({ value: "esri-topographic", label: "Topographic" }),
  Object.freeze({ value: "esri-satellite", label: "Satellite" }),
  Object.freeze({ value: "tiles-off", label: "Tiles off / privacy" }),
]);

const MAP_STYLE_VALUES = new Set(MAP_STYLES.map(({ value }) => value));
const ESRI_ROOT = "https://server.arcgisonline.com/ArcGIS/rest/services";
const ESRI_ATTRIBUTION =
  'Tiles &copy; <a href="https://www.esri.com/">Esri</a> and its data providers';

const tileLayer = (url, attribution = "") =>
  Object.freeze({
    url,
    options: Object.freeze({
      maxZoom: 19,
      ...(attribution ? { attribution } : {}),
    }),
  });

const baseAndReference = (base, reference) =>
  Object.freeze([
    tileLayer(
      `${ESRI_ROOT}/${base}/MapServer/tile/{z}/{y}/{x}`,
      ESRI_ATTRIBUTION,
    ),
    tileLayer(`${ESRI_ROOT}/${reference}/MapServer/tile/{z}/{y}/{x}`),
  ]);

const MAP_PRESENTATIONS = Object.freeze({
  "esri-dark": Object.freeze({
    value: "esri-dark",
    tiles: true,
    className: "esri-dark-tiles",
    detail: "Dark gray · Esri and its data providers",
    layers: baseAndReference(
      "Canvas/World_Dark_Gray_Base",
      "Canvas/World_Dark_Gray_Reference",
    ),
  }),
  "esri-light": Object.freeze({
    value: "esri-light",
    tiles: true,
    className: "esri-light-tiles",
    detail: "Light gray · Esri and its data providers",
    layers: baseAndReference(
      "Canvas/World_Light_Gray_Base",
      "Canvas/World_Light_Gray_Reference",
    ),
  }),
  "esri-streets": Object.freeze({
    value: "esri-streets",
    tiles: true,
    className: "esri-streets-tiles",
    detail: "Streets · Esri and its data providers",
    layers: Object.freeze([
      tileLayer(
        `${ESRI_ROOT}/World_Street_Map/MapServer/tile/{z}/{y}/{x}`,
        ESRI_ATTRIBUTION,
      ),
    ]),
  }),
  "esri-topographic": Object.freeze({
    value: "esri-topographic",
    tiles: true,
    className: "esri-topographic-tiles",
    detail: "Topographic · Esri and its data providers",
    layers: Object.freeze([
      tileLayer(
        `${ESRI_ROOT}/World_Topo_Map/MapServer/tile/{z}/{y}/{x}`,
        ESRI_ATTRIBUTION,
      ),
    ]),
  }),
  "esri-satellite": Object.freeze({
    value: "esri-satellite",
    tiles: true,
    className: "esri-satellite-tiles",
    detail: "Satellite · Esri and its data providers",
    layers: baseAndReference(
      "World_Imagery",
      "Reference/World_Boundaries_and_Places",
    ),
  }),
  "tiles-off": Object.freeze({
    value: "tiles-off",
    tiles: false,
    className: "tiles-off",
    detail: "Privacy mode · no external tiles",
    layers: Object.freeze([]),
  }),
});

export const nodeIsVisibleOnMap = (node) => node?.hidden_from_map !== true;

export const readShowHome = (storage) =>
  storage.getItem(MAP_SHOW_HOME_STORAGE) === "true";

export const persistShowHome = (storage, value) => {
  const visible = value === true;
  storage.setItem(MAP_SHOW_HOME_STORAGE, String(visible));
  return visible;
};

export const homeLocation = (hass) => {
  const zone = hass?.states?.["zone.home"];
  const latitude = Number(
    zone?.attributes?.latitude ?? hass?.config?.latitude,
  );
  const longitude = Number(
    zone?.attributes?.longitude ?? hass?.config?.longitude,
  );
  if (
    !Number.isFinite(latitude) ||
    !Number.isFinite(longitude) ||
    latitude < -90 ||
    latitude > 90 ||
    longitude < -180 ||
    longitude > 180
  )
    return null;
  return {
    latitude,
    longitude,
    name: zone?.attributes?.friendly_name || "Home",
  };
};

export const normalizeMapStyle = (value, legacyPrivacy = null) => {
  if (MAP_STYLE_VALUES.has(value)) return value;
  if (value === "neutral-dark") return "esri-dark";
  if (value === "standard") return "esri-streets";
  return legacyPrivacy === "true" ? "tiles-off" : "esri-dark";
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
  return MAP_PRESENTATIONS[value];
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
