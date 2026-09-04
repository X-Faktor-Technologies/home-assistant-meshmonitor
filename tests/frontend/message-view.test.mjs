import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  completeMessagesRefresh,
  conversationSourceChoices,
  messageByteLimit,
  messageConversationCatalog,
  messageConversationKey,
  messageDirectPeerId,
  messageDraftValidation,
  messagePresentation,
  pendingMessagePresentation,
  messageSenderName,
  messageSendNonce,
  messageTimestampMs,
  messageTimelineAtBottom,
  messageTimelineRestorePosition,
  messagesInConversation,
  shouldDeferMessagesRender,
  shouldFlushDeferredMessagesRender,
  sortMessagesChronologically,
  sendErrorPresentation,
  wireMessageInteractionGuard,
  wireMessageTimelineControl,
} from "../../custom_components/meshmonitor/frontend/message-view.js";

const SOURCE = {
  entry_id: "entry-1",
  source_id: "source-1",
  protocol: "meshtastic",
  name: "Synthetic Meshtastic",
  available: true,
  connected: true,
  fetched_at: "2026-08-17T19:00:00Z",
  stale_after_seconds: 300,
  transmit_enabled: true,
  channels: [{ index: 0, name: "Primary" }],
  nodes: [{ id: "!0000002a", name: "Synthetic node" }],
};

const HISTORY = Array.from({ length: 7 }, (_, index) => ({
  id: `mt:sender:p${1000 + index}`,
  protocol: "meshtastic",
  from_id: "sender",
  from_name: "Synthetic sender",
  channel: 0,
  channel_name: "Primary",
  text: `synthetic-${index}`,
  created_at: 1_770_000_000_000 + index,
  receptions: [{ source_id: "source-1" }],
}));

test("Primary and All messages contain the discovered stored history fixture", () => {
  const catalog = messageConversationCatalog(HISTORY, [SOURCE]);
  const primary = catalog.find((item) => item.name === "Primary");

  assert.equal(primary.key, "channel:meshtastic:0");
  assert.equal(messagesInConversation(HISTORY, primary.key).length, 7);
  assert.equal(messagesInConversation(HISTORY, "all").length, 7);
  assert.equal(messageConversationKey(HISTORY[0]), primary.key);
});

test("empty stored history keeps an honest channel destination", () => {
  const catalog = messageConversationCatalog([], [SOURCE]);

  assert.equal(catalog.length, 1);
  assert.equal(catalog[0].name, "Primary");
  assert.deepEqual(messagesInConversation([], catalog[0].key), []);
});

test("protocol names keep MeshCore and Meshtastic channels separate", () => {
  const meshcore = {
    ...HISTORY[0],
    id: "mc:source-2:9",
    protocol: "meshcore",
  };

  assert.notEqual(messageConversationKey(meshcore), messageConversationKey(HISTORY[0]));
  assert.deepEqual(
    messagesInConversation([HISTORY[0], meshcore], "channel:meshcore:0").map(
      (message) => message.id,
    ),
    ["mc:source-2:9"],
  );
});

test("direct identity uses the stable remote node in both directions", () => {
  const incoming = {
    protocol: "meshtastic",
    channel: null,
    from_id: "!0000002a",
    to_id: "!00000001",
  };
  const outgoing = { ...incoming, outgoing: true, from_id: "!00000001", to_id: "!0000002a" };

  assert.equal(messageDirectPeerId(incoming), "!0000002a");
  assert.equal(messageDirectPeerId(outgoing), "!0000002a");
  assert.equal(messageConversationKey(incoming), "direct:meshtastic:!0000002a");
  assert.equal(messageConversationKey(outgoing), "direct:meshtastic:!0000002a");
});

test("Reticulum conversations use announced friendly names instead of hashes", () => {
  const peerHash = "0123456789abcdef0123456789abcdef";
  const reticulum = {
    ...SOURCE,
    protocol: "reticulum",
    channels: [],
    nodes: [],
    reticulum: { peers: [{ id: peerHash, name: "Elier's LXMF" }] },
  };
  const incoming = {
    protocol: "reticulum",
    channel: -1,
    from_id: peerHash,
    to_id: "fedcba9876543210fedcba9876543210",
  };

  assert.equal(
    messageConversationCatalog([incoming], [reticulum])[0].name,
    "Elier's LXMF",
  );
});

