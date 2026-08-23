export const PANEL_TABS = Object.freeze([
  Object.freeze({ value: "overview", label: "Overview" }),
  Object.freeze({ value: "messages", label: "Messages" }),
  Object.freeze({ value: "nodes", label: "Nodes" }),
  Object.freeze({ value: "map", label: "Map" }),
]);

const TAB_VALUES = new Set(PANEL_TABS.map(({ value }) => value));

export const normalizePanelTab = (value) => {
  if (value === "routes") return "nodes";
  return TAB_VALUES.has(value) ? value : PANEL_TABS[0].value;
};

export const adjacentPanelTab = (current, key) => {
  const value = normalizePanelTab(current);
  const index = PANEL_TABS.findIndex((tab) => tab.value === value);
  if (key === "Home") return PANEL_TABS[0].value;
  if (key === "End") return PANEL_TABS.at(-1).value;
  if (key === "ArrowRight")
    return PANEL_TABS[(index + 1) % PANEL_TABS.length].value;
  if (key === "ArrowLeft")
    return PANEL_TABS[(index - 1 + PANEL_TABS.length) % PANEL_TABS.length]
      .value;
  return null;
};

export const notificationDeepLink = (search) => {
  const query = new URLSearchParams(search || "");
  const conversation = query.get("conversation") || "";
  if (
    query.get("tab") !== "messages" ||
    !/^(direct|channel):[^:]+:.{1,160}$/.test(conversation)
  ) return null;
  return {
    conversation,
    messageId: (query.get("message") || "").slice(0, 240),
  };
};
