"""Home Assistant integration for MeshMonitor."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType

from .automation_coordinator import MeshMonitorAutomationCoordinator
from .const import (
    CONF_ENABLE_AUTOMATION_VISIBILITY,
    CONF_ENABLE_MESSAGE_POLLING,
    CONF_ENABLE_SIDEBAR_PANEL,
    CONF_EXPOSE_MESSAGE_TEXT,
    CONF_MESSAGE_SCAN_INTERVAL,
    CONF_SCAN_INTERVAL,
    CONF_SERVER_OPTIONS,
    CONF_SOURCE_ID,
    CONF_SOURCE_NAME,
    CONF_SOURCE_OPTIONS,
    CONF_SOURCE_TYPE,
    CONF_SOURCES,
    DOMAIN,
    PLATFORMS,
    SOURCE_TYPE_MESHCORE,
    SOURCE_TYPE_MESHTASTIC,
    SOURCE_TYPE_RETICULUM,
)
from .coordinator import MeshMonitorCoordinator
from .firmware_updates import async_refresh_releases
from .message_coordinator import MeshMonitorMessageCoordinator, MessageSource
from .node_event_monitor import MeshMonitorNodeEventMonitor
from .notification_manager import MeshMonitorNotificationManager
from .panel import async_register_panel, async_remove_panel
from .registry import (
    node_device_identifier,
    server_device_identifier,
    server_fingerprint,
    source_device_identifier,
)
from .server_health_coordinator import MeshMonitorServerHealthCoordinator
from .source_connection import MeshMonitorSourceConnectionRegistry
from .vendor_meshmonitor_client import MeshMonitorClient
from .websocket_api import async_register_websocket_commands


@dataclass(slots=True)
class MeshMonitorSourceRuntime:
    """Runtime context for one stored child source."""

    entry: MeshMonitorConfigEntry
    client: MeshMonitorClient
    coordinator: MeshMonitorCoordinator
    source_id: str
    source_name: str
    source_type: str

    @property
    def entry_id(self) -> str:
        """Return the owning server entry ID."""
        return self.entry.entry_id

    @property
    def title(self) -> str:
        """Return the readable source label."""
        return self.source_name or self.source_id

    @property
    def data(self) -> dict[str, Any]:
        """Expose the narrow legacy-shaped view used by panel helpers."""
        return {
            CONF_URL: self.entry.data[CONF_URL],
            CONF_SOURCE_ID: self.source_id,
            CONF_SOURCE_NAME: self.source_name,
            CONF_SOURCE_TYPE: self.source_type,
        }

    @property
    def options(self) -> dict[str, Any]:
        """Return only this source's isolated options."""
        return source_options(self.entry, self.source_id)

    @property
    def runtime_data(self) -> MeshMonitorSourceRuntime:
        """Keep existing source consumers explicit and narrowly compatible."""
        return self

    def async_on_unload(self, func: Any) -> Any:
        """Bind source listeners to the owning server entry lifecycle."""
        return self.entry.async_on_unload(func)


@dataclass(slots=True)
class MeshMonitorRuntimeData:
    """Runtime objects associated with one exact-server config entry."""

    client: MeshMonitorClient
    fingerprint: str
    sources: dict[str, MeshMonitorSourceRuntime]


type MeshMonitorConfigEntry = ConfigEntry[MeshMonitorRuntimeData]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def server_options(entry: MeshMonitorConfigEntry) -> dict[str, Any]:
    """Return the server-global option mapping."""
    value = entry.options.get(CONF_SERVER_OPTIONS)
    return dict(value) if isinstance(value, Mapping) else {}


def source_options(entry: MeshMonitorConfigEntry, source_id: str) -> dict[str, Any]:
    """Return options isolated to one stored source."""
    sources = entry.options.get(CONF_SOURCE_OPTIONS, {})
    if not isinstance(sources, Mapping):
        return {}
    value = sources.get(source_id, {})
    return dict(value) if isinstance(value, Mapping) else {}


