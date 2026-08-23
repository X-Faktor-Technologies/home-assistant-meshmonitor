const historyTime = (value) => {
  const numeric = Number(value);
  if (Number.isFinite(numeric)) return numeric > 1e11 ? numeric : numeric * 1000;
  const timestamp = new Date(value).valueOf();
  return Number.isFinite(timestamp) ? timestamp : null;
};

export function normalizeHistoryPoints(points, valueKey) {
  return (Array.isArray(points) ? points : [])
    .map((point) => ({
      ...point,
      timestamp_ms: historyTime(point?.timestamp),
      numeric_value:
        point?.[valueKey] === null || point?.[valueKey] === undefined
          ? Number.NaN
          : Number(point[valueKey]),
    }))
    .filter(
      (point) =>
        point.timestamp_ms !== null && Number.isFinite(point.numeric_value),
    )
    .sort(
      (left, right) =>
        left.timestamp_ms - right.timestamp_ms ||
        left.numeric_value - right.numeric_value,
    );
}

export function telemetrySeries(points) {
  const grouped = new Map();
  for (const point of normalizeHistoryPoints(points, "value")) {
    const type = String(point.type || "Telemetry");
    const unit = String(point.unit || "");
    const key = `${type}\u0000${unit}`;
    if (!grouped.has(key)) grouped.set(key, { key, type, unit, points: [] });
    grouped.get(key).points.push(point);
  }
  return [...grouped.values()].sort((left, right) =>
    left.key.localeCompare(right.key),
  );
}