test("outbound and inbound LXMF records share one friendly conversation in time order", () => {
  const localHash = "20914cb776e9d9e60418354ea6986238";
  const peerHash = "0123456789abcdef0123456789abcdef";
  const source = {
    ...SOURCE,
    protocol: "reticulum",
    channels: [],
    nodes: [],
    reticulum: { peers: [{ id: peerHash, name: "xPhone" }] },
  };
  const outbound = {
    id: "outbound",
    protocol: "reticulum",
    channel: -1,
    from_id: localHash,
    to_id: peerHash,
    direction: "outbound",
    created_at: 1_777_000_000_000,
  };
  const inbound = {
    id: "inbound",
    protocol: "reticulum",
    channel: -1,
    from_id: peerHash,
    to_id: localHash,
    direction: "incoming",
    created_at: 1_777_000_120_000,
  };

  const catalog = messageConversationCatalog([outbound, inbound], [source]);
  const key = `direct:reticulum:${peerHash}`;

  assert.deepEqual(catalog.map((item) => [item.key, item.name]), [[key, "xPhone"]]);
  assert.equal(messageConversationKey(outbound), key);
  assert.equal(messageConversationKey(inbound), key);
  assert.deepEqual(
    sortMessagesChronologically([inbound, outbound]).map((message) => message.id),
    ["outbound", "inbound"],
  );
});

test("Reticulum message cards use the announced peer name with a hash fallback", () => {
  const peerHash = "0123456789abcdef0123456789abcdef";
  const otherSource = {
    ...SOURCE,
    source_id: "source-other",
    protocol: "reticulum",
    nodes: [],
    reticulum: { peers: [{ id: peerHash, name: "Wrong source name" }] },
  };
  const reticulum = {
    ...SOURCE,
    protocol: "reticulum",
    nodes: [],
    reticulum: { peers: [{ id: peerHash, name: "Elier's LXMF" }] },
  };
  const incoming = {
    protocol: "reticulum",
    from_id: peerHash,
    receptions: [{ source_id: "source-1" }],
  };

  assert.equal(messageSenderName(incoming, [otherSource, reticulum]), "Elier's LXMF");
  assert.equal(
    messagePresentation(incoming, 0, [otherSource, reticulum]).sender,
    "Elier's LXMF",
  );
  assert.equal(
    messageSenderName({ ...incoming, from_name: "Stored friendly name" }, [reticulum]),
    "Stored friendly name",
  );
  assert.equal(
    messageSenderName({ ...incoming, receptions: [] }, []),
    "0123456789ab…abcdef",
  );
});

test("source choices are exact, explicit, fresh, and destination compatible", () => {
  const now = Date.parse("2026-08-17T19:02:00Z");
  const conversation = messageConversationCatalog(HISTORY, [SOURCE])[0];
  const second = { ...SOURCE, entry_id: "entry-2", source_id: "source-2", name: "Second" };
  const wrongChannel = { ...SOURCE, source_id: "wrong-channel", channels: [{ index: 1, name: "Secondary" }] };
  const stale = { ...SOURCE, source_id: "stale", fetched_at: "2026-08-17T18:00:00Z" };
  const disabled = { ...SOURCE, source_id: "disabled", transmit_enabled: false };

  const choices = conversationSourceChoices(
    conversation,
    [SOURCE, second, wrongChannel, stale, disabled],
    now,
  );

  assert.deepEqual(choices.map((choice) => choice.source.source_id), ["source-1", "source-2", "stale", "disabled"]);
  assert.deepEqual(choices.map((choice) => choice.enabled), [true, true, false, false]);
  assert.match(choices[2].reason, /stale/);
  assert.match(choices[3].reason, /option is off/);
});

test("Reticulum peers are eligible direct-message destinations", () => {
  const now = Date.parse("2026-08-17T19:02:00Z");
  const peerHash = "0123456789abcdef0123456789abcdef";
  const source = {
    ...SOURCE,
    protocol: "reticulum",
    nodes: [],
    reticulum: { peers: [{ id: peerHash, name: "Friendly peer" }] },
  };
  const conversation = {
    key: `direct:reticulum:${peerHash}`,
    type: "direct",
    protocol: "reticulum",
    recipient: peerHash,
  };

  const choices = conversationSourceChoices(conversation, [source], now);

  assert.equal(choices.length, 1);
  assert.equal(choices[0].enabled, true);
});

test("unknown direct targets and unsupported protocols stay non-sendable", () => {
  const unknown = { key: "direct:meshtastic:unknown", type: "direct", protocol: "meshtastic", recipient: "unknown" };
  const unsupported = { key: "channel:meshcore:0", type: "channel", protocol: "meshcore", channel: 0 };

  assert.deepEqual(conversationSourceChoices(unknown, [SOURCE]), []);
  assert.deepEqual(conversationSourceChoices(unsupported, [SOURCE]), []);
});

test("UTF-8 limits use encoded bytes at exact protocol boundaries", () => {
  assert.equal(messageByteLimit("meshtastic", "direct"), 200);
  assert.equal(messageByteLimit("meshcore", "channel"), 130);
  assert.equal(messageByteLimit("meshcore", "direct"), 150);
  assert.equal(messageByteLimit("reticulum", "direct"), 4096);
  assert.equal(messageDraftValidation("é".repeat(75), "meshcore", "direct").valid, true);
  assert.equal(messageDraftValidation("é".repeat(76), "meshcore", "direct").valid, false);
  assert.equal(messageDraftValidation("\n", "meshtastic", "channel").valid, false);
  assert.equal(messageDraftValidation("broken\ud800", "meshtastic", "channel").valid, false);
});

test("send errors distinguish deterministic blocks from ambiguous outcomes", () => {
  assert.equal(sendErrorPresentation({ code: "permission_denied" }).ambiguous, false);
  assert.match(sendErrorPresentation({ code: "rate_limited" }).message, /Wait/);
  assert.equal(sendErrorPresentation({ code: "cannot_connect" }).ambiguous, true);
  assert.match(sendErrorPresentation({}).message, /no automatic retry/);
});

test("send nonce works on HTTP origins without crypto.randomUUID", () => {
  const cryptoWithoutUuid = {
    getRandomValues(bytes) {
      bytes.forEach((_, index) => { bytes[index] = index; });
      return bytes;
    },
  };

  assert.equal(
    messageSendNonce(cryptoWithoutUuid),
    "000102030405060708090a0b0c0d0e0f",
  );
  assert.equal(messageSendNonce(cryptoWithoutUuid).length, 32);
});

test("radio-backed sends await MeshMonitor and preserve its acceptance state", () => {
  const panel = readFileSync(
    new URL(
      "../../custom_components/meshmonitor/frontend/meshmonitor-panel.js",
      import.meta.url,
    ),
    "utf8",
  );

  assert.match(panel, /const result = await this\._hass\.callWS\(request\)/);
  assert.match(panel, /id: messageSendNonce\(\)/);
  assert.match(panel, /nonce: pending\.id/);
  assert.doesNotMatch(panel, /crypto\.randomUUID/);
  assert.doesNotMatch(panel, /connection\.sendMessagePromise/);
  assert.match(panel, /pending\.state = "accepted"/);
  assert.match(panel, /pending\.deliveryState = result\.delivery_state \|\| "accepted"/);
  assert.doesNotMatch(panel, /Queued once by Home Assistant/);
  assert.deepEqual(
    pendingMessagePresentation({ state: "accepted", deliveryState: "sent" }),
    { label: "Sent", title: "Sent; radio delivery is not confirmed" },
  );
  assert.deepEqual(
    pendingMessagePresentation({ state: "accepted", deliveryState: "queued" }),
    {
      label: "Queued by MeshMonitor",
      title: "Queued by MeshMonitor; radio delivery is not confirmed",
    },
  );
});

test("timeline presentation keeps provenance compact and deterministic", () => {
  const presentation = messagePresentation(
    {
      ...HISTORY[0],
      receptions: [
        { source_id: "source-1", source_name: "North relay" },
        { source_id: "source-2", source_name: "South relay" },
        { source_id: "source-1", source_name: "North relay" },
      ],
    },
    HISTORY[0].created_at - 1,
  );

  assert.equal(presentation.sender, "Synthetic sender");
  assert.equal(presentation.sourceSummary, "Via 2 sources");
  assert.deepEqual(presentation.sourceNames, ["North relay", "South relay"]);
  assert.equal(presentation.unread, true);
  assert.equal(presentation.outgoing, false);
});

test("unknown, reaction, outbound, and timestamp fallbacks stay honest", () => {
  assert.equal(messageTimestampMs({ created_at: 1_800_000_000 }), 1_800_000_000_000);
  assert.equal(messageTimestampMs({ timestamp: "not-a-date" }), 0);
  assert.deepEqual(
    messagePresentation({ outgoing: true, text: "sent", receptions: [] }),
    {
      body: "sent",
      deliveryState: "",
      outgoing: true,
      protocol: "unknown",
      sender: "You",
      sourceNames: [],
      sourceSummary: "Source unavailable",
      timestamp: 0,
      unread: false,
    },
  );
  assert.equal(messagePresentation({ emoji: "👍" }).body, "Reaction 👍");
  assert.equal(messagePresentation({}).sender, "Unknown sender");
});

