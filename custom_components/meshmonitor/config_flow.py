"""Config flow for MeshMonitor."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_TOKEN, CONF_URL
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_AUTOMATED_TX_UTILIZATION_LIMIT,
    CONF_ENABLE_AUTOMATION_VISIBILITY,
    CONF_ENABLE_DEVICE_TRACKERS,
    CONF_ENABLE_FAVORITES,
    CONF_ENABLE_MESSAGE_POLLING,
    CONF_ENABLE_NODE_MANAGEMENT,
    CONF_ENABLE_SIDEBAR_PANEL,
    CONF_ENABLE_TRANSMIT,
    CONF_EXPOSE_MESSAGE_TEXT,
    CONF_MESSAGE_SCAN_INTERVAL,
    CONF_NODE_DEVICE_POLICY,
    CONF_SCAN_INTERVAL,
    CONF_SERVER_OPTIONS,
    CONF_SOURCE_ID,
    CONF_SOURCE_NAME,
    CONF_SOURCE_OPTIONS,
    CONF_SOURCE_TYPE,
    CONF_SOURCES,
    DEFAULT_NODE_DEVICE_POLICY,
    DOMAIN,
    NODE_DEVICE_POLICY_ALL,
    NODE_DEVICE_POLICY_FAVORITES,
    NODE_DEVICE_POLICY_SOURCES,
    SOURCE_TYPE_MESHCORE,
    SOURCE_TYPE_MESHTASTIC,
    SOURCE_TYPE_RETICULUM,
)
from .registry import server_fingerprint
from .vendor_meshmonitor_client import (
    MeshMonitorAuthenticationError,
    MeshMonitorClient,
    MeshMonitorConnectionError,
    MeshMonitorError,
    MeshMonitorPermissionError,
    Source,
)

_MAX_SOURCES = 64
_MAX_SOURCE_ID_LENGTH = 256
_MAX_SOURCE_NAME_LENGTH = 256
_CONF_CONFIRM_REGISTRY_CLEANUP = "confirm_registry_cleanup"
_POLICY_RANK = {
    NODE_DEVICE_POLICY_SOURCES: 0,
    NODE_DEVICE_POLICY_FAVORITES: 1,
    NODE_DEVICE_POLICY_ALL: 2,
}

_SERVER_DEFAULTS: dict[str, Any] = {
    CONF_ENABLE_SIDEBAR_PANEL: True,
    CONF_ENABLE_AUTOMATION_VISIBILITY: False,
    CONF_MESSAGE_SCAN_INTERVAL: 30,
    CONF_NODE_DEVICE_POLICY: DEFAULT_NODE_DEVICE_POLICY,
}

_SOURCE_DEFAULTS: dict[str, Any] = {
    CONF_SCAN_INTERVAL: 60,
    CONF_ENABLE_DEVICE_TRACKERS: True,
    CONF_ENABLE_MESSAGE_POLLING: True,
    CONF_EXPOSE_MESSAGE_TEXT: False,
    CONF_ENABLE_FAVORITES: False,
    CONF_ENABLE_TRANSMIT: False,
    CONF_ENABLE_NODE_MANAGEMENT: False,
    CONF_AUTOMATED_TX_UTILIZATION_LIMIT: 0,
}


class MeshMonitorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a MeshMonitor config flow."""

    VERSION = 2

    def __init__(self) -> None:
        self._reauth_entry: config_entries.ConfigEntry | None = None

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Atomically update one exact server and its validated inventory."""
        entry = self._get_reconfigure_entry()
        if _is_legacy_entry(entry.data):
            return self.async_abort(reason="legacy_entry_unsupported")
        errors: dict[str, str] = {}
        if user_input is not None:
            token = str(user_input.get(CONF_TOKEN, "")).strip() or entry.data[CONF_TOKEN]
            try:
                url = _normalize_url(str(user_input[CONF_URL]))
                async with MeshMonitorClient(
                    url, token, session=async_get_clientsession(self.hass)
                ) as client:
                    inventory = await _async_validated_inventory(client)
            except ValueError:
                errors["base"] = "invalid_url"
            except _NoSupportedSourcesError:
                errors["base"] = "no_supported_sources"
            except _NodeVisibilityError:
                errors["base"] = "node_visibility_required"
            except MeshMonitorAuthenticationError:
                errors["base"] = "invalid_auth"
            except MeshMonitorPermissionError:
                errors["base"] = "insufficient_permissions"
            except MeshMonitorConnectionError:
                errors["base"] = "cannot_connect"
            except MeshMonitorError:
                errors["base"] = "unknown"
            if not errors:
                _merged, replacements = _reconcile_inventory(
                    _entry_inventory(entry.data), inventory
                )
                migrated_options = _migrate_source_options(entry.options, replacements)
                if migrated_options != entry.options:
                    self.hass.config_entries.async_update_entry(entry, options=migrated_options)
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=server_fingerprint(url),
                    data_updates={
                        CONF_URL: url,
                        CONF_TOKEN: token,
                        CONF_SOURCES: inventory,
                    },
                    title=_server_title(url),
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL, default=entry.data[CONF_URL]): str,
                    vol.Optional(CONF_TOKEN): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the server/source integration options flow."""
        del config_entry
        return MeshMonitorOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Collect and validate the MeshMonitor connection."""
        errors: dict[str, str] = {}
        if user_input is not None:
            token = str(user_input[CONF_TOKEN])
            try:
                url = _normalize_url(str(user_input[CONF_URL]))
                async with MeshMonitorClient(
                    url,
                    token,
                    session=async_get_clientsession(self.hass),
                ) as client:
                    inventory = await _async_validated_inventory(client)
            except ValueError:
                errors["base"] = "invalid_url"
            except _NoSupportedSourcesError:
                errors["base"] = "no_supported_sources"
            except _NodeVisibilityError:
                errors["base"] = "node_visibility_required"
            except MeshMonitorAuthenticationError:
                errors["base"] = "invalid_auth"
            except MeshMonitorPermissionError:
                errors["base"] = "insufficient_permissions"
            except MeshMonitorConnectionError:
                errors["base"] = "cannot_connect"
            except MeshMonitorError:
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(server_fingerprint(url))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=_server_title(url),
                    data={
                        CONF_URL: url,
                        CONF_TOKEN: token,
                        CONF_SOURCES: inventory,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_URL, default="http://"): str,
                vol.Required(CONF_TOKEN): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> config_entries.ConfigFlowResult:
        """Start reauthentication after MeshMonitor rejects a token."""
        del entry_data
        self._reauth_entry = self._get_reauth_entry()
        if _is_legacy_entry(self._reauth_entry.data):
            return self.async_abort(reason="legacy_entry_unsupported")
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Validate and store a replacement read-only token."""
        assert self._reauth_entry is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            token = str(user_input[CONF_TOKEN])
            try:
                async with MeshMonitorClient(
                    self._reauth_entry.data[CONF_URL],
                    token,
                    session=async_get_clientsession(self.hass),
                ) as client:
                    await _async_validated_inventory(client)
            except MeshMonitorAuthenticationError:
                errors["base"] = "invalid_auth"
            except _NoSupportedSourcesError:
                errors["base"] = "no_supported_sources"
            except _NodeVisibilityError:
                errors["base"] = "node_visibility_required"
            except MeshMonitorPermissionError:
                errors["base"] = "insufficient_permissions"
            except MeshMonitorConnectionError:
                errors["base"] = "cannot_connect"
            except MeshMonitorError:
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    self._reauth_entry,
                    data_updates={CONF_TOKEN: token},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}),
            errors=errors,
        )


