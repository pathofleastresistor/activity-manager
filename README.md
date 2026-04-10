# activity-manager

Track recurring activities from within Home Assistant.

Use the companion [Activity Manager Card](https://github.com/pathofleastresistor/activity-manager-card) for the best experience.

Each activity has a frequency (e.g. every 7 days). The integration tracks when it was last completed and exposes a sensor whose state is the next due datetime. Activities can be overdue, due soon, or on track.

<p align="center">
  <img width="600" src="images/activitymanager.gif">
</p>

## Installation

### HACS

1. Open the HACS section of Home Assistant.
2. Click the "..." button in the top right corner and select "Custom Repositories."
3. Paste this repository's GitHub URL, select "Integration", and click Install.

### Manually

Copy the `activity_manager` directory into your HA config directory:

```
<config>/custom_components/activity_manager/
```

## Setup

Once installed, add the integration from the UI:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=activity_manager)

You will be prompted to give the list a name (e.g. "Home", "Garden", "Car"). You can add the integration multiple times to create independent lists.

### Upgrading from a legacy installation

If you have an existing installation (v1.2 or earlier), your data and config entry will be automatically migrated on first startup:

- Your config entry will be renamed to **"Activity Manager"** (the name used by all legacy installs).
- Your activities will be migrated from `.activities_list.json` to a per-list file. A backup is saved as `.activities_list.json.bak` before migration.

No manual steps required.

## Card

Add the [Activity Manager Card](https://github.com/pathofleastresistor/activity-manager-card) to your dashboard. Use the built-in card editor to:

- Select which activity list to display
- Optionally filter by category
- Add, edit, and remove activities directly from the card

## Entities

An entity is created for each activity under `sensor.<list>_<category>_<name>`. The entity state is the datetime when the activity is next due.

Each entity exposes the following attributes:

| Attribute | Description |
|-----------|-------------|
| `category` | The activity's category |
| `last_completed` | ISO datetime of the last completion |
| `frequency_ms` | Repeat interval in milliseconds |
| `frequency` | Repeat interval as `{days, hours, minutes}` |
| `id` | Internal activity ID |
| `entry_id` | Config entry ID of the list this activity belongs to |
| `list_title` | Human-readable name of the list |

## Services

### `activity_manager.add_activity`

Add a new activity to a list.

| Field | Required | Description |
|-------|----------|-------------|
| `list` | Yes | Name of the activity list (e.g. `"Home"`; legacy installs use `"Activity Manager"`) |
| `name` | Yes | Activity name |
| `category` | Yes | Category (used for grouping and filtering) |
| `frequency` | Yes | How often the activity repeats. Either an integer number of seconds, or an object with `days`, `hours`, and/or `minutes` |
| `last_completed` | No | ISO datetime of last completion. Defaults to now. |
| `icon` | No | MDI icon name (e.g. `mdi:car`) |

### `activity_manager.update_activity`

Update an existing activity.

| Field | Required | Description |
|-------|----------|-------------|
| `entity_id` | Yes | Entity ID of the activity to update |
| `now` | No | Set to `true` to mark the activity as completed right now |
| `last_completed` | No | ISO datetime to set as the last completion time |
| `category` | No | New category |
| `frequency` | No | New frequency (same format as `add_activity`) |
| `icon` | No | New icon |

### `activity_manager.remove_activity`

Remove an activity permanently.

| Field | Required | Description |
|-------|----------|-------------|
| `entity_id` | Yes | Entity ID of the activity to remove |

## Notifications

Because each activity is a sensor entity, you can build automations around them. The example below sends a mobile notification at sunrise listing all overdue workout activities:

```yaml
service: notify.mobile_android_phone
data:
  title: >-
    Workout reminder{% if (states.sensor | selectattr('attributes.integration', 'eq', 'activity_manager') |
    selectattr('attributes.category', 'equalto', 'Workout') |
    map(attribute='state') | map('as_datetime') | reject(">", now()) | list |
    count > 1)%}s{% endif %}
  message: >-
    {{ "Remember to stay healthy and go do: " }}
    {%- set new_line = joiner("<br />") %}
    <br />
    {%- for activity in states.sensor | selectattr('attributes.integration', 'eq', 'activity_manager') -%}
    {%- if activity.state|as_datetime < now() and activity.attributes.category=="Workout"  -%}
    {{ new_line() }}{{ " - "}}{{  activity.name }}
    {%- endif -%}
    {%- endfor %}
  data:
    priority: high
    ttl: 0
    importance: high
    notification_icon: "mdi:dumbbell"
```

## Storage

Activities are stored in your HA config directory, one file per list:

```
<config>/.activities_list_<entry_id>.json
```

Legacy installs stored everything in `.activities_list.json`. This file is automatically migrated on first startup and a `.activities_list.json.bak` backup is kept.
