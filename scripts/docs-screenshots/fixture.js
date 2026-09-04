const NOW = Date.now();

const nodeNames = [
  "Canyon Relay", "Pine Lookout", "Summit House", "Trailhead",
  "Juniper Base", "North Ridge", "Blue Mesa", "Fox Hollow",
  "River Gate", "Aspen Camp", "Granite Point", "Lake Station",
];

const makeNodes = (source, protocol, offset, count) =>
  Array.from({ length: count }, (_, index) => ({
    id: `${protocol}-${index + 1}`,
    node_num: offset + index + 1,
    name: nodeNames[(offset + index) % nodeNames.length],
    protocol,
    source_id: source.source_id,
    source_name: source.name,
    entry_id: source.entry_id,
    last_heard: NOW - index * 4 * 60_000,
    battery: 94 - index * 5,
    voltage: 4.18 - index * 0.04,
    rssi: -79 - index * 4,
    snr: 10.5 - index * 0.8,
    hops: index % 4,
    role: protocol === "meshcore" ? (index % 3 === 0 ? "Repeater" : "Companion") : (index % 4 === 0 ? "Router" : "Client"),
    favorite: index < 2,
    latitude: 39.60 + ((offset + index) % 5) * 0.045,
    longitude: -105.24 + Math.floor((offset + index) / 5) * 0.08,
  }));

const meshtastic = {
  entry_id: "entry-mesa",
  source_id: "source-mesa",
  name: "Mesa Green",
  protocol: "meshtastic",
  available: true,
  connected: true,
  fetched_at: new Date(NOW).toISOString(),
  stale_after_seconds: 300,
  errors: [],
  transmit_enabled: true,
  channels: [{ index: 0, name: "Primary" }],
  device: {
    model: "RAK4631",
    firmware: "2.7.26",
    frequency_mhz: 906.875,
    bandwidth_khz: 250,
    spreading_factor: 11,
    coding_rate: 5,
    battery_percent: 93,
    battery_voltage: 4.16,
    uptime_seconds: 196200,
    noise_floor_dbm: -118,
    last_rssi_dbm: -82,
    last_snr_db: 8.5,
    packets_received: 1842,
    receive_errors: 2,
  },
  firmware_update: { state: "current", latest_version: "2.7.26" },
};

const meshcore = {
  entry_id: "entry-mesa",
  source_id: "source-orchid",
  name: "Orchid Purple",
  protocol: "meshcore",
  available: true,
  connected: true,
  fetched_at: new Date(NOW - 20_000).toISOString(),
  stale_after_seconds: 300,
  errors: [],
  transmit_enabled: true,
  channels: [{ index: 0, name: "Public" }, { index: 1, name: "#trail" }],
  device: {
    model: "RAK3401",
    firmware: "1.17.1",
    frequency_mhz: 910.525,
    bandwidth_khz: 62.5,
    spreading_factor: 7,
    coding_rate: 5,
    battery_voltage: 4.11,
    uptime_seconds: 284500,
    noise_floor_dbm: -121,
    last_rssi_dbm: -91,
    last_snr_db: 7.75,
    packets_received: 3264,
    receive_errors: 0,
  },
  firmware_update: { state: "current", latest_version: "1.17.1" },
};

const reticulum = {
  entry_id: "entry-mesa",
  source_id: "source-rns",
  name: "Azure RNS",
  protocol: "reticulum",
  available: true,
  connected: true,
  fetched_at: new Date(NOW - 40_000).toISOString(),
  stale_after_seconds: 300,
  errors: [],
  transmit_enabled: true,
  channels: [],
  reticulum: {
    interface_count: 4,
    destination_count: 7,
    rns_version: "1.0.0",
    bridge_version: "4.15.2",
    mode: "attach",
    identity_name: "Azure RNS",
    identity_hash: "0123456789abcdef0123456789abcdef",
    peers: [
      {
        id: "abcdef0123456789abcdef0123456789",
        name: "Bluebird LXMF",
        app_name: "lxmf",
        last_seen: NOW - 90_000,
        latitude: 39.79,
        longitude: -104.91,
        rssi: -91,
        snr: 7.5,
        hops: 2,
        favorite: true,
      },
    ],
  },
  device: {},
  firmware_update: { state: "unknown" },
};

meshtastic.nodes = makeNodes(meshtastic, "meshtastic", 0, 12);
meshcore.nodes = makeNodes(meshcore, "meshcore", 12, 10);
reticulum.nodes = [];

meshtastic.node_count = meshtastic.nodes.length;
meshtastic.positioned_count = meshtastic.nodes.length;
meshcore.node_count = meshcore.nodes.length;
meshcore.positioned_count = meshcore.nodes.length;
reticulum.node_count = 1;
reticulum.positioned_count = 1;

meshtastic.topology = {
  state: "supported",
  nodes: meshtastic.nodes,
  edges: meshtastic.nodes.slice(1, 8).map((node, index) => ({
    from_id: meshtastic.nodes[index].id,
    to_id: node.id,
    route: [],
    snr: [8.5 - index * 0.5],
  })),
};
meshtastic.neighbors = {
  state: "supported",
  links: meshtastic.nodes.slice(1, 6).map((node, index) => ({
    from_id: meshtastic.nodes[index].id,
    to_id: node.id,
    from_name: meshtastic.nodes[index].name,
    to_name: node.name,
    snr: 9 - index,
    reverse_snr: 8.5 - index,
  })),
};
meshcore.topology = { state: "not_available", nodes: [], edges: [] };
meshcore.neighbors = { state: "not_available", links: [] };

