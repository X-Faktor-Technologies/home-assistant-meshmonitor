const timestamp = (value) => {
  if (!value) return null;
  const parsed = new Date(value).valueOf();
  return Number.isFinite(parsed) ? parsed : null;
};

const checkedLabel = (value, now) => {
  const checkedAt = timestamp(value);
  if (checkedAt === null) return "Not checked yet";
  const age = now - checkedAt;
  if (age < -60000) return "Check time unavailable";
  if (age < 60000) return "Checked now";
  if (age < 3600000) return `Checked ${Math.floor(age / 60000)} min ago`;
  const hours = Math.floor(age / 3600000);
  return `Checked ${hours} hour${hours === 1 ? "" : "s"} ago`;
};

export const serverCardPresentation = (server = {}, now = Date.now()) => {
  const health = server.health || {};
  const version = server.version || {};
  const healthState = health.state || "pending";
  const healthValue = health.value || {};
  const versionValue = version.value || {};
  const installed = versionValue.current_version || healthValue.version || null;
  const latest = versionValue.latest_version || null;

  const healthOk = healthState === "ok" && healthValue.status === "ok";
  const healthLabel = healthOk
    ? "Healthy"
    : healthState === "pending"
      ? "Checking"
      : health.stale
        ? "Health stale"
        : healthState === "authentication_error"
          ? "Authentication failed"
          : "Unavailable";

  let updateLabel = "Update status unknown";
  let updateTone = "quiet";
  if (version.state === "ok" && versionValue.update_available === true) {
    updateLabel = "Update available";
    updateTone = "attention";
  } else if (
    version.state === "ok" &&
    versionValue.update_available === false &&
    latest
  ) {
    updateLabel = "Up to date";
    updateTone = "ok";
  } else if (version.stale && latest) {
    updateLabel = "Update check stale";
  } else if (version.state === "not_checked") {
    updateLabel = "Update check unavailable";
  } else if (version.state === "authentication_error") {
    updateLabel = "Update check denied";
  } else if (version.state === "error") {
    updateLabel = "Update check failed";
  }

  return {
    installed: installed || "Unknown",
    latest: latest || "Unknown",
    healthLabel,
    healthTone: healthOk ? "ok" : healthState === "pending" ? "quiet" : "bad",
    updateLabel,
    updateTone,
    checked: checkedLabel(version.last_attempt_at, now),
    releaseUrl: versionValue.release_url || null,
  };
};