def source_runtimes(entry: MeshMonitorConfigEntry) -> tuple[MeshMonitorSourceRuntime, ...]:
    """Return stable source contexts for a loaded server entry."""
    runtime = getattr(entry, "runtime_data", None)
    sources = getattr(runtime, "sources", None)
    if isinstance(sources, Mapping):
        return tuple(sources[source_id] for source_id in sorted(sources))
    # Transitional compatibility keeps focused helpers/tests usable while the
    # runtime conversion is reviewed as one coherent change.
    return (entry,)  # type: ignore[return-value]


def registry_planning_sources(
    hass: HomeAssistant, entry: MeshMonitorConfigEntry
) -> tuple[MeshMonitorSourceRuntime, ...]:
    """Return every active exact-server source for one registry planning batch."""
    planning_states = {
        ConfigEntryState.LOADED,
        ConfigEntryState.SETUP_IN_PROGRESS,
    }
    sources: list[MeshMonitorSourceRuntime] = []
    for candidate in hass.config_entries.async_entries(DOMAIN):
        if candidate is not entry and candidate.state not in planning_states:
            continue
        runtime = getattr(candidate, "runtime_data", None)
        runtime_sources = getattr(runtime, "sources", None)
        if not isinstance(runtime_sources, Mapping):
            continue
        sources.extend(runtime_sources.values())
    if not sources:
        return source_runtimes(entry)
    return tuple(
        sorted(
            sources,
            key=lambda source: (
                source.entry.runtime_data.fingerprint,
                source.source_id,
            ),
        )
    )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Keep the authenticated panel available while every source is offline."""
    del config
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get("actions_registered"):
        from .actions import async_register_actions

        async_register_actions(hass)
        domain_data["actions_registered"] = True
    if "notification_manager" not in domain_data:
        notification_manager = MeshMonitorNotificationManager(hass)
        await notification_manager.async_initialize()
        domain_data["notification_manager"] = notification_manager
    if not domain_data.get("websocket_registered"):
        async_register_websocket_commands(hass)
        domain_data["websocket_registered"] = True
    panel_wanted = any(
        server_options(entry).get(CONF_ENABLE_SIDEBAR_PANEL, True)
        for entry in hass.config_entries.async_entries(DOMAIN)
    )
    if panel_wanted and not domain_data.get("panel_registered"):
        await async_register_panel(hass)
        domain_data["panel_registered"] = True
    return True


async def async_setup_entry(hass: HomeAssistant, entry: MeshMonitorConfigEntry) -> bool:
    """Set up one exact MeshMonitor server and all stored child sources."""
    inventory = entry.data.get(CONF_SOURCES)
    if not isinstance(inventory, list) or CONF_SOURCE_ID in entry.data:
        raise ConfigEntryError(
            "Legacy source-shaped MeshMonitor entries are unsupported; remove and reinstall"
        )

    client = MeshMonitorClient(
        entry.data[CONF_URL],
        entry.data[CONF_TOKEN],
        session=async_get_clientsession(hass),
    )
    fingerprint = server_fingerprint(entry.data[CONF_URL])
    sources: dict[str, MeshMonitorSourceRuntime] = {}
    successful_sources = 0
    for item in sorted(inventory, key=lambda value: value[CONF_SOURCE_ID]):
        source_id = item[CONF_SOURCE_ID]
        source_type = item.get(CONF_SOURCE_TYPE, SOURCE_TYPE_MESHTASTIC)
        coordinator = MeshMonitorCoordinator(
            hass,
            client,
            source_id,
            source_type,
            timedelta(seconds=source_options(entry, source_id).get(CONF_SCAN_INTERVAL, 60)),
        )
        source = MeshMonitorSourceRuntime(
            entry,
            client,
            coordinator,
            source_id,
            item.get(CONF_SOURCE_NAME, ""),
            source_type,
        )
        sources[source_id] = source
        try:
            # Deliberately serialized to avoid a startup request burst.
            await coordinator.async_config_entry_first_refresh()
        except ConfigEntryNotReady:
            continue
        successful_sources += 1

    if not sources:
        raise ConfigEntryError("MeshMonitor server entry has no stored sources")
    if not successful_sources:
        raise ConfigEntryNotReady("No stored MeshMonitor source is currently available")

    entry.runtime_data = MeshMonitorRuntimeData(client, fingerprint, sources)
    _async_create_and_migrate_source_devices(hass, entry)
    from .entity_policy import async_reconcile_node_registries

    async_reconcile_node_registries(hass, entry)

    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data.setdefault("automation_coordinators", {})
    domain_data.setdefault("message_coordinators", {})
    domain_data.setdefault("server_health_coordinators", {})
    if "firmware_releases" not in domain_data:
        release_cache: dict[str, dict[str, Any]] = {}
        domain_data["firmware_releases"] = release_cache
        session = async_get_clientsession(hass)

        async def refresh_firmware_releases(*_: Any) -> None:
            await async_refresh_releases(session, release_cache)

        hass.async_create_background_task(
            refresh_firmware_releases(),
            "MeshMonitor firmware release check",
            eager_start=False,
        )
        domain_data["firmware_release_unsubscribe"] = async_track_time_interval(
            hass, refresh_firmware_releases, timedelta(hours=6), cancel_on_shutdown=True
        )
    source_connection_registry = domain_data.get("source_connection_registry")
    if source_connection_registry is None:
        source_connection_registry = MeshMonitorSourceConnectionRegistry(hass)
        domain_data["source_connection_registry"] = source_connection_registry
    if not domain_data.get("websocket_registered"):
        async_register_websocket_commands(hass)
        domain_data["websocket_registered"] = True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if hasattr(entry, "async_schedule_reload"):
        entry.async_on_unload(entry.async_schedule_reload(hass))
    else:
        entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    for source in sources.values():
        entry.async_on_unload(
            source_connection_registry.register(
                f"{entry.entry_id}:{source.source_id}",
                entry.data[CONF_URL],
                source.source_id,
                source.source_type,
                source.coordinator,
            )
        )
        if source.source_type != SOURCE_TYPE_RETICULUM:
            entry.async_on_unload(
                MeshMonitorNodeEventMonitor(
                    hass,
                    source.coordinator,
                    source.source_name,
                    source.source_type,
                ).async_initialize()
            )
    await _async_reconcile_shared_runtime(hass)
    return True


def _async_create_and_migrate_source_devices(
    hass: HomeAssistant, entry: MeshMonitorConfigEntry
) -> None:
    """Create source devices and migrate the former server/local-node hierarchy."""
    registry = dr.async_get(hass)
    entities = er.async_get(hass)
    fingerprint = entry.runtime_data.fingerprint
    for source in source_runtimes(entry):
        source_device = registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={source_device_identifier(fingerprint, source.source_id)},
            name=source.title,
            manufacturer="MeshMonitor",
            model=(
                "Reticulum source"
                if source.source_type == SOURCE_TYPE_RETICULUM
                else "MeshCore source"
                if source.source_type == SOURCE_TYPE_MESHCORE
                else "Meshtastic source"
            ),
            configuration_url=entry.data[CONF_URL],
        )
        if source_device.via_device_id is not None:
            registry.async_update_device(source_device.id, via_device_id=None)

        snapshot = source.coordinator.data
        local_node_id = getattr(getattr(snapshot, "status", None), "local_node_id", None)
        if local_node_id is None:
            continue
        from .entity_policy import is_source_node

        local_node = next(
            (node for node in source.coordinator.nodes.values() if is_source_node(source, node)),
            None,
        )
        if local_node is None:
            continue
        old_identifier = node_device_identifier(fingerprint, source.source_id, local_node.id)
        old_device = registry.async_get_device(identifiers={old_identifier})
        if old_device is None or old_device.config_entries != {entry.entry_id}:
            continue
        for entity in tuple(entities.entities.values()):
            if entity.config_entry_id == entry.entry_id and entity.device_id == old_device.id:
                entities.async_update_entity(entity.entity_id, device_id=source_device.id)
        registry.async_remove_device(old_device.id)

    server_device = registry.async_get_device(identifiers={server_device_identifier(fingerprint)})
    if server_device is not None and server_device.config_entries == {entry.entry_id}:
        registry.async_remove_device(server_device.id)


async def async_unload_entry(hass: HomeAssistant, entry: MeshMonitorConfigEntry) -> bool:
    """Unload one exact-server config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        return False
    await _async_reconcile_shared_runtime(hass, excluding_entry_id=entry.entry_id)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: MeshMonitorConfigEntry) -> None:
    """Reload an entry so operational option changes take effect cleanly."""
    await hass.config_entries.async_reload(entry.entry_id)


