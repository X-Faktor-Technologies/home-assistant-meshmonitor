const compareValues = (left, right) => (left > right) - (left < right);

export const LAST_HEARD_FUTURE_TOLERANCE_MS = 60000;

export const nodeTimestamp = (value) => {
  if (value === null || value === undefined || value === "") return null;
  const numeric = Number(value);
  const timestamp = Number.isFinite(numeric)
    ? numeric > 1e11
      ? numeric
      : numeric * 1000
    : new Date(value).valueOf();
  return Number.isFinite(timestamp) ? timestamp : null;
};

export const relativeNodeTime = (value, now = Date.now(), label = "Last seen") => {
  const timestamp = nodeTimestamp(value);
  if (timestamp === null)
    return {
      label: "Unknown",
      title: `${label} timestamp is unavailable`,
      state: "unknown",
    };

  const exact = new Date(timestamp).toISOString();
  const elapsed = now - timestamp;
  if (elapsed < -LAST_HEARD_FUTURE_TOLERANCE_MS)
    return {
      label: "Unavailable",
      title: `${label} timestamp is unavailable because ${exact} is more than 1 minute ahead of this browser`,
      state: "unknown",
    };
  if (elapsed < 60000)
    return { label: "Now", title: `${label}: ${exact}`, state: "fresh" };
  if (elapsed < 3600000)
    return {
      label: `${Math.floor(elapsed / 60000)} min`,
      title: `${label}: ${exact}`,
      state: "fresh",
    };
  if (elapsed < 86400000) {
    const hours = Math.floor(elapsed / 3600000);
    return {
      label: `${hours} hour${hours === 1 ? "" : "s"}`,
      title: `${label}: ${exact}`,
      state: "recent",
    };
  }
  const days = Math.floor(elapsed / 86400000);
  return {
    label: `${days} day${days === 1 ? "" : "s"}`,
    title: `${label}: ${exact}`,
    state: "stale",
  };
};

export const nodeActivity = (node) => {
  const localUpdate = node?.is_local_source ? node.local_updated_at : null;
  return localUpdate !== null && localUpdate !== undefined && localUpdate !== ""
    ? { value: localUpdate, label: "Last update", local: true }
    : { value: node?.last_heard, label: "Last seen", local: false };
};

export const relativeNodeActivity = (node, now = Date.now()) => {
  const activity = nodeActivity(node);
  return {
    ...relativeNodeTime(activity.value, now, activity.label),
    activityLabel: activity.label,
    local: activity.local,
  };
};

const sortableLastHeard = (value, now) => {
  const timestamp = nodeTimestamp(value);
  return timestamp !== null &&
    timestamp <= now + LAST_HEARD_FUTURE_TOLERANCE_MS
    ? timestamp
    : null;
};

const sortValue = (node, key, now) => {
  switch (key) {
    case "last_heard":
      return sortableLastHeard(nodeActivity(node).value, now);
    case "battery":
      return node.battery ?? node.voltage ?? null;
    case "signal":
      return node.rssi ?? node.snr ?? null;
    case "hops":
      return node.hops ?? null;
    case "protocol":
      return node.protocol?.toLowerCase() || null;
    case "role":
      return node.role?.toLowerCase() || null;
    default:
      return node.name?.toLowerCase() || null;
  }
};

const tieBreaker = (node) =>
  `${node.name || ""}\u0000${node.source_id || ""}\u0000${node.id || ""}`.toLowerCase();

export const compareNodes = (
  left,
  right,
  key,
  direction,
  now = Date.now(),
) => {
  if (Boolean(left.favorite) !== Boolean(right.favorite))
    return left.favorite ? -1 : 1;

  const leftValue = sortValue(left, key, now);
  const rightValue = sortValue(right, key, now);
  if (leftValue === null && rightValue !== null) return 1;
  if (leftValue !== null && rightValue === null) return -1;
  if (leftValue !== null && rightValue !== null) {
    const primary = compareValues(leftValue, rightValue);
    if (primary) return primary * (direction === "desc" ? -1 : 1);
  }
  return compareValues(tieBreaker(left), tieBreaker(right));
};

export const sortNodes = (nodes, key, direction, now = Date.now()) =>
  [...nodes].sort((left, right) =>
    compareNodes(left, right, key, direction, now),
  );
