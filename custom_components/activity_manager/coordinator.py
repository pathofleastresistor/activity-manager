"""DataUpdateCoordinator for Activity Manager."""
from __future__ import annotations

import logging
import os
import uuid
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers.json import save_json
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from homeassistant.util.json import load_json_array

from .const import (
    ATTR_CATEGORY,
    ATTR_FREQUENCY,
    ATTR_FREQUENCY_MS,
    ATTR_ICON,
    ATTR_ID,
    ATTR_LAST_COMPLETED,
    ATTR_NAME,
    DEFAULT_ICON,
    DOMAIN,
    EVENT_UPDATED,
    PERSISTENCE,
)
from .utils import duration_to_ms

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


class ActivityManagerCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Coordinator that owns all activity data and persistence.

    No update_interval — data is file-based. All updates are push-only via
    async_set_updated_data(), which automatically notifies all CoordinatorEntity
    subscribers.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
        )
        self._entry = entry
        self.entry_id: str = entry.entry_id
        self.title: str = entry.title

        # Per-entry persistence file. Falls back to legacy file on first load
        # so existing data migrates automatically.
        self._persistence = f".activities_list_{entry.entry_id}.json"
        self._legacy_persistence = PERSISTENCE

        # Set by sensor.async_setup_entry so we can add new entities dynamically.
        self.async_add_entities: AddEntitiesCallback | None = None

    async def async_load(self) -> None:
        """Load activities from disk and push to all listeners."""
        items = await self.hass.async_add_executor_job(self._load_sync)
        self.async_set_updated_data(items)

    def _load_sync(self) -> list[dict[str, Any]]:
        """Load and migrate items from disk. Runs in executor."""
        per_entry_path = self.hass.config.path(self._persistence)
        legacy_path = self.hass.config.path(self._legacy_persistence)

        if os.path.exists(per_entry_path):
            raw = load_json_array(per_entry_path)
        elif os.path.exists(legacy_path):
            backup_path = legacy_path + ".bak"
            if not os.path.exists(backup_path):
                import shutil
                shutil.copy2(legacy_path, backup_path)
                _LOGGER.info("Backed up legacy file to %s", backup_path)
            _LOGGER.info(
                "Migrating activities from legacy file %s to %s",
                legacy_path,
                per_entry_path,
            )
            raw = load_json_array(legacy_path)
        else:
            raw = []

        result = []
        for item in raw:
            migrated = self._migrate_item(item)
            if migrated is not None:
                result.append(migrated)
        return result

    def _migrate_item(self, item: dict[str, Any]) -> dict[str, Any] | None:
        """Normalise a raw dict from disk. Returns None to skip corrupt records."""
        if ATTR_FREQUENCY not in item:
            _LOGGER.warning(
                "Skipping activity with no frequency field: %s", item.get(ATTR_ID)
            )
            return None
        item[ATTR_FREQUENCY_MS] = duration_to_ms(item[ATTR_FREQUENCY])
        item.setdefault(ATTR_ICON, DEFAULT_ICON)
        return item

    async def async_save(self) -> None:
        """Persist current data to disk."""
        await self.hass.async_add_executor_job(self._save_sync)

    def _save_sync(self) -> None:
        """Write items to per-entry file. Runs in executor."""
        save_json(self.hass.config.path(self._persistence), self.data or [])

    # ------------------------------------------------------------------
    # Mutation methods — each operates on a copy so listeners always see
    # a consistent snapshot.
    # ------------------------------------------------------------------

    async def async_add_activity(
        self,
        name: str,
        category: str,
        frequency: dict[str, int] | int,
        icon: str = DEFAULT_ICON,
        last_completed: str | None = None,
        context: Context | None = None,
    ) -> dict[str, Any]:
        """Add a new activity, persist, and notify listeners."""
        if last_completed is None:
            last_completed = dt_util.now().isoformat()

        item: dict[str, Any] = {
            ATTR_ID: uuid.uuid4().hex,
            ATTR_NAME: name,
            ATTR_CATEGORY: category,
            ATTR_FREQUENCY: frequency,
            ATTR_FREQUENCY_MS: duration_to_ms(frequency),
            ATTR_LAST_COMPLETED: last_completed,
            ATTR_ICON: icon,
        }

        new_data = list(self.data or []) + [item]
        self.async_set_updated_data(new_data)

        # Add a new entity for this activity if the platform is already set up.
        if self.async_add_entities is not None:
            from .sensor import ActivityEntity  # avoid circular import at module level

            self.async_add_entities([ActivityEntity(self, item[ATTR_ID])])

        await self.async_save()

        _LOGGER.debug("Added activity: %s", item)
        self.hass.bus.async_fire(
            EVENT_UPDATED,
            {"action": "add", "item": item, "entry_id": self.entry_id},
            context=context,
        )
        return item

    async def async_remove_activity(
        self,
        item_id: str,
        context: Context | None = None,
    ) -> dict[str, Any] | None:
        """Remove an activity by id, persist, and notify listeners."""
        current = list(self.data or [])
        item = next((i for i in current if i[ATTR_ID] == item_id), None)
        if item is None:
            _LOGGER.warning("Tried to remove unknown activity id: %s", item_id)
            return None

        new_data = [i for i in current if i[ATTR_ID] != item_id]
        self.async_set_updated_data(new_data)

        # Remove from entity registry so the sensor disappears from HA.
        from homeassistant.helpers.entity_registry import async_get as er_async_get

        entity_registry = er_async_get(self.hass)
        unique_id = f"{self.entry_id}_{item_id}"
        entity_entry = next(
            (e for e in entity_registry.entities.values() if e.unique_id == unique_id),
            None,
        )
        if entity_entry is not None:
            entity_registry.async_remove(entity_entry.entity_id)

        await self.async_save()

        _LOGGER.debug("Removed activity: %s", item)
        self.hass.bus.async_fire(
            EVENT_UPDATED,
            {"action": "remove", "item": item, "entry_id": self.entry_id},
            context=context,
        )
        return item

    async def async_update_activity(
        self,
        item_id: str,
        last_completed: str | None = None,
        name: str | None = None,
        category: str | None = None,
        frequency: dict[str, int] | None = None,
        icon: str | None = None,
        context: Context | None = None,
    ) -> dict[str, Any] | None:
        """Update fields on an existing activity, persist, and notify listeners."""
        current = list(self.data or [])
        idx = next((i for i, it in enumerate(current) if it[ATTR_ID] == item_id), None)
        if idx is None:
            _LOGGER.warning("Tried to update unknown activity id: %s", item_id)
            return None

        # Work on a shallow copy of the item dict so the old snapshot is untouched.
        item = dict(current[idx])

        if last_completed is not None:
            item[ATTR_LAST_COMPLETED] = last_completed
        if name is not None:
            item[ATTR_NAME] = name
        if category is not None:
            item[ATTR_CATEGORY] = category
        if frequency is not None:
            item[ATTR_FREQUENCY] = frequency
            item[ATTR_FREQUENCY_MS] = duration_to_ms(frequency)
        if icon is not None:
            item[ATTR_ICON] = icon

        new_data = current[:idx] + [item] + current[idx + 1 :]
        self.async_set_updated_data(new_data)
        await self.async_save()

        _LOGGER.debug("Updated activity: %s", item)
        self.hass.bus.async_fire(
            EVENT_UPDATED,
            {"action": "updated", "item": item, "entry_id": self.entry_id},
            context=context,
        )
        return item