def _source_type(source: Source) -> str | None:
    """Map MeshMonitor's concrete source type to an integration adapter."""
    raw_type = (source.type or "").lower()
    if "meshcore" in raw_type:
        return SOURCE_TYPE_MESHCORE
    if "meshtastic" in raw_type:
        return SOURCE_TYPE_MESHTASTIC
    if "reticulum" in raw_type:
        return SOURCE_TYPE_RETICULUM
    return None


async def _async_validated_inventory(client: MeshMonitorClient) -> list[dict[str, str]]:
    """Read and validate a bounded, stable inventory of every supported source."""
    sources = [source for source in await client.get_sources() if _source_type(source)]
    if not sources:
        raise _NoSupportedSourcesError
    if len(sources) > _MAX_SOURCES:
        raise MeshMonitorError("source inventory exceeds integration bound")
    if len({source.id for source in sources}) != len(sources):
        raise MeshMonitorError("source inventory contains duplicate identifiers")

    inventory: list[dict[str, str]] = []
    for source in sorted(sources, key=lambda item: item.id):
        source_id = source.id
        source_name = (source.name or "").strip()
        source_type = _source_type(source)
        assert source_type is not None
        if (
            not source_id
            or source_id != source_id.strip()
            or len(source_id) > _MAX_SOURCE_ID_LENGTH
            or len(source_name) > _MAX_SOURCE_NAME_LENGTH
        ):
            raise MeshMonitorError("source inventory contains invalid metadata")
        if source_type == SOURCE_TYPE_RETICULUM:
            await client.get_reticulum_status(source_id)
        elif source_type == SOURCE_TYPE_MESHCORE:
            await client.get_meshcore_status(source_id)
            nodes = await client.get_meshcore_nodes(source_id)
            if not nodes:
                raise _NodeVisibilityError
        else:
            capabilities = await client.probe_capabilities(source_id)
            if not capabilities.nodes:
                raise MeshMonitorPermissionError("node visibility is not permitted")
            if capabilities.node_visibility_suspect:
                raise _NodeVisibilityError
        inventory.append(
            {
                CONF_SOURCE_ID: source_id,
                CONF_SOURCE_NAME: source_name,
                CONF_SOURCE_TYPE: source_type,
            }
        )
    return inventory


class _NodeVisibilityError(MeshMonitorError):
    """A source is readable but has no permitted visible nodes."""


class _NoSupportedSourcesError(MeshMonitorError):
    """The bounded catalog contains no source supported by the integration."""


def _normalize_url(raw_url: str) -> str:
    """Normalize an exact HTTP(S) server address without weakening identity."""
    if len(raw_url) > 2048 or raw_url != raw_url.strip():
        raise ValueError("invalid URL")
    parsed = urlsplit(raw_url)
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("invalid URL")
    try:
        port = parsed.port
    except ValueError as err:
        raise ValueError("invalid port") from err
    host = parsed.hostname.lower()
    if any(character.isspace() for character in host):
        raise ValueError("invalid host")
    if ":" in host:
        host = f"[{host}]"
    default_port = 80 if parsed.scheme.lower() == "http" else 443
    netloc = host if port in (None, default_port) else f"{host}:{port}"
    path = parsed.path.rstrip("/")
    return urlunsplit(SplitResult(parsed.scheme.lower(), netloc, path, "", ""))


def _server_title(normalized_url: str) -> str:
    parsed = urlsplit(normalized_url)
    host = parsed.hostname or "MeshMonitor"
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"{host}{port}{parsed.path}"


def _is_legacy_entry(data: Mapping[str, Any]) -> bool:
    """Identify the intentionally unsupported pre-v1 source-entry shape."""
    return CONF_SOURCES not in data or CONF_SOURCE_ID in data


