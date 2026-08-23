const STATE_PRESENTATIONS = {
  pending: {
    label: "Loading",
    tone: "quiet",
    title: "Waiting for the first bounded read",
    detail: "MeshMonitor has not completed this read yet.",
  },
  ok: {
    label: "Current",
    tone: "ok",
    title: "Current data",
    detail: "The latest bounded read completed successfully.",
  },
  empty: {
    label: "Empty",
    tone: "quiet",
    title: "No configured automations",
    detail: "MeshMonitor returned a successful empty result.",
  },
  permission_denied: {
    label: "Permission denied",
    tone: "bad",
    title: "Automation access was denied",
    detail: "The dedicated account needs the global automations:read permission.",
  },
  unsupported: {
    label: "Not available",
    tone: "quiet",
    title: "Automation history is not available",
    detail: "This MeshMonitor deployment does not expose the requested read.",
  },
  authentication_error: {
    label: "Authentication error",
    tone: "bad",
    title: "MeshMonitor rejected the account",
    detail: "Review the integration authentication without broadening permissions.",
  },
  error: {
    label: "Read failed",
    tone: "bad",
    title: "Automation data could not be refreshed",
    detail: "The last bounded read failed; retained rows may be stale.",
  },
};

export const automationStatePresentation = (state, hasRetainedData = false) => {
  const presentation = STATE_PRESENTATIONS[state] || STATE_PRESENTATIONS.error;
  if (!hasRetainedData || state === "ok" || state === "empty") return presentation;
  return {
    ...presentation,
    detail: `${presentation.detail} Showing the last retained bounded data.`,
  };
};

export const automationOverviewSummary = (groups = []) => {
  const automations = groups.flatMap((group) => group.automations || []);
  const runs = automations.flatMap((automation) => automation.history?.runs || []);
  const enabled = automations.filter((automation) => automation.enabled === true).length;
  if (!groups.length)
    return {
      state: "disabled",
      tone: "quiet",
      label: "Off",
      automationCount: 0,
      enabledCount: 0,
      runCount: 0,
    };
  const states = groups.map((group) => group.state);
  const state = states.includes("authentication_error")
    ? "authentication_error"
    : states.includes("permission_denied")
      ? "permission_denied"
      : states.includes("error")
        ? "error"
        : states.includes("pending")
          ? "pending"
          : states.every((value) => value === "empty")
            ? "empty"
            : states.includes("unsupported") && !automations.length
              ? "unsupported"
              : "ok";
  const presentation = automationStatePresentation(state, automations.length > 0);
  return {
    state,
    tone: presentation.tone,
    label: presentation.label,
    automationCount: automations.length,
    enabledCount: enabled,
    runCount: runs.length,
  };
};

const timestampMs = (value) => {
  if (value === null || value === undefined || value === "") return Number.NaN;
  const parsed = typeof value === "number"
    ? value > 1e11
      ? value
      : value * 1000
    : new Date(value).valueOf();
  return Number.isFinite(parsed) ? parsed : Number.NaN;
};

export const sortedAutomationRuns = (runs = []) =>
  [...runs].sort((left, right) => {
    const leftTime = timestampMs(left.updated_at ?? left.started_at);
    const rightTime = timestampMs(right.updated_at ?? right.started_at);
    if (Number.isFinite(leftTime) !== Number.isFinite(rightTime))
      return Number.isFinite(leftTime) ? -1 : 1;
    if (Number.isFinite(leftTime) && leftTime !== rightTime) return rightTime - leftTime;
    return String(left.id ?? "").localeCompare(String(right.id ?? ""));
  });

export const automationRunPresentation = (run = {}) => {
  const normalized = String(run.status || "unknown").trim().toLowerCase() || "unknown";
  const tone = normalized === "completed"
    ? "ok"
    : normalized === "failed"
      ? "bad"
      : "quiet";
  return {
    status: normalized,
    label: normalized.replaceAll("_", " "),
    tone,
    timestamp: run.updated_at ?? run.started_at ?? null,
  };
};
