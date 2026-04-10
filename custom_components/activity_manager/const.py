"""Constants for the Activity Manager integration."""

DOMAIN = "activity_manager"
PERSISTENCE = ".activities_list.json"

# Config entry versioning
ENTRY_VERSION = 1
ENTRY_MINOR_VERSION = 3

# Platforms
PLATFORMS = ["sensor"]

# Websocket command types
WS_ITEMS = "activity_manager/items"
WS_ADD = "activity_manager/add"
WS_UPDATE = "activity_manager/update"
WS_REMOVE = "activity_manager/remove"

# Bus event
EVENT_UPDATED = "activity_manager_updated"

# Service names
SERVICE_ADD = "add_activity"
SERVICE_REMOVE = "remove_activity"
SERVICE_UPDATE = "update_activity"

# Activity field names
ATTR_ID = "id"
ATTR_NAME = "name"
ATTR_CATEGORY = "category"
ATTR_FREQUENCY = "frequency"
ATTR_FREQUENCY_MS = "frequency_ms"
ATTR_LAST_COMPLETED = "last_completed"
ATTR_ICON = "icon"

DEFAULT_ICON = "mdi:checkbox-outline"
