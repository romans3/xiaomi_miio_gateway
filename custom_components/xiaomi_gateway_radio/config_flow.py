import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONF_HOST, CONF_TOKEN, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)

# ✅ SINGOLO lazy import
try:
    from miio import Device, DeviceException  # type: ignore
except ImportError:
    Device = None
    DeviceException = None

async def _async_validate_input(hass: HomeAssistant, data: dict) -> dict:
    """Validate the user input allows us to connect."""
    
    if Device is None:
        raise Exception("python-miio not available")

    host = data[CONF_HOST]
    token = data[CONF_TOKEN]

    def _sync_test():
        dev = Device(host, token)
        info = dev.info()
        return info

    info = await hass.async_add_executor_job(_sync_test)

    return {
        "title": data.get("name") or DEFAULT_NAME,
        "model": info.model,
        "firmware": info.firmware_version,
        "hardware": info.hardware_version,
    }

class XiaomiGatewayRadioConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Xiaomi Gateway Radio."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await _async_validate_input(self.hass, user_input)
            except Exception as err:  # broad, ma ok per il flow
                _LOGGER.error("Error validating Xiaomi Gateway Radio: %s", err)
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(f"{user_input[CONF_HOST]}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"],
                    data={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_TOKEN: user_input[CONF_TOKEN],
                        "name": info["title"],
                        "volume_step": user_input.get("volume_step", 5),
                    },
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_TOKEN): str,
                vol.Optional("name", default=DEFAULT_NAME): str,
                vol.Optional("volume_step", default=5): int,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )
