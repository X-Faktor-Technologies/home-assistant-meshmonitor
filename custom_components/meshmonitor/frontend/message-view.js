export const messageIsOutgoing = (message) =>
  message.direction === "outbound" ||
  message.direction === "sent" ||
  message.outgoing === true;

export const messageDirectPeerId = (message) =>
  messageIsOutgoing(message)
    ? message.to_id || "unknown"
    : message.from_id || "unknown";

export const messageConversationKey = (message) => {
  const direct = message.channel === -1 || message.channel == null;
  if (direct)
    return `direct:${message.protocol}:${messageDirectPeerId(message)}`;
  return `channel:${message.protocol}:${message.channel}`;
};

export const messageConversationCatalog = (
  messages,
  sources,
  pinned = new Set(),
) => {
  // Names are presentation only. The key retains protocol routing identity and
  // the channel index or direct peer ID used by the backend send command.
  const catalog = new Map();
  for (const source of sources) {
    for (const channel of source.channels || []) {
      const key = `channel:${source.protocol}:${channel.index}`;
      if (!catalog.has(key))
        catalog.set(key, {
          key,
          type: "channel",
          protocol: source.protocol,
          name: channel.name || `Channel ${channel.index}`,
          detail: source.name,
          channel: Number(channel.index),
        });
    }
  }
  for (const message of messages) {
    const key = messageConversationKey(message);
    const direct = key.startsWith("direct:");
    if (!catalog.has(key)) {
      const recipient = direct ? messageDirectPeerId(message) : null;
      const node = direct
        ? sources
            .filter((source) => source.protocol === message.protocol)
            .flatMap((source) => [
              ...(source.nodes || []),
              ...(source.reticulum?.peers || []),
            ])
            .find((item) => item.id === recipient)
        : null;
      catalog.set(key, {
        key,
        type: direct ? "direct" : "channel",
        protocol: message.protocol,
        name: direct
          ? node?.name ||
            (messageIsOutgoing(message) ? null : message.from_name) ||
            recipient ||
            "Unknown node"
          : message.channel_name || `Channel ${message.channel}`,
        detail: direct ? "Direct message" : message.protocol,
        ...(direct
          ? { recipient }
          : { channel: Number(message.channel) }),
      });
    }
  }
  return [...catalog.values()].sort((left, right) => {
    const pin = Number(pinned.has(right.key)) - Number(pinned.has(left.key));
    return pin || left.name.localeCompare(right.name);
  });
};

const sourceIsFresh = (source, now) => {
  if (!source.available || source.connected !== true || !source.fetched_at)
    return false;
  const fetched = new Date(source.fetched_at).valueOf();
  const staleAfter = Number(source.stale_after_seconds) * 1000;
  return (
    Number.isFinite(fetched) &&
    Number.isFinite(staleAfter) &&
    staleAfter > 0 &&
    now - fetched <= staleAfter
  );
};

export const conversationSourceChoices = (conversation, sources, now = Date.now()) => {
  if (!conversation || conversation.key === "all") return [];
  return sources
    .filter((source) => source.protocol === conversation.protocol)
    .filter((source) =>
      conversation.type === "channel"
        ? (source.channels || []).some(
            (channel) => Number(channel.index) === conversation.channel,
          )
        : conversation.recipient !== "unknown" &&
          [
            ...(source.nodes || []),
            ...(source.reticulum?.peers || []),
          ].some((node) => node.id === conversation.recipient),
    )
    .map((source) => {
      const fresh = sourceIsFresh(source, now);
      const enabled = source.transmit_enabled === true && fresh;
      let reason = "Eligible for backend permission and transmit checks";
      if (!source.transmit_enabled) reason = "Outbound option is off";
      else if (!source.available) reason = "Source is unavailable";
      else if (source.connected !== true) reason = "Source is disconnected";
      else if (!fresh) reason = "Source data is stale or incomplete";
      return { source, enabled, reason };
    });
};

export const messageByteLimit = (protocol, type) =>
  protocol === "reticulum"
    ? 4096
    : protocol === "meshcore"
      ? (type === "direct" ? 150 : 130)
      : 200;

const hasValidUnicode = (text) => {
  for (let index = 0; index < text.length; index += 1) {
    const unit = text.charCodeAt(index);
    if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = text.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return false;
      index += 1;
    } else if (unit >= 0xdc00 && unit <= 0xdfff) return false;
  }
  return true;
};

export const messageDraftValidation = (text, protocol, type) => {
  const bytes = new TextEncoder().encode(text).length;
  const limit = messageByteLimit(protocol, type);
  const unicodeValid = hasValidUnicode(text);
  return {
    bytes,
    limit,
    valid: Boolean(text.trim()) && unicodeValid && bytes <= limit,
    reason: !unicodeValid
      ? "Message contains invalid Unicode"
      : !text.trim()
      ? "Enter a message"
      : bytes > limit
        ? `Message exceeds the ${limit}-byte limit`
        : "Ready to review",
  };
};

export const messageSendNonce = (cryptoApi = globalThis.crypto) => {
  const bytes = new Uint8Array(16);
  if (cryptoApi?.getRandomValues) cryptoApi.getRandomValues(bytes);
  else {
    // A nonce prevents accidental replay; it is not an authentication secret.
    // Keep HTTP-only/local HA installations functional on older webviews.
    for (let index = 0; index < bytes.length; index += 1)
      bytes[index] = Math.floor(Math.random() * 256);
  }
  return [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
};

export const sendErrorPresentation = (error) => {
  const code = error?.code || "unknown";
  const messages = {
    invalid_auth: "Authentication failed. Reauthenticate before trying again.",
    permission_denied: "The MeshMonitor token lacks messages:write permission.",
    transmit_disabled: "Outbound messages are disabled for this exact source.",
    source_tx_disabled: "Protocol transmit is disabled on this exact source.",
    rate_limited: "Rate limit reached. Wait before deliberately trying again.",
    invalid_format: "The message or destination failed backend validation.",
    invalid_destination: "The exact destination is no longer valid.",
    protocol_mismatch: "The source protocol changed. Review the conversation again.",
    not_found: "The exact source or destination is no longer available.",
    duplicate: "This attempt was already activated and was blocked from replay.",
    send_failed: "MeshMonitor rejected the send; no retry was attempted.",
    queue_failed: "Home Assistant could not queue the reviewed send. Nothing was transmitted.",
  };
  if (messages[code]) return { code, ambiguous: false, message: messages[code] };
  if (code === "cannot_connect" || code === "timeout" || code === "unknown")
    return {
      code,
      ambiguous: true,
      message:
        "The result is ambiguous. Check stored history before deliberately trying again; no automatic retry was made.",
    };
  return {
    code,
    ambiguous: false,
    message: error?.message || "The send was blocked.",
  };
};

export const pendingMessagePresentation = (pending) => {
  if (pending.state === "sending")
    return { label: "Sending", title: "Submitting once to MeshMonitor" };
  if (pending.state === "accepted") {
    const deliveryState = String(pending.deliveryState || "accepted").toLowerCase();
    return {
      label: "Accepted by MeshMonitor",
      title:
        `MeshMonitor reported ${deliveryState}; stored history and radio delivery are not confirmed`,
    };
  }
  return {
    label: "Not sent",
    title: pending.error || "The send was not accepted",
  };
};

export const messagesInConversation = (messages, conversation) =>
  conversation === "all"
    ? [...messages]
    : messages.filter(
        (message) => messageConversationKey(message) === conversation,
      );

export const conversationUnreadCounts = (messages, lastReadByConversation = {}) => {
  const counts = new Map();
  for (const message of messages) {
    if (messageIsOutgoing(message)) continue;
    const key = messageConversationKey(message);
    const lastRead = Number(lastReadByConversation[key] || 0);
    if (messageTimestampMs(message) > lastRead)
      counts.set(key, (counts.get(key) || 0) + 1);
  }
  return counts;
};

export const messageTimestampMs = (message) => {
  const raw = message.created_at ?? message.timestamp;
  const numeric = Number(raw);
  if (Number.isFinite(numeric)) return numeric > 1e11 ? numeric : numeric * 1000;
  const parsed = new Date(raw).valueOf();
  return Number.isFinite(parsed) ? parsed : 0;
};

export const sortMessagesChronologically = (messages) =>
  [...messages].sort((left, right) => {
    const time = messageTimestampMs(left) - messageTimestampMs(right);
    return time || String(left.id || "").localeCompare(String(right.id || ""));
  });

export const shouldDeferMessagesRender = ({
  background = false,
  composerEngagedAtCompletion = false,
  messagesEngagedAtCompletion = false,
  messagePointerActive = false,
} = {}) =>
  background && (
    composerEngagedAtCompletion ||
    messagesEngagedAtCompletion ||
    messagePointerActive
  );

export const completeMessagesRefresh = ({
  background = false,
  activeElement = null,
  messagePointerActive = false,
  onDefer,
  onRender,
} = {}) => {
  const deferred = shouldDeferMessagesRender({
    background,
    messagesEngagedAtCompletion:
      activeElement?.closest?.(".conversation-shell") != null,
    messagePointerActive,
  });
  if (deferred) onDefer?.();
  else onRender?.();
  return deferred ? "deferred" : "rendered";
};

export const wireMessageInteractionGuard = (
  target,
  onActiveChange,
  schedule = (callback) => window.setTimeout(callback, 0),
  releaseTarget = target.ownerDocument,
) => {
  target.addEventListener("pointerdown", () => {
    onActiveChange(true);
    const release = () => {
      releaseTarget.removeEventListener("pointerup", release, true);
      releaseTarget.removeEventListener("pointercancel", release, true);
      schedule(() => onActiveChange(false));
    };
    releaseTarget.addEventListener("pointerup", release, true);
    releaseTarget.addEventListener("pointercancel", release, true);
  });
};

export const shouldFlushDeferredMessagesRender = ({
  deferred = false,
  messagePointerActive = false,
  onMessagesTab = false,
  composerEngaged = false,
  messagesEngaged = false,
} = {}) =>
  deferred &&
  onMessagesTab &&
  !messagePointerActive &&
  !composerEngaged &&
  !messagesEngaged;

export const messageTimelineAtBottom = (
  { scrollHeight, clientHeight, scrollTop },
  threshold = 48,
) => scrollHeight - clientHeight - scrollTop < threshold;

export const wireMessageTimelineControl = (timeline, button) => {
  const update = () => {
    button.hidden = messageTimelineAtBottom(timeline);
  };
  button.addEventListener("click", () => {
    timeline.scrollTop = timeline.scrollHeight;
    update();
    timeline.focus?.({ preventScroll: true });
  });
  timeline.addEventListener("scroll", update);
  update();
  return update;
};

export const messageTimelineRestorePosition = ({
  forceToBottom = false,
  saved,
} = {}) =>
  forceToBottom || saved?.atBottom ? "bottom" : saved?.top ?? "bottom";

const normalizedPeerId = (value) => String(value || "").toLowerCase();

export const messageSenderName = (message, sources = []) => {
  if (messageIsOutgoing(message)) return "You";
  if (message.from_name) return message.from_name;

  const senderId = normalizedPeerId(message.from_id);
  if (message.protocol === "reticulum" && senderId) {
    const receptionSourceIds = new Set(
      (message.receptions || [])
        .map((reception) => reception.source_id)
        .filter(Boolean),
    );
    const peer = sources
      .filter((source) => source.protocol === "reticulum")
      .filter(
        (source) =>
          receptionSourceIds.size === 0 || receptionSourceIds.has(source.source_id),
      )
      .flatMap((source) => source.reticulum?.peers || [])
      .find((item) => normalizedPeerId(item.id) === senderId);
    if (peer?.name && normalizedPeerId(peer.name) !== senderId) return peer.name;
    if (senderId.length > 20) return `${senderId.slice(0, 12)}…${senderId.slice(-6)}`;
  }

  return message.from_id || "Unknown sender";
};

export const messagePresentation = (message, lastRead = 0, sources = []) => {
  const outgoing = messageIsOutgoing(message);
  const receptions = Array.isArray(message.receptions)
    ? message.receptions
    : [];
  const sourceNames = [
    ...new Set(
      receptions
        .map((reception) => reception.source_name || reception.source_id)
        .filter(Boolean),
    ),
  ];
  const sourceCount =
    new Set(
      receptions
        .map((reception) => reception.source_id || reception.source_name)
        .filter(Boolean),
    ).size || receptions.length;
  const sourceSummary =
    sourceCount === 0
      ? "Source unavailable"
      : sourceCount === 1
        ? `Via ${sourceNames[0] || "1 source"}`
        : `Via ${sourceCount} sources`;

  return {
    body: message.text || (message.emoji ? `Reaction ${message.emoji}` : "(No text)"),
    deliveryState: message.delivery_state || "",
    outgoing,
    protocol: message.protocol || "unknown",
    sender: messageSenderName(message, sources),
    sourceNames,
    sourceSummary,
    timestamp: messageTimestampMs(message),
    // Local outbound history confirms our own send; it is not new inbound
    // activity that the user needs to read.
    unread: !outgoing && messageTimestampMs(message) > lastRead,
  };
};
