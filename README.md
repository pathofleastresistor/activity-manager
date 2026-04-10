# activity-manager

Manager recurring tasks from within Home Assistant

Use the companion [Activity Manager Card](https://github.com/pathofleastresistor/activity-manager-card) for the best experience.

The core idea is that an activity happens on a recurring basis, which is stored in the `frequency` field when adding an activity. By default, the activity is last completed when you first add the activity and then the timer can be reset.

<p align="center">
  <img width="600" src="images/activitymanager.gif">
</p>

## Installation

### Manually

Clone or download this repository and copy the "activity_manager" directory to your "custom_components" directory in your config directory

`<config directory>/custom_components/activity-manager/...`

### HACS

1. Open the HACS section of Home Assistant.
2. Click the "..." button in the top right corner and select "Custom Repositories."
3. In the window that opens paste this Github URL.
4. Select "Integration"
5. In the window that opens when you select it click om "Install This Repository in HACS"

## Usage

Once installed, you can use the link below to add the integration from the UI.

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=activity_manager)

You can add multiple activity lists by adding the integration more than once — each instance is independent with its own set of activities.

If you're using the [Activity Manager Card](https://github.com/pathofleastresistor/activity-manager-card), add the card to your dashboard and use the built-in editor to select which activity list to display. You can optionally filter by category.

### Notifications

Because entities are exposed for each activity, you can build custom notifications. The example below runs an automation at sunrise to remind the user if they are past due on workout activities:

```
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

### More information

-   Activities are stored in `.activities_list_<entry_id>.json` in your `<config>` folder, one file per list. If you're upgrading from an older version, the legacy `.activities_list.json` is automatically migrated and a `.activities_list.json.bak` backup is created.
-   An entity is created for each activity. The state of the entity is the datetime of when the activity is next due. You can use this entity to build notifications or your own custom cards.
-   Three services are exposed:
    -   `activity_manager.add_activity` — add a new activity; requires `entry_id` (to select the list), `name`, `category`, `frequency`; optional `last_completed` and `icon`
    -   `activity_manager.update_activity` — update an existing activity by `entity_id`; pass `now: true` to reset the timer to now, or `last_completed` to set a specific datetime
    -   `activity_manager.remove_activity` — remove an activity by `entity_id`
