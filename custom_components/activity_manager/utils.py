from homeassistant.util import dt


def dt_as_local(dt_str=None):
    return dt.as_local(dt.parse_datetime(dt_str)).isoformat()