test("outbound history never becomes unread", () => {
  const presentation = messagePresentation(
    { outgoing: true, text: "sent", created_at: 1_800_000_000_000, receptions: [] },
    1_700_000_000_000,
  );

  assert.equal(presentation.outgoing, true);
  assert.equal(presentation.unread, false);
});

test("timer refresh deferral protects live composer engagement", async () => {
  let composerEngagedAtCompletion = false;
  const refresh = Promise.resolve().then(() => {
    composerEngagedAtCompletion = true;
  });
  await refresh;

  assert.equal(
    shouldDeferMessagesRender({
      background: true,
      composerEngagedAtCompletion,
      messagePointerActive: false,
    }),
    true,
    "focus acquired while a refresh is in flight must prevent destructive rendering",
  );
  assert.equal(shouldDeferMessagesRender({
    background: true,
    messagePointerActive: true,
  }), true, "pointerdown through click must not be interrupted by a refresh render");
  assert.equal(
    shouldDeferMessagesRender({
      background: true,
      composerEngagedAtCompletion: false,
    }),
    false,
  );
  assert.equal(
    shouldDeferMessagesRender({
      background: false,
      composerEngagedAtCompletion: true,
    }),
    false,
  );

  const panel = readFileSync(
    new URL("../../custom_components/meshmonitor/frontend/meshmonitor-panel.js", import.meta.url),
    "utf8",
  );
  assert.match(panel, /this\._load\(\{ background: true \}\)/);
  const request = panel.indexOf("await this._hass.callWS({ type: \"meshmonitor/panel\" })");
  const finallyPath = panel.indexOf("} finally {", request);
  assert.ok(request >= 0 && request < finallyPath, "finally follows the asynchronous request");
  assert.match(panel, /activeElement: this\.shadowRoot\?\.activeElement/);
  assert.match(panel, /messagePointerActive: this\._messagePointerActive/);
  assert.match(panel, /else completeMessagesRefresh\(\{/);
  const loadFinally = panel.slice(finallyPath, panel.indexOf("\n  _allNodes()", finallyPath));
  assert.match(loadFinally, /activeElement/);
  assert.match(panel, /_render\(\) \{\s+if \(!this\.shadowRoot\) return;\s+this\._deferredMessagesRender = false;/);
  assert.doesNotMatch(panel, /compose-text"\)\?\.addEventListener\("blur"/);
  assert.doesNotMatch(panel, /addEventListener\("blur"/);
  assert.match(panel, /_flushDeferredMessagesRender\(\)/);
  assert.match(panel, /composer\?\.addEventListener\("focusout"/);
});

test("background refresh preserves an engaged composer's focus and caret", () => {
  const textarea = {
    value: "A deliberately unfinished draft",
    selectionStart: 14,
    selectionEnd: 14,
    closest(selector) {
      return selector === ".compose" ? { className: "compose" } : null;
    },
  };
  let deferred = false;
  let destructiveRenderCount = 0;

  const outcome = completeMessagesRefresh({
    background: true,
    activeElement: textarea,
    onDefer: () => { deferred = true; },
    onRender: () => {
      destructiveRenderCount += 1;
      textarea.value = "";
      textarea.selectionStart = 0;
      textarea.selectionEnd = 0;
    },
  });

  assert.equal(outcome, "deferred");
  assert.equal(deferred, true);
  assert.equal(destructiveRenderCount, 0);
  assert.equal(textarea.value, "A deliberately unfinished draft");
  assert.equal(textarea.selectionStart, 14);
  assert.equal(textarea.selectionEnd, 14);
});

test("message pointer guard protects activation until click delivery", () => {
  const composer = new EventTarget();
  const releaseTarget = new EventTarget();
  const scheduled = [];
  let pointerActive = false;
  let clickDelivered = false;
  wireMessageInteractionGuard(
    composer,
    (active) => { pointerActive = active; },
    (callback) => scheduled.push(callback),
    releaseTarget,
  );
  composer.addEventListener("click", () => { clickDelivered = true; });

  composer.dispatchEvent(new Event("pointerdown"));
  assert.equal(pointerActive, true);
  assert.equal(shouldDeferMessagesRender({
    background: true,
    messagePointerActive: pointerActive,
  }), true, "refresh completion between pointerdown and click must defer rendering");

  releaseTarget.dispatchEvent(new Event("pointerup"));
  assert.equal(pointerActive, true, "pointerup defers release until after click dispatch");
  composer.dispatchEvent(new Event("click"));
  assert.equal(clickDelivered, true);
  scheduled.shift()();
  assert.equal(pointerActive, false);

  composer.dispatchEvent(new Event("pointerdown"));
  assert.equal(pointerActive, true);
  releaseTarget.dispatchEvent(new Event("pointercancel"));
  scheduled.shift()();
  assert.equal(pointerActive, false, "release outside the composer cannot leave the guard active");
});

test("deferred refresh flushes only after message interaction ends", () => {
  assert.equal(shouldFlushDeferredMessagesRender({
    deferred: true,
    onMessagesTab: true,
  }), true);
  assert.equal(shouldFlushDeferredMessagesRender({
    deferred: true,
    onMessagesTab: true,
    composerEngaged: true,
  }), false);
  assert.equal(shouldFlushDeferredMessagesRender({
    deferred: true,
    onMessagesTab: true,
    messagePointerActive: true,
  }), false);
  assert.equal(shouldFlushDeferredMessagesRender({
    deferred: true,
    onMessagesTab: false,
  }), false);
  assert.equal(shouldFlushDeferredMessagesRender({
    deferred: false,
    onMessagesTab: true,
  }), false);
});

test("message timelines force latest only for selections and sends", () => {
  assert.equal(
    messageTimelineRestorePosition({ forceToBottom: true, saved: { top: 120 } }),
    "bottom",
  );
  assert.equal(
    messageTimelineRestorePosition({ saved: { atBottom: true, top: 120 } }),
    "bottom",
  );
  assert.equal(
    messageTimelineRestorePosition({ saved: { atBottom: false, top: 120 } }),
    120,
  );
  assert.equal(messageTimelineAtBottom({ scrollHeight: 1000, clientHeight: 400, scrollTop: 600 }), true);
  assert.equal(messageTimelineAtBottom({ scrollHeight: 1000, clientHeight: 400, scrollTop: 500 }), false);
});

test("scroll-to-latest follows real scroll and click transitions", () => {
  const timeline = new EventTarget();
  timeline.scrollHeight = 1000;
  timeline.clientHeight = 400;
  timeline.scrollTop = 300;
  let focused = false;
  timeline.focus = () => { focused = true; };
  const button = new EventTarget();
  button.hidden = true;

  wireMessageTimelineControl(timeline, button);
  assert.equal(button.hidden, false, "control appears while reading older messages");

  button.dispatchEvent(new Event("click"));
  assert.equal(timeline.scrollTop, 1000);
  assert.equal(button.hidden, true);
  assert.equal(focused, true, "keyboard focus returns to the timeline after jumping");

  timeline.scrollTop = 200;
  timeline.dispatchEvent(new Event("scroll"));
  assert.equal(button.hidden, false);
});

test("Messages includes persistent backend notification controls", () => {
  const panel = readFileSync(
    new URL("../../custom_components/meshmonitor/frontend/meshmonitor-panel.js", import.meta.url),
    "utf8",
  );
  assert.match(panel, /id="notification-bell"/);
  assert.match(panel, /class="tab-bar"/);
  assert.match(panel, /_notificationBell\(\)/);
  assert.match(panel, /Message notifications disabled/);
  assert.match(panel, /\.notification-bell svg \{[^}]+fill:none/);
  assert.match(panel, /\.notification-bell\.enabled svg \{ fill:currentColor; stroke:none/);
  assert.match(panel, /\.notification-bell \{[^}]+border:0[^}]+background:transparent[^}]+box-shadow:none/);
  assert.match(panel, /meshmonitor\/notification_settings/);
  assert.match(panel, /meshmonitor\/update_notification_settings/);
  assert.match(panel, /All incoming messages/);
  assert.match(panel, /Channel messages only/);
  assert.match(panel, /Direct messages only/);
  assert.match(panel, /History, sent messages, and replays are excluded/);
  assert.match(panel, /No notification targets found/);
  assert.match(panel, /target\.entity_id/);
  assert.match(panel, /<select id="notification-target">/);
  assert.doesNotMatch(panel, /name="notification-target"/);
  assert.match(panel, /notificationDeepLink\(window\.location\.search\)/);
  assert.match(panel, /set route\(value\)/);
  assert.match(panel, /window\.addEventListener\("location-changed"/);
  assert.match(panel, /_applyNotificationDeepLink\(\)/);
  assert.match(panel, /this\._tab = "messages"/);
  assert.match(panel, /data-message-id=/);
  assert.match(panel, /_restoreNotificationDeepLink\(\)/);
  assert.match(panel, /nav::-webkit-scrollbar \{ display:none/);
});

test("conversation DOM keeps a visible focusable scroll region and calm cards", () => {
  const panel = readFileSync(
    new URL("../../custom_components/meshmonitor/frontend/meshmonitor-panel.js", import.meta.url),
    "utf8",
  );

  assert.match(panel, /overflow-y:scroll/);
  assert.match(panel, /scrollbar-width:auto/);
  assert.match(panel, /scrollbar-gutter:stable/);
  assert.match(panel, /class="messages"[^>]+role="log"[^>]+tabindex="0"/);
  assert.match(panel, /_messageScrollByConversation/);
  assert.match(panel, /_forceMessageScrollToBottom = true/);
  assert.match(panel, /id = "scroll-to-latest"/);
  assert.match(panel, /button\.textContent = "Scroll to latest"/);
  assert.match(panel, /button\.type = "button"/);
  assert.match(panel, /wrapper\.className = "timeline-wrapper"/);
  assert.match(panel, /timeline\.replaceWith\(wrapper\);\s+wrapper\.append\(timeline, button\)/);
  assert.match(panel, /wireMessageTimelineControl\(timeline, button\)/);
  assert.match(panel, /\.timeline-wrapper \{ grid-row:2; position:relative; min-width:0; min-height:0; \}/);
  assert.match(panel, /@media\(max-width:760px\)\{\.timeline-wrapper\{grid-row:1\}\}/);
  assert.match(panel, /\.scroll-to-latest \{ position:absolute; right:20px; bottom:16px;/);
  assert.doesNotMatch(panel, /bottom:116px/);
  assert.match(panel, /\.scroll-to-latest:focus-visible \{ outline:3px solid var\(--primary-color\)/);
  assert.match(panel, /id="compose-send"/);
  assert.match(panel, /this\._sending \? "Sending…" : "Send"/);
  assert.match(panel, /data-reply-message/);
  assert.match(panel, /this\._composeText = ""/);
  assert.match(panel, /this\._messageDrafts\.delete\(this\._conversation\)/);
  assert.match(panel, /class="message outgoing pending"/);
  assert.match(panel, /border-bottom-left-radius:0/);
  assert.match(panel, /border-bottom-right-radius:0/);
  assert.match(panel, /main\.messages-view \{[^}]*overflow:hidden/);
  assert.match(panel, /#compose-send \{[^}]*background:var\(--primary-color\)/);
  assert.match(panel, /\.compose-route\{[^}]*text-overflow:ellipsis[^}]*white-space:nowrap/);
  assert.match(panel, /\.compose-action #compose-send\{[^}]*width:100%[^}]*min-height:44px/);
  assert.match(panel, /\.conversation-shell\{height:100%[^}]*min-height:0/);
  assert.match(panel, /\.compose textarea\{[^}]*min-height:44px[^}]*max-height:96px/);
  assert.match(panel, /\.compose-note\{display:none/);
  assert.match(panel, /safe-area-inset-bottom/);
  assert.doesNotMatch(panel, /height:max\(640px,calc\(100dvh - 92px\)\)/);
  assert.doesNotMatch(panel, /\.conversation-item \{[^}]*border-bottom:/);
  assert.doesNotMatch(panel, /window\.confirm/);
  assert.doesNotMatch(panel, /Review outbound message/);
  assert.doesNotMatch(panel, /\.message \{[^}]*border-left:4px/);
});

test("message bubbles are content-sized and safely wrap at every breakpoint", () => {
  const panel = readFileSync(
    new URL("../../custom_components/meshmonitor/frontend/meshmonitor-panel.js", import.meta.url),
    "utf8",
  );

  assert.match(panel, /\.message \{ width:fit-content; max-width:min\(82%,760px\)/);
  assert.match(panel, /\.message-text \{[^}]*overflow-wrap:anywhere/);
  assert.match(panel, /@media\(max-width:760px\)[\s\S]*?\.message \{ width:fit-content; max-width:100%/);
  assert.match(panel, /\.message\.incoming \{[^}]*border-bottom-left-radius:0/);
  assert.match(panel, /\.message\.outgoing \{[^}]*border-bottom-right-radius:0/);
});
