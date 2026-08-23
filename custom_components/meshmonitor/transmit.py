"""Process-wide radio transmit rate and replay safeguards."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import monotonic

from homeassistant.core import HomeAssistant

from .const import CONF_AUTOMATED_TX_UTILIZATION_LIMIT, DOMAIN


@dataclass(frozen=True, slots=True)
class TransmitGuardError(Exception):
    """Describe a blocked transmit without leaking request content."""

    code: str
    message: str


def ensure_automated_airtime(source: object, context: object | None) -> None:
    """Block HA-owned automated writes above the configured source ceiling."""
    if getattr(context, "user_id", None) is not None:
        return
    options = getattr(source, "options", {})
    limit = int(options.get(CONF_AUTOMATED_TX_UTILIZATION_LIMIT, 0) or 0)
    if limit <= 0:
        return
    data = getattr(getattr(source, "coordinator", None), "data", None)
    utilization = getattr(getattr(data, "status", None), "channel_utilization", None)
    if utilization is None:
        return
    if float(utilization) >= limit:
        raise TransmitGuardError(
            "airtime_limited",
            f"Automated transmission paused at {float(utilization):g}% channel utilization",
        )


def reserve_message_send(hass: HomeAssistant, replay_key: str) -> None:
    """Reserve one message send under the shared panel/automation limits."""
    state = hass.data.setdefault(DOMAIN, {}).setdefault(
        "send_state", {"times": deque(), "nonces": {}}
    )
    now = monotonic()
    times: deque[float] = state["times"]
    nonces: dict[str, float] = state["nonces"]
    while times and now - times[0] > 60:
        times.popleft()
    _expire_replay_keys(nonces, now)
    if replay_key in nonces:
        raise TransmitGuardError("duplicate", "Duplicate send request blocked")
    if len(times) >= 3:
        raise TransmitGuardError("rate_limited", "Maximum 3 messages per minute")
    nonces[replay_key] = now
    times.append(now)


def reserve_advert_send(hass: HomeAssistant, replay_key: str) -> None:
    """Reserve one MeshCore advert under the shared panel/automation limits."""
    state = hass.data.setdefault(DOMAIN, {}).setdefault(
        "advert_state", {"last_at": 0.0, "nonces": {}}
    )
    now = monotonic()
    nonces: dict[str, float] = state["nonces"]
    _expire_replay_keys(nonces, now)
    if replay_key in nonces:
        raise TransmitGuardError("duplicate", "Duplicate advert request blocked")
    if now - float(state["last_at"]) < 300:
        raise TransmitGuardError(
            "rate_limited", "Maximum one advert every five minutes"
        )
    nonces[replay_key] = now
    state["last_at"] = now


def _expire_replay_keys(nonces: dict[str, float], now: float) -> None:
    """Keep replay state bounded to the five-minute ambiguity window."""
    for nonce, timestamp in list(nonces.items()):
        if now - timestamp > 300:
            del nonces[nonce]
