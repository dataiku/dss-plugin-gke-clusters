def do(payload, config, plugin_config, inputs):
    if config.get("isAutopilot", False):
        return {
            "choices": [
                {"label": "Rapid", "value": "RAPID"},
                {"label": "Regular", "value": "REGULAR"},
                {"label": "Stable", "value": "STABLE"},
            ]
        }
    else:
        return {
            "choices": [
                {"label": "Rapid", "value": "RAPID"},
                {"label": "Regular", "value": "REGULAR"},
                {"label": "Stable", "value": "STABLE"},
                {"label": "Extended", "value": "EXTENDED"},
                {"label": "No Channel", "value": "NO_CHANNEL"},
            ]
        }