class MeshMonitorOptionsFlow(config_entries.OptionsFlow):
    """Configure exact-server settings and isolated per-source settings."""

    def __init__(self) -> None:
        self._selected_source_id: str | None = None
        self._refreshed_inventory: list[dict[str, str]] | None = None
        self._pending_server_settings: dict[str, Any] | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        del user_input
        if _is_legacy_entry(self.config_entry.data):
            return self.async_abort(reason="legacy_entry_unsupported")
        return self.async_show_menu(
            step_id="init",
            menu_options=["server_settings", "source_select", "refresh_source_inventory"],
        )

    async def async_step_server_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Edit controls that are owned once by the exact server."""
        current = _option_section(self.config_entry.options, CONF_SERVER_OPTIONS)
        if user_input is not None:
            current_policy = current.get(
                CONF_NODE_DEVICE_POLICY, _SERVER_DEFAULTS[CONF_NODE_DEVICE_POLICY]
            )
            next_policy = user_input[CONF_NODE_DEVICE_POLICY]
            if _POLICY_RANK[next_policy] < _POLICY_RANK[current_policy]:
                self._pending_server_settings = dict(user_input)
                return await self.async_step_confirm_registry_cleanup()
            return self._save_section(CONF_SERVER_OPTIONS, user_input)
        return self.async_show_form(
            step_id="server_settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ENABLE_SIDEBAR_PANEL,
                        default=current.get(
                            CONF_ENABLE_SIDEBAR_PANEL,
                            _SERVER_DEFAULTS[CONF_ENABLE_SIDEBAR_PANEL],
                        ),
                    ): bool,
                    vol.Required(
                        CONF_ENABLE_AUTOMATION_VISIBILITY,
                        default=current.get(
                            CONF_ENABLE_AUTOMATION_VISIBILITY,
                            _SERVER_DEFAULTS[CONF_ENABLE_AUTOMATION_VISIBILITY],
                        ),
                    ): bool,
                    vol.Required(
                        CONF_NODE_DEVICE_POLICY,
                        default=current.get(
                            CONF_NODE_DEVICE_POLICY,
                            _SERVER_DEFAULTS[CONF_NODE_DEVICE_POLICY],
                        ),
                    ): vol.In(
                        {
                            NODE_DEVICE_POLICY_SOURCES: "Source nodes only",
                            NODE_DEVICE_POLICY_FAVORITES: (
                                "Source nodes + favorites (recommended)"
                            ),
                            NODE_DEVICE_POLICY_ALL: "All discovered nodes",
                        }
                    ),
                    vol.Required(
                        CONF_MESSAGE_SCAN_INTERVAL,
                        default=current.get(
                            CONF_MESSAGE_SCAN_INTERVAL,
                            _SERVER_DEFAULTS[CONF_MESSAGE_SCAN_INTERVAL],
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=15, max=900)),
                }
            ),
        )

    async def async_step_confirm_registry_cleanup(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Preview and confirm removal of now-ineligible HA registry objects."""
        assert self._pending_server_settings is not None
        from .entity_policy import registry_reconciliation_plan

        policy = self._pending_server_settings[CONF_NODE_DEVICE_POLICY]
        plan = registry_reconciliation_plan(self.hass, self.config_entry, policy)
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get(_CONF_CONFIRM_REGISTRY_CLEANUP):
                return self._save_section(CONF_SERVER_OPTIONS, self._pending_server_settings)
            errors["base"] = "registry_cleanup_confirmation_required"
        return self.async_show_form(
            step_id="confirm_registry_cleanup",
            data_schema=vol.Schema(
                {vol.Required(_CONF_CONFIRM_REGISTRY_CLEANUP, default=False): bool}
            ),
            errors=errors,
            description_placeholders={
                "devices": str(len(plan.device_ids)),
                "entities": str(len(plan.entity_ids)),
            },
        )

    async def async_step_source_select(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Select one stored source before editing source-scoped controls."""
        inventory = _entry_inventory(self.config_entry.data)
        if user_input is not None:
            self._selected_source_id = str(user_input[CONF_SOURCE_ID])
            return await self.async_step_source_settings()
        choices = {
            item[CONF_SOURCE_ID]: (
                f"{item[CONF_SOURCE_NAME] or item[CONF_SOURCE_ID]} ({item[CONF_SOURCE_TYPE]})"
            )
            for item in inventory
        }
        return self.async_show_form(
            step_id="source_select",
            data_schema=vol.Schema({vol.Required(CONF_SOURCE_ID): vol.In(choices)}),
        )

    async def async_step_source_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Edit controls whose effects are confined to one stored source."""
        assert self._selected_source_id is not None
        source_options = _option_section(self.config_entry.options, CONF_SOURCE_OPTIONS)
        current = _option_section(source_options, self._selected_source_id)
        if user_input is not None:
            updated_sources = dict(source_options)
            updated_sources[self._selected_source_id] = dict(user_input)
            return self._save_section(CONF_SOURCE_OPTIONS, updated_sources)
        return self.async_show_form(
            step_id="source_settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=current.get(
                            CONF_SCAN_INTERVAL, _SOURCE_DEFAULTS[CONF_SCAN_INTERVAL]
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=30, max=3600)),
                    vol.Required(
                        CONF_ENABLE_MESSAGE_POLLING,
                        default=current.get(
                            CONF_ENABLE_MESSAGE_POLLING,
                            _SOURCE_DEFAULTS[CONF_ENABLE_MESSAGE_POLLING],
                        ),
                    ): bool,
                    vol.Required(
                        CONF_ENABLE_DEVICE_TRACKERS,
                        default=current.get(
                            CONF_ENABLE_DEVICE_TRACKERS,
                            _SOURCE_DEFAULTS[CONF_ENABLE_DEVICE_TRACKERS],
                        ),
                    ): bool,
                    vol.Required(
                        CONF_EXPOSE_MESSAGE_TEXT,
                        default=current.get(
                            CONF_EXPOSE_MESSAGE_TEXT,
                            _SOURCE_DEFAULTS[CONF_EXPOSE_MESSAGE_TEXT],
                        ),
                    ): bool,
                    vol.Required(
                        CONF_ENABLE_FAVORITES,
                        default=current.get(
                            CONF_ENABLE_FAVORITES,
                            _SOURCE_DEFAULTS[CONF_ENABLE_FAVORITES],
                        ),
                    ): bool,
                    vol.Required(
                        CONF_ENABLE_TRANSMIT,
                        default=current.get(
                            CONF_ENABLE_TRANSMIT,
                            _SOURCE_DEFAULTS[CONF_ENABLE_TRANSMIT],
                        ),
                    ): bool,
                    vol.Required(
                        CONF_ENABLE_NODE_MANAGEMENT,
                        default=current.get(
                            CONF_ENABLE_NODE_MANAGEMENT,
                            _SOURCE_DEFAULTS[CONF_ENABLE_NODE_MANAGEMENT],
                        ),
                    ): bool,
                    vol.Required(
                        CONF_AUTOMATED_TX_UTILIZATION_LIMIT,
                        default=current.get(
                            CONF_AUTOMATED_TX_UTILIZATION_LIMIT,
                            _SOURCE_DEFAULTS[CONF_AUTOMATED_TX_UTILIZATION_LIMIT],
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
                }
            ),
        )

    async def async_step_refresh_source_inventory(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Read once, preview, then confirm a non-destructive inventory merge."""
        errors: dict[str, str] = {}
        if self._refreshed_inventory is None:
            try:
                async with MeshMonitorClient(
                    self.config_entry.data[CONF_URL],
                    self.config_entry.data[CONF_TOKEN],
                    session=async_get_clientsession(self.hass),
                ) as client:
                    self._refreshed_inventory = await _async_validated_inventory(client)
            except MeshMonitorAuthenticationError:
                errors["base"] = "invalid_auth"
            except _NoSupportedSourcesError:
                errors["base"] = "no_supported_sources"
            except MeshMonitorPermissionError:
                errors["base"] = "insufficient_permissions"
            except _NodeVisibilityError:
                errors["base"] = "node_visibility_required"
            except MeshMonitorConnectionError:
                errors["base"] = "cannot_connect"
            except MeshMonitorError:
                errors["base"] = "unknown"
            if errors:
                return self.async_show_form(
                    step_id="refresh_source_inventory",
                    data_schema=vol.Schema({}),
                    errors=errors,
                )

        assert self._refreshed_inventory is not None
        existing = _entry_inventory(self.config_entry.data)
        merged, replacements = _reconcile_inventory(existing, self._refreshed_inventory)
        if user_input is not None:
            migrated_options = _migrate_source_options(self.config_entry.options, replacements)
            _migrate_registry_source_ids(self.hass, self.config_entry.entry_id, replacements)
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={**self.config_entry.data, CONF_SOURCES: merged},
                options=migrated_options,
            )
            return self.async_create_entry(title="", data=migrated_options)
        existing_ids = {item[CONF_SOURCE_ID] for item in existing}
        refreshed_ids = {item[CONF_SOURCE_ID] for item in self._refreshed_inventory}
        replaced_old_ids = set(replacements)
        replaced_new_ids = set(replacements.values())
        return self.async_show_form(
            step_id="refresh_source_inventory",
            data_schema=vol.Schema({}),
            description_placeholders={
                "added": str(len(refreshed_ids - existing_ids - replaced_new_ids)),
                "replaced": str(len(replacements)),
                "retained": str(len(existing_ids - refreshed_ids - replaced_old_ids)),
                "total": str(len(merged)),
            },
        )

    def _save_section(
        self, section: str, value: Mapping[str, Any]
    ) -> config_entries.ConfigFlowResult:
        options = dict(self.config_entry.options)
        options[section] = dict(value)
        return self.async_create_entry(title="", data=options)


def _entry_inventory(data: Mapping[str, Any]) -> list[dict[str, str]]:
    value = data.get(CONF_SOURCES)
    if not isinstance(value, list):
        raise ValueError("server entry has no source inventory")
    return [dict(item) for item in value]


def _option_section(options: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = options.get(key, {})
    return dict(value) if isinstance(value, Mapping) else {}


def _source_replacement_key(item: Mapping[str, Any]) -> tuple[str, str]:
    """Return conservative human identity used to recognize recreated sources."""
    return (
        str(item.get(CONF_SOURCE_NAME, "")).strip().casefold(),
        str(item.get(CONF_SOURCE_TYPE, "")).strip().casefold(),
    )


def _reconcile_inventory(
    existing: list[dict[str, str]], refreshed: list[dict[str, str]]
) -> tuple[list[dict[str, str]], dict[str, str]]:
    """Merge inventory and retire unique same-name/type recreated sources."""
    existing_ids = {item[CONF_SOURCE_ID] for item in existing}
    refreshed_ids = {item[CONF_SOURCE_ID] for item in refreshed}
    missing = [item for item in existing if item[CONF_SOURCE_ID] not in refreshed_ids]
    added = [item for item in refreshed if item[CONF_SOURCE_ID] not in existing_ids]

    missing_by_key: dict[tuple[str, str], list[dict[str, str]]] = {}
    added_by_key: dict[tuple[str, str], list[dict[str, str]]] = {}
    for item in missing:
        key = _source_replacement_key(item)
        if all(key):
            missing_by_key.setdefault(key, []).append(item)
    for item in added:
        key = _source_replacement_key(item)
        if all(key):
            added_by_key.setdefault(key, []).append(item)

    replacements = {
        old_items[0][CONF_SOURCE_ID]: added_by_key[key][0][CONF_SOURCE_ID]
        for key, old_items in missing_by_key.items()
        if len(old_items) == 1 and len(added_by_key.get(key, [])) == 1
    }
    by_id = {
        item[CONF_SOURCE_ID]: item for item in existing if item[CONF_SOURCE_ID] not in replacements
    }
    by_id.update({item[CONF_SOURCE_ID]: item for item in refreshed})
    return [by_id[source_id] for source_id in sorted(by_id)], replacements


def _migrate_source_options(
    options: Mapping[str, Any], replacements: Mapping[str, str]
) -> dict[str, Any]:
    """Move source-scoped options to recreated IDs without changing values."""
    migrated = dict(options)
    source_options = _option_section(options, CONF_SOURCE_OPTIONS)
    for old_id, new_id in replacements.items():
        if old_id in source_options and new_id not in source_options:
            source_options[new_id] = source_options[old_id]
        source_options.pop(old_id, None)
    if replacements or CONF_SOURCE_OPTIONS in options:
        migrated[CONF_SOURCE_OPTIONS] = source_options
    return migrated


def _replace_source_id_segment(value: str, old_id: str, new_id: str) -> str:
    """Replace one exact colon-delimited source-ID segment."""
    return ":".join(new_id if part == old_id else part for part in value.split(":"))


def _migrate_registry_source_ids(hass: Any, entry_id: str, replacements: Mapping[str, str]) -> None:
    """Preserve device/entity identities when a source is recreated."""
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    entry_entities = er.async_entries_for_config_entry(entity_registry, entry_id)
    entry_devices = dr.async_entries_for_config_entry(device_registry, entry_id)

    for old_id, new_id in replacements.items():
        entity_updates = [
            (
                item,
                _replace_source_id_segment(item.unique_id, old_id, new_id),
            )
            for item in entry_entities
            if old_id in item.unique_id.split(":")
        ]
        device_updates = [
            (
                item,
                {
                    (domain, _replace_source_id_segment(identifier, old_id, new_id))
                    for domain, identifier in item.identifiers
                },
            )
            for item in entry_devices
            if any(old_id in identifier.split(":") for _, identifier in item.identifiers)
        ]

        entity_collision = any(
            entity_registry.async_get_entity_id(item.domain, DOMAIN, new_unique_id)
            not in (None, item.entity_id)
            for item, new_unique_id in entity_updates
        )
        device_collision = any(
            (collision := device_registry.async_get_device(identifiers=new_identifiers)) is not None
            and collision.id != item.id
            for item, new_identifiers in device_updates
        )
        if entity_collision or device_collision:
            continue

        for device_entry, new_identifiers in device_updates:
            device_registry.async_update_device(
                device_entry.id, new_identifiers=new_identifiers
            )
        for entity_entry, new_unique_id in entity_updates:
            entity_registry.async_update_entity(
                entity_entry.entity_id, new_unique_id=new_unique_id
            )
