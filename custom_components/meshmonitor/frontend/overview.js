const timestamp = (value) => {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  const parsed = Number.isFinite(number)
    ? number > 1e11
      ? number
      : number * 1000
    : new Date(value).valueOf();
  return Number.isFinite(parsed) ? parsed : null;
};

const DEFAULT_STALE_AFTER_SECONDS = 300;

export const sourceHealthPresentation = (source = {}, now = Date.now()) => {
  const errors = Array.isArray(source.errors) ? source.errors : [];
  const fetchedAt = timestamp(source.fetched_at);
  const staleAfterSeconds = Number(source.stale_after_seconds);
  const staleAfter =
    (Number.isFinite(staleAfterSeconds) && staleAfterSeconds > 0
      ? staleAfterSeconds
      : DEFAULT_STALE_AFTER_SECONDS) * 1000;
  const age = fetchedAt === null ? null : now - fetchedAt;

  // Reporting is deliberately the one fully healthy state. Cached content and
  // node counts never override an unavailable, disconnected, incomplete, or
  // temporally unverifiable source snapshot.
  const state = source.available === false
    ? "unavailable"
    : source.available !== true
      ? "unknown"
      : source.connected === false
        ? "disconnected"
        : source.connected !== true || age === null || age < -60000
          ? "unknown"
          : age > staleAfter
            ? "stale"
            : errors.length
              ? "partial"
              : "reporting";
  const labels = {
    unavailable: "Unavailable",
    disconnected: "Disconnected",
    stale: "Stale snapshot",
    partial: "Partial data",
    unknown: "Health unknown",
    reporting: "Reporting",
  };

  return {
    state,
    stateLabel: labels[state],
    tone: state === "reporting" ? "ok" : "bad",
    connection:
      source.connected === true
        ? "Connected"
        : source.connected === false
          ? "Disconnected"
          : "Unknown",
    errors,
    updated: relativeSnapshotTime(source.fetched_at, now),
  };
};

export const overviewSummary = (sources = [], nodes = [], now = Date.now()) => {
  const health = sources.map((source) => sourceHealthPresentation(source, now));
  const stateCounts = Object.fromEntries(
    ["reporting", "partial", "disconnected", "unavailable", "stale", "unknown"]
      .map((state) => [state, health.filter((item) => item.state === state).length]),
  );
  const reporting = stateCounts.reporting;
  const attention = sources.length - reporting;
  const recent = nodes.filter((node) => {
    const heardAt = timestamp(node.last_heard);
    const age = heardAt === null ? null : now - heardAt;
    return age !== null && age >= 0 && age <= 60 * 60 * 1000;
  }).length;
  const positioned = nodes.filter(
    (node) =>
      node.hidden_from_map !== true &&
      node.latitude != null &&
      node.longitude != null,
  ).length;
  const protocols = [...new Set(sources.map((source) => source.protocol).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b));

  return {
    reporting,
    attention,
    recent,
    positioned,
    protocols,
    sourceCount: sources.length,
    nodeCount: nodes.length,
    stateCounts,
    state: !sources.length ? "empty" : attention ? "attention" : "healthy",
  };
};

export const overviewHealthPresentation = (summary) => {
  const sourceWord = summary.sourceCount === 1 ? "source" : "sources";
  const issueWord = summary.attention === 1 ? "is" : "are";
  const labels = {
    unavailable: "unavailable",
    disconnected: "disconnected",
    stale: "stale",
    partial: "partial",
    unknown: "unknown",
  };
  const breakdown = Object.entries(labels)
    .filter(([state]) => summary.stateCounts?.[state])
    .map(([state, label]) => `${summary.stateCounts[state]} ${label}`)
    .join(", ");
  const badge = `${summary.reporting}/${summary.sourceCount} reporting`;

  if (summary.state === "healthy")
    return {
      headline: "All sources are reporting",
      detail: `${summary.nodeCount} known nodes across ${summary.sourceCount} ${sourceWord}.`,
      badge,
      ariaLabel: `${summary.reporting} of ${summary.sourceCount} ${sourceWord} currently reporting`,
    };
  return {
    headline: "Your mesh needs attention",
    detail: `${summary.attention} of ${summary.sourceCount} ${sourceWord} ${issueWord} not currently reporting${breakdown ? `: ${breakdown}` : ""}.`,
    badge,
    ariaLabel: `${summary.reporting} of ${summary.sourceCount} ${sourceWord} currently reporting; ${summary.attention} ${summary.attention === 1 ? "needs" : "need"} attention${breakdown ? `: ${breakdown}` : ""}`,
  };
};

export const overviewAttentionItems = (sources = [], now = Date.now()) =>
  sources.flatMap((source) => {
    const health = sourceHealthPresentation(source, now);
    if (health.state === "reporting") return [];
    const reasons = {
      unavailable: "Source unavailable",
      disconnected: "Disconnected",
      stale: health.updated.label,
      partial: health.errors.length
        ? `Partial data: ${health.errors.join(", ")}`
        : "Partial data",
      unknown: "Health could not be verified",
    };
    return [{
      entryId: source.entry_id || "",
      sourceId: source.source_id || "",
      name: source.name || "Unnamed source",
      state: health.state,
      stateLabel: health.stateLabel,
      reason: reasons[health.state],
    }];
  });

export const overviewLifecyclePresentation = ({
  loading = false,
  hasSnapshot = false,
  sourceCount = 0,
  error = false,
} = {}) => {
  if (loading && !hasSnapshot)
    return {
      state: "loading",
      title: "Loading mesh status…",
      detail: "Reading the latest sanitized coordinator snapshots from Home Assistant.",
    };
  if (sourceCount) return null;
  return error
    ? {
      state: "unavailable",
      title: "Source status is unavailable",
      detail: "The panel could not load a coordinator snapshot. Use Refresh after the connection recovers.",
    }
    : {
      state: "empty",
      title: "Waiting for source data",
      detail: "No loaded MeshMonitor sources are visible yet. Configure or reload a source to populate this daily console.",
    };
};

export const relativeSnapshotTime = (value, now = Date.now()) => {
  const updatedAt = timestamp(value);
  if (updatedAt === null)
    return {label: "Last reported: unknown", title: "Last reported timestamp is unavailable"};
  const exact = new Date(updatedAt).toISOString();
  const elapsed = now - updatedAt;
  if (elapsed < -60000)
    return {label: "Last reported: timestamp is in the future", title: `Future reported timestamp: ${exact}`};
  if (elapsed < 60000)
    return {label: "Last reported: now", title: `Last reported: ${exact}`};
  if (elapsed < 3600000)
    return {label: `Last reported: ${Math.floor(elapsed / 60000)} min ago`, title: `Last reported: ${exact}`};
  if (elapsed < 86400000) {
    const hours = Math.floor(elapsed / 3600000);
    return {label: `Last reported: ${hours} hour${hours === 1 ? "" : "s"} ago`, title: `Last reported: ${exact}`};
  }
  const days = Math.floor(elapsed / 86400000);
  return {label: `Last reported: ${days} day${days === 1 ? "" : "s"} ago`, title: `Last reported: ${exact}`};
};