const reception = (source) => ({
  source_id: source.source_id,
  source_name: source.name,
  entry_id: source.entry_id,
});

const messages = [
  {
    id: "mc-public-1",
    protocol: "meshcore",
    from_id: "meshcore-3",
    from_name: "Summit House",
    channel: 0,
    channel_name: "Public",
    text: "Morning check-in complete.",
    created_at: NOW - 28 * 60_000,
    receptions: [reception(meshcore)],
  },
  {
    id: "mc-public-5",
    protocol: "meshcore",
    from_id: "meshcore-4",
    from_name: "Trailhead",
    channel: 0,
    channel_name: "Public",
    text: "Repeater path looks good from here.",
    created_at: NOW - 10 * 60_000,
    receptions: [reception(meshcore)],
  },
  {
    id: "mc-public-6",
    protocol: "meshcore",
    from_id: "meshcore-local",
    from_name: "Orchid Purple",
    channel: 0,
    channel_name: "Public",
    text: "Thanks!",
    created_at: NOW - 8 * 60_000,
    direction: "outbound",
    outgoing: true,
    delivery_state: "stored",
    receptions: [reception(meshcore)],
  },
  {
    id: "mc-public-7",
    protocol: "meshcore",
    from_id: "meshcore-6",
    from_name: "North Ridge",
    channel: 0,
    channel_name: "Public",
    text: "Signal report: clear and readable.",
    created_at: NOW - 6 * 60_000,
    receptions: [reception(meshcore)],
  },
  {
    id: "mc-public-8",
    protocol: "meshcore",
    from_id: "meshcore-local",
    from_name: "Orchid Purple",
    channel: 0,
    channel_name: "Public",
    text: "Great.",
    created_at: NOW - 4 * 60_000,
    direction: "outbound",
    outgoing: true,
    delivery_state: "stored",
    receptions: [reception(meshcore)],
  },
  {
    id: "mc-public-2",
    protocol: "meshcore",
    from_id: "meshcore-local",
    from_name: "Orchid Purple",
    to_id: "public",
    channel: 0,
    channel_name: "Public",
    text: "Trail conditions are clear near the lower ridge.",
    created_at: NOW - 23 * 60_000,
    direction: "outbound",
    outgoing: true,
    delivery_state: "stored",
    receptions: [reception(meshcore)],
  },
  {
    id: "mc-public-3",
    protocol: "meshcore",
    from_id: "meshcore-5",
    from_name: "Juniper Base",
    channel: 0,
    channel_name: "Public",
    text: "Copy that.",
    created_at: NOW - 19 * 60_000,
    receptions: [reception(meshcore)],
  },
  {
    id: "mc-public-4",
    protocol: "meshcore",
    from_id: "meshcore-7",
    from_name: "Blue Mesa",
    channel: 0,
    channel_name: "Public",
    text: "A longer example message wraps naturally while shorter replies stay compact and easy to scan.",
    created_at: NOW - 14 * 60_000,
    receptions: [reception(meshcore)],
  },
  {
    id: "mt-primary-1",
    protocol: "meshtastic",
    from_id: "meshtastic-2",
    from_name: "Pine Lookout",
    channel: 0,
    channel_name: "Primary",
    text: "Weather station is online.",
    created_at: NOW - 11 * 60_000,
    receptions: [reception(meshtastic)],
  },
  {
    id: "rns-direct-1",
    protocol: "reticulum",
    from_id: "abcdef0123456789abcdef0123456789",
    from_name: "Bluebird LXMF",
    to_id: "0123456789abcdef0123456789abcdef",
    channel: -1,
    text: "Encrypted delivery confirmed.",
    created_at: NOW - 7 * 60_000,
    receptions: [reception(reticulum)],
  },
];

export const screenshotFixture = {
  sources: [meshtastic, meshcore, reticulum],
  messages,
  message_status: "ready",
  can_send_messages: true,
  servers: [
    {
      entry_id: "entry-mesa",
      name: "Synthetic MeshMonitor",
      source_count: 3,
      health: { state: "ok", value: { status: "ok", version: "4.15.2" } },
      version: {
        state: "ok",
        last_attempt_at: new Date(NOW).toISOString(),
        value: {
          current_version: "4.15.2",
          latest_version: "4.15.2",
          update_available: false,
        },
      },
    },
  ],
  automation_groups: [
    {
      entry_ids: ["entry-mesa"],
      state: "ok",
      definitions_truncated: false,
      sources: [{ id: "source-mesa", name: "Mesa Green" }],
      automations: [
        {
          id: "source-health-watch",
          name: "Source health watch",
          description: "Reports a sustained source outage.",
          enabled: true,
          updated_at: NOW - 24 * 60 * 60_000,
          history: { state: "ok", runs: [] },
        },
      ],
    },
  ],
};
