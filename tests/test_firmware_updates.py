"""Tests for cached radio-firmware release presentation."""

from custom_components.meshmonitor.const import SOURCE_TYPE_MESHCORE
from custom_components.meshmonitor.firmware_updates import (
    update_presentation,
    version_numbers,
)


def test_version_numbers_accepts_prefixed_release_labels() -> None:
    assert version_numbers("v1.9.4") == (1, 9, 4)
    assert version_numbers("MeshCore 1.9.4 stable") == (1, 9, 4)
    assert version_numbers("unknown") == ()


def test_update_presentation_keeps_missing_data_unknown() -> None:
    assert update_presentation(SOURCE_TYPE_MESHCORE, "1.9.3", {}) == {
        "state": "unknown",
        "latest_version": None,
        "release_url": None,
    }


def test_update_presentation_exposes_available_version() -> None:
    assert update_presentation(
        SOURCE_TYPE_MESHCORE,
        "1.9.3",
        {
            SOURCE_TYPE_MESHCORE: {
                "version": "v1.9.4",
                "url": "https://example.invalid/v1.9.4",
            }
        },
    ) == {
        "state": "available",
        "latest_version": "v1.9.4",
        "release_url": "https://example.invalid/v1.9.4",
    }