def _active_entries(
    hass: HomeAssistant, excluding_entry_id: str | None = None
) -> list[MeshMonitorConfigEntry]:
    """Return loaded server entries, including one currently finishing setup."""
    return [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.entry_id != excluding_entry_id
        and (
            entry.state is ConfigEntryState.LOADED
            or getattr(entry, "runtime_data", None) is not None
        )
    ]


async def _async_reconcile_shared_runtime(
    hass: HomeAssistant, excluding_entry_id: str | None = None
) -> None:
    """Reconcile UI and direct per-server shared bounded coordinators."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    message_runtimes = domain_data.setdefault("message_coordinators", {})
    automation_runtimes = domain_data.setdefault("automation_coordinators", {})
    server_health_runtimes = domain_data.setdefault("server_health_coordinators", {})
    entries = _active_entries(hass, excluding_entry_id)

    panel_wanted = any(
        server_options(entry).get(CONF_ENABLE_SIDEBAR_PANEL, True) for entry in entries
    )
    if panel_wanted and not domain_data.get("panel_registered"):
        await async_register_panel(hass)
        domain_data["panel_registered"] = True
    elif not panel_wanted and domain_data.get("panel_registered"):
        async_remove_panel(hass)
        domain_data["panel_registered"] = False

    wanted_ids = {entry.entry_id for entry in entries}
    for runtimes in (
        message_runtimes,
        automation_runtimes,
        server_health_runtimes,
    ):
        for entry_id in set(runtimes) - wanted_ids:
            runtimes.pop(entry_id)["unsubscribe"]()

    for entry in entries:
        entry_id = entry.entry_id
        source_views = source_runtimes(entry)
        existing_health = server_health_runtimes.get(entry_id)
        if (
            existing_health is None
            or existing_health.get("client") is not entry.runtime_data.client
        ):
            if existing_health is not None:
                existing_health["unsubscribe"]()
            server_health = MeshMonitorServerHealthCoordinator(
                hass, entry.runtime_data.client, entry_id
            )
            server_health_runtimes[entry_id] = {
                "client": entry.runtime_data.client,
                "coordinator": server_health,
                "unsubscribe": await server_health.async_initialize(),
            }
        message_sources = tuple(
            MessageSource(
                source.client,
                source.source_id,
                source.source_name,
                source.source_type,
                source.coordinator,
                bool(source.options.get(CONF_EXPOSE_MESSAGE_TEXT, False)),
            )
            for source in source_views
            if source.options.get(CONF_ENABLE_MESSAGE_POLLING, True)
        )
        if message_sources:
            if entry_id in message_runtimes:
                message_runtimes.pop(entry_id)["unsubscribe"]()
            seconds = server_options(entry).get(CONF_MESSAGE_SCAN_INTERVAL, 30)
            message_coordinator = MeshMonitorMessageCoordinator(
                hass,
                message_sources,
                entry.data[CONF_URL],
                timedelta(seconds=seconds),
            )
            message_runtimes[entry_id] = {
                "coordinator": message_coordinator,
                "unsubscribe": await message_coordinator.async_initialize(),
            }
        elif entry_id in message_runtimes:
            message_runtimes.pop(entry_id)["unsubscribe"]()

        automation_enabled = server_options(entry).get(CONF_ENABLE_AUTOMATION_VISIBILITY, False)
        if automation_enabled:
            existing = automation_runtimes.get(entry_id)
            if existing is None or existing.get("client") is not entry.runtime_data.client:
                if existing is not None:
                    existing["unsubscribe"]()
                automation_coordinator = MeshMonitorAutomationCoordinator(
                    hass, entry.runtime_data.client, entry.data[CONF_URL]
                )
                automation_runtimes[entry_id] = {
                    "client": entry.runtime_data.client,
                    "coordinator": automation_coordinator,
                    "unsubscribe": await automation_coordinator.async_initialize(),
                }
        elif entry_id in automation_runtimes:
            automation_runtimes.pop(entry_id)["unsubscribe"]()
