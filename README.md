# EARLY RELEASE

This was designed to solve a personal need and I'm now trying to prepare it for others to use. That means several things can break between releases.

# activity-manager

Manager recurring tasks from within Home Assistant

Use the companion [Activity Manager Card](https://github.com/pathofleastresistor/activity-manager-card) for the best experience.

The core idea is that an activity happens on a recurring basis, which is stored in the `frequency` field when adding an activity. By default, the activity is last completed when you first add the activity and then the timer can be reset.

<p align="center">
  <img width="600" src="images/activitymanager.gif">
</p>

## Installation

### Manually

Clone or download this repository and copy the "nfl" directory to your "custom_components" directory in your config directory

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

If you're using the [Activity Manager Card](https://github.com/pathofleastresistor/activity-manager-card), then you all you need to do is add the Activity Manager Card to your dashboard. When you're creating the card, you'll have to supply a `category` attribute to the card.

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

Another example on automation for a daily mail report on overdue tasks (copy&paste into automations.yaml)
```
- id: '1688160592613'
  alias: 'activity-manager: daily email reminder on overdue tasks'
  description: email notification on overdue tasks within activity-manager
  trigger:
  - platform: sun
    event: sunrise
    offset: 0
  condition:
  - condition: template
    value_template: '{{ states.sensor | selectattr(''attributes.integration'', ''eq'',
      ''activity_manager'') | map(attribute=''state'') | map(''as_datetime'') | reject(">",
      now()) | list | count > 0 }}'
  action:
  - service: notify.notify_email
    data:
      target:
      - example@domain.com
      title: '#### {{ states.sensor | selectattr(''attributes.integration'', ''eq'',
        ''activity_manager'') | map(attribute=''state'') |  map(''as_datetime'') |
        reject(">", now()) | list | count }}  overdue tasks ####'
      message: '

        currently {{ states.sensor | selectattr(''attributes.integration'', ''eq'',
        ''activity_manager'') | map(attribute=''state'') | map(''as_datetime'') |
        reject(">", now())  | list | count }} tasks are overdue: {{"\n"}}  {%- for
        activity in states.sensor | selectattr(''attributes.integration'', ''eq'',
        ''activity_manager'') -%} {%- if  activity.state|as_datetime < now() -%} {{"\n"}}
        {{ activity.name }} seit {{ (now() - activity.state|as_datetime).days }} {{"Tagen
        ("}}{{ as_timestamp(activity.state|as_datetime) | timestamp_custom(''%d.%m.%Y'')
        }}{{")"}} {%- endif -%} {%- endfor %} {{"\n"}}      {{"\n"}}      {{"\n"}}

        overview of all {{ states.sensor | selectattr(''attributes.integration'',
        ''eq'', ''activity_manager'') | map(attribute=''state'') | map(''as_datetime'')
        | list | count }} Aufgaben: {{"\n"}}         {%- for activity in states.sensor
        | selectattr(''attributes.integration'', ''eq'', ''activity_manager'') -%}     {{"\n"}}{{  activity.name
        }} last {{ as_timestamp(activity.attributes.last_completed|as_datetime)
        | timestamp_custom(''%d.%m.%Y'') }}, in {{ (activity.state|as_datetime - now()).days
        }}/{{ int(activity.attributes.frequency_ms /86400000) }} days      {%- endfor
        %}

        {{"\n"}}{{"\n"}} This Mail was automatically sent via homeAssistant/automation'
  mode: single
```

### More information

-   Activities are stored in .activities_list.json in your `<config>` folder
-   An entity is created for each activity (e.g. `sensor.<category>_<activity>`). The state of the activity is the datetime of when the activity is due. You can use this entity to build notifications or your own custom cards.
-   Three services are exposed: `activity_manager.add_activity`, `activity_manager.update_activity`, `activity_manager.remove_activity`. The update activity can be used to reset the timer.
