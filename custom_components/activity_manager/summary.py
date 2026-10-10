"""Aggregate ("summary") entities for Activity Manager.

Each config entry (list) gets a device with summary entities for the whole list
and for every category found in it. Categories are discovered from the data, so
entities appear and disappear as activities are added, edited or removed.

Definitions (shared by the sensors, the binary sensors and their tests):

* An activity is *overdue* when its due datetime is now or in the past.
* An activity is *due* when it is overdue or comes due within the list's
  "due soon" window (an option, 24 hours by default). So ``due >= overdue``.
* *Next due* is the earliest due datetime of any activity in scope. It is in the
  past while something is overdue.

These entities deliberately do NOT carry the ``integration`` state attribute that
the per-activity sensors have: the notification blueprint, user templates and the
card editor select on it and expect a datetime state.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import ATTR_CATEGORY, ATTR_FREQUENCY_MS, ATTR_LAST_COMPLETED, ATTR_NAME, DOMAIN
from .coordinator import ActivityManagerCoordinator

UNIQUE_ID_INFIX = "summary"
SCOPE_LIST = "list"
SCOPE_CATEGORY_PREFIX = "cat_"


def due_datetime(item: dict[str, Any], now: datetime) -> datetime:
    """Return when an activity is next due; an activity never completed is due now."""
    last_completed = dt_util.parse_datetime(item.get(ATTR_LAST_COMPLETED) or "")
    if last_completed is None:
        return now
    return dt_util.as_local(last_completed) + timedelta(
        milliseconds=item.get(ATTR_FREQUENCY_MS) or 0
    )


def category_key(category: str | None) -> str:
    """Return the stable key categories are grouped by (case/punctuation-insensitive)."""
    return slugify(category or "")


def categories_in(items: list[dict[str, Any]]) -> dict[str, str]:
    """Map category key -> display name (first seen), skipping uncategorised items."""
    found: dict[str, str] = {}
    for item in items:
        key = category_key(item.get(ATTR_CATEGORY))
        if key and key not in found:
            found[key] = item[ATTR_CATEGORY]
    return found


@dataclass(frozen=True)
class Summary:
    """Aggregate figures for a set of activities."""

    due_count: int
    overdue_count: int
    next_due: datetime | None
    next_due_name: str | None
    due: list[str]
    overdue: list[str]


def compute_summary(
    items: list[dict[str, Any]],
    now: datetime,
    due_soon: timedelta,
    key: str | None = None,
) -> Summary:
    """Summarise ``items`` (restricted to category ``key`` when given)."""
    rows = [
        (due_datetime(item, now), item.get(ATTR_NAME) or "")
        for item in items
        if key is None or category_key(item.get(ATTR_CATEGORY)) == key
    ]
    rows.sort(key=lambda row: (row[0], row[1].lower()))
    overdue = [name for due, name in rows if due <= now]
    due = [name for due_at, name in rows if due_at <= now + due_soon]
    return Summary(
        due_count=len(due),
        overdue_count=len(overdue),
        next_due=rows[0][0] if rows else None,
        next_due_name=rows[0][1] if rows else None,
        due=due,
        overdue=overdue,
    )


class SummaryEntity(CoordinatorEntity[ActivityManagerCoordinator]):
    """Base class: one metric for the whole list or for one category."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ActivityManagerCoordinator,
        metric: str,
        cat_key: str | None = None,
        cat_name: str | None = None,
    ) -> None:
        """Initialize; ``cat_key`` None means the whole list."""
        super().__init__(coordinator)
        self._metric = metric
        self._cat_key = cat_key
        self._cat_name = cat_name
        scope = SCOPE_LIST if cat_key is None else f"{SCOPE_CATEGORY_PREFIX}{cat_key}"
        self._attr_unique_id = unique_id(coordinator.entry_id, scope, metric)
        self._attr_translation_key = metric if cat_key is None else f"category_{metric}"
        if cat_key is not None:
            self._attr_translation_placeholders = {"category": cat_name or cat_key}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry_id)},
            name=coordinator.title,
            manufacturer="Activity Manager",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def summary(self) -> Summary:
        """Return the live summary for this entity's scope."""
        return compute_summary(
            self.coordinator.data or [],
            dt_util.now(),
            self.coordinator.due_soon,
            self._cat_key,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return attributes common to every summary entity."""
        return {
            "entry_id": self.coordinator.entry_id,
            "list_title": self.coordinator.title,
            "category": self._cat_name,
        }


def unique_id(entry_id: str, scope: str, metric: str) -> str:
    """Build a stable unique id; never collides with ``<entry_id>_<activity_id>``."""
    return f"{entry_id}_{UNIQUE_ID_INFIX}_{scope}_{metric}"


@callback
def async_setup_summary_platform(
    entry: ConfigEntry,
    coordinator: ActivityManagerCoordinator,
    async_add_entities: AddEntitiesCallback,
    platform_domain: str,
    build: Callable[[str | None, str | None], list[Entity]],
    metrics: tuple[str, ...],
) -> None:
    """Add list-level entities, then keep per-category entities in sync with the data.

    ``build(None, None)`` returns the list-level entities, ``build(key, name)`` the
    entities for one category. Entities for categories that no longer have any
    activity are removed from the registry, mirroring how removed activities are
    handled.
    """
    hass = coordinator.hass
    registry = er.async_get(hass)
    prefix = f"{entry.entry_id}_{UNIQUE_ID_INFIX}_{SCOPE_CATEGORY_PREFIX}"
    known: set[str] = set()

    @callback
    def _sync() -> None:
        current = categories_in(coordinator.data or [])
        new = [key for key in current if key not in known]
        if new:
            async_add_entities(
                [entity for key in new for entity in build(key, current[key])]
            )
            known.update(new)
        for key in known - current.keys():
            for metric in metrics:
                entity_id = registry.async_get_entity_id(
                    platform_domain,
                    DOMAIN,
                    unique_id(entry.entry_id, f"{SCOPE_CATEGORY_PREFIX}{key}", metric),
                )
                if entity_id:
                    registry.async_remove(entity_id)
            known.discard(key)

    # Drop registry entries left behind for categories that vanished while HA was down.
    live = categories_in(coordinator.data or [])
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg_entry.domain != platform_domain or not reg_entry.unique_id.startswith(prefix):
            continue
        rest = reg_entry.unique_id[len(prefix):]
        key = next((rest[: -len(m) - 1] for m in metrics if rest.endswith(f"_{m}")), None)
        if key is not None and key not in live:
            registry.async_remove(reg_entry.entity_id)

    async_add_entities(build(None, None))
    _sync()
    entry.async_on_unload(coordinator.async_add_listener(_sync))