export function sparklinePoints(points, width = 240, height = 64) {
  if (!points.length) return "";
  const times = points.map((point) => point.timestamp_ms);
  const values = points.map((point) => point.numeric_value);
  const minTime = Math.min(...times);
  const maxTime = Math.max(...times);
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const timeSpan = maxTime - minTime || 1;
  const valueSpan = maxValue - minValue || 1;
  return points
    .map((point) => {
      const x = ((point.timestamp_ms - minTime) / timeSpan) * width;
      const y =
        maxValue === minValue
          ? height / 2
          : height - ((point.numeric_value - minValue) / valueSpan) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

export function nodeHistoryStatePresentation(endpoint, label) {
  if (!endpoint)
    return {
      state: "idle",
      title: `${label} not loaded`,
      detail: "Choose a time range and load stored history.",
    };
  if (endpoint.state === "permission_denied")
    return {
      state: "permission_denied",
      title: `${label} permission required`,
      detail: "The MeshMonitor token needs info:read for this source.",
    };
  if (endpoint.state === "not_available")
    return {
      state: "not_available",
      title: `${label} is not available`,
      detail: "This source or MeshMonitor version does not expose this stored history.",
    };
  if (endpoint.state === "error")
    return {
      state: "error",
      title: `${label} could not be loaded`,
      detail: "The stored-data read failed. Try again after the connection recovers.",
    };
  if (endpoint.state === "supported" && !(endpoint.points || []).length)
    return {
      state: "empty",
      title: `No ${label.toLowerCase()} in this range`,
      detail: "MeshMonitor returned a successful empty result.",
    };
  return null;
}

const present = (value) => value !== null && value !== undefined && value !== "";

// MeshMonitor 4.14.x may expose Meshtastic's protobuf enum as a numeric string.
// Keep the known value readable while retaining an honest fallback for future enums.
const MESHTASTIC_HARDWARE_MODELS = new Map([
  [16, "LilyGO T3S3"],
  [110, "Heltec V4"],
]);

const MESHTASTIC_ROLES = new Map([
  [0, "Client"],
  [1, "Client mute"],
  [2, "Router"],
  [3, "Router client"],
  [4, "Repeater"],
  [5, "Tracker"],
  [6, "Sensor"],
  [7, "TAK"],
  [8, "Client hidden"],
  [9, "Lost and found"],
  [10, "TAK tracker"],
  [11, "Router late"],
  [12, "Client base"],
]);

const MESHCORE_ROLES = new Map([
  [1, "Companion"],
  [2, "Repeater"],
  [3, "Room server"],
  [4, "Sensor"],
]);

const namedRole = (text, roles) => {
  const normalized = text.toUpperCase().replace(/[ -]+/g, "_");
  for (const label of roles.values())
    if (label.toUpperCase().replaceAll(" ", "_") === normalized) return label;
  return null;
};

export function nodeRoleLabel(value, protocol) {
  if (!present(value)) return null;
  const text = String(value).trim();
  const roles = String(protocol || "").toLowerCase() === "meshcore"
    ? MESHCORE_ROLES
    : MESHTASTIC_ROLES;
  if (/^\d+$/.test(text))
    return roles.get(Number(text)) || `Unknown (${text})`;
  return namedRole(text, roles) || text;
}

export function batteryPresentation(level, voltage = null) {
  const numericLevel = present(level) ? Number(level) : Number.NaN;
  const percent = Number.isFinite(numericLevel)
    ? Math.max(0, Math.min(100, Math.round(numericLevel)))
    : null;
  const numericVoltage = present(voltage) ? Number(voltage) : Number.NaN;
  const voltageLabel = Number.isFinite(numericVoltage)
    ? `${numericVoltage.toFixed(2)} V`
    : null;
  if (percent === null && !voltageLabel) return null;
  if (percent === null)
    return {
      icon: "mdi:battery",
      tone: "neutral",
      label: voltageLabel,
      percentLabel: null,
      voltageLabel,
    };
  const icon = percent <= 5
    ? "mdi:battery-outline"
    : percent >= 95
      ? "mdi:battery"
      : `mdi:battery-${Math.max(10, Math.min(90, Math.round(percent / 10) * 10))}`;
  return {
    icon,
    tone: percent < 30 ? "low" : percent < 70 ? "medium" : "high",
    label: `${percent}%${voltageLabel ? ` · ${voltageLabel}` : ""}`,
    percentLabel: `${percent}%`,
    voltageLabel,
  };
}

export function hardwareModelLabel(value, protocol) {
  if (!present(value)) return null;
  const text = String(value).trim();
  if (String(protocol || "").toLowerCase() !== "meshtastic" || !/^\d+$/.test(text))
    return text;
  return MESHTASTIC_HARDWARE_MODELS.get(Number(text)) || `Unknown (${text})`;
}

export function nodeRoleModelLabel(role, model, protocol) {
  return present(role)
    ? nodeRoleLabel(role, protocol)
    : hardwareModelLabel(model, protocol);
}

export function isMonitoredSourceNode(node, source) {
  if (!node || !source?.local_node_id) return false;
  const identifiers = (value) => {
    const normalized = String(value).trim().toLowerCase().replace(/^!/, "");
    const variants = new Set([normalized]);
    if (/^\d+$/.test(normalized))
      variants.add(Number(normalized).toString(16));
    return variants;
  };
  const nodeIds = identifiers(node.id);
  return [...identifiers(source.local_node_id)].some((id) => nodeIds.has(id));
}

export function nodeDetailPresentation(node, source, canSendMessages = false) {
  const monitored = isMonitoredSourceNode(node, source);
  const positioned = present(node?.latitude) && present(node?.longitude);
  const signal = {
    rssi: present(node?.rssi) ? `${node.rssi} dBm` : null,
    snr: present(node?.snr) ? `${node.snr} dB` : null,
  };
  const power = batteryPresentation(node?.battery, node?.voltage)?.label || "";
  const identity = [
    ["Node ID", node?.id],
    ["Short name", node?.short_name],
    ["Source", source?.name || node?.source_id],
  ].filter(([, value]) => present(value));
  const radio = [
    ["Role", nodeRoleLabel(node?.role, node?.protocol || source?.protocol)],
    ["Hardware", hardwareModelLabel(node?.model, node?.protocol || source?.protocol)],
    ["Firmware", node?.firmware],
    ["Hops away", node?.hops],
  ].filter(([, value]) => present(value));
  const position = positioned
    ? [
        ["Latitude", Number(node.latitude).toFixed(5)],
        ["Longitude", Number(node.longitude).toFixed(5)],
        ...(present(node?.altitude)
          ? [["Altitude", `${Number(node.altitude).toLocaleString(undefined, { maximumFractionDigits: 1 })} m`]]
          : []),
      ]
    : [];
  return {
    monitored,
    positioned,
    signal,
    power,
    groups: [
      { title: "Identity", items: identity },
      { title: "Radio and network", items: radio },
      { title: "Position", items: position, empty: !positioned },
    ].filter((group) => group.items.length || group.empty),
    actions: {
      favorite: node?.favorites_enabled === true,
      message:
        canSendMessages === true &&
        source?.transmit_enabled === true &&
        source?.available === true &&
        source?.connected === true &&
        !monitored,
      map: positioned,
      requests:
        String(source?.protocol || "").toLowerCase() === "meshtastic" &&
        source?.transmit_enabled === true &&
        source?.available === true &&
        source?.connected === true &&
        !monitored,
      ignore:
        String(source?.protocol || "").toLowerCase() === "meshtastic" &&
        source?.node_management_enabled === true &&
        !monitored,
      device: Boolean(node?.device_id),
      remove:
        String(source?.protocol || "").toLowerCase() === "meshtastic" &&
        !monitored,
      removeEnabled: source?.node_removal_enabled === true,
    },
  };
}
