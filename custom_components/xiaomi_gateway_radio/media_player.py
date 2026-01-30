import logging
from functools import partial

from homeassistant.components.media_player import MediaPlayerEntity
from homeassistant.components.media_player.const import (
    MediaPlayerEntityFeature,
)
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, DATA_DEVICE, DEFAULT_NAME

_LOGGER = logging.getLogger(__name__)

# SOLO LE FEATURE REALMENTE SUPPORTATE DAL GATEWAY
SUPPORT_XIAOMI_GATEWAY_FM = (
    MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.VOLUME_MUTE
)

try:
    from miio import Device, DeviceException  # type: ignore
except ImportError:
    Device = None
    DeviceException = None

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    device = data[DATA_DEVICE]
    info = data["info"]

    name = entry.data.get("name", DEFAULT_NAME)
    volume_step = entry.data.get("volume_step", 5)

    entity = XiaomiGatewayRadioMediaPlayer(
        hass=hass,
        device=device,
        name=name,
        model=info.model,
        firmware=info.firmware_version,
        hardware=info.hardware_version,
        unique_id=f"{info.model}-{info.mac_address}-fm",
        volume_step=volume_step,
    )

    async_add_entities([entity])


class XiaomiGatewayRadioMediaPlayer(MediaPlayerEntity):

    _attr_supported_features = SUPPORT_XIAOMI_GATEWAY_FM

    def __init__(
        self,
        hass: HomeAssistant,
        device,
        name: str,
        model: str,
        firmware: str,
        hardware: str,
        unique_id: str,
        volume_step: int,
    ) -> None:
        self.hass = hass
        self._device = device
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._model = model
        self._firmware = firmware
        self._hardware = hardware

        self._attr_icon = "mdi:radio"
        self._attr_available = True
        self._attr_state = None

        self._muted = False
        self._volume = 0.0
        self._volume_step = max(1, int(volume_step))

    # ---------------------------
    # PROPRIETÀ RICHIESTE DA HA
    # ---------------------------

    @property
    def volume_level(self):
        return self._volume

    @property
    def is_volume_muted(self):
        return self._muted

    @property
    def state(self):
        return self._attr_state

    @property
    def extra_state_attributes(self):
        return {
            "model": self._model,
            "firmware_version": self._firmware,
            "hardware_version": self._hardware,
            "muted": self._muted,
            "volume_step": self._volume_step,
        }

    # ---------------------------
    # COMANDI DI BASE
    # ---------------------------

    async def _async_try_command(self, mask_error: str, func, *args, **kwargs) -> bool:
        """Nessun import qui!"""
        if DeviceException is None:
            _LOGGER.error("python-miio not available")
            return False

        try:
            result = await self.hass.async_add_executor_job(
                partial(func, *args, **kwargs)
            )
            _LOGGER.debug("Response from Xiaomi Gateway Radio: %s", result)
            return True
        except DeviceException as exc:  # ✅ Ora funziona
            _LOGGER.error("%s: %s", mask_error, exc)
            self._attr_available = False
            return False

    # ---------------------------
    # ON / OFF
    # ---------------------------

    async def async_turn_on(self):
        ok = await self._async_try_command("Turn on failed", self._device.send, "play_fm", ["on"])
        if ok:
            self._attr_state = STATE_ON
            self.async_write_ha_state()

    async def async_turn_off(self):
        ok = await self._async_try_command("Turn off failed", self._device.send, "play_fm", ["off"])
        if ok:
            self._attr_state = STATE_OFF
            self.async_write_ha_state()

    # ---------------------------
    # VOLUME
    # ---------------------------

    async def async_volume_up(self):
        volume = round(self._volume * 100) + self._volume_step
        volume = max(0, min(100, volume))
        await self._async_try_command("Volume up failed", self._device.send, "set_fm_volume", [volume])

    async def async_volume_down(self):
        volume = round(self._volume * 100) - self._volume_step
        volume = max(0, min(100, volume))
        await self._async_try_command("Volume down failed", self._device.send, "set_fm_volume", [volume])

    async def async_set_volume_level(self, volume):
        try:
            volume = float(volume)
        except Exception:
            _LOGGER.error("Invalid volume value: %s", volume)
            return

        volset = max(0, min(100, round(volume * 100)))

        ok = await self._async_try_command(
            "Setting volume failed", self._device.send, "set_fm_volume", [volset]
        )

        if ok:
            self._volume = volume
            self._muted = (volset == 0)
            self._attr_volume_level = volume
            self.async_write_ha_state()

    async def async_mute_volume(self, mute: bool):
        volume = 0 if mute else 10
        ok = await self._async_try_command("Mute failed", self._device.send, "set_fm_volume", [volume])
        if ok:
            self._muted = mute
            self._volume = volume / 100
            self.async_write_ha_state()

    # ---------------------------
    # UPDATE
    # ---------------------------

    async def async_update(self):
        """Nessun import qui!"""
        if DeviceException is None:
            self._attr_available = False
            return

        try:
            def _sync_state():
                return self._device.send("get_prop_fm", "")

            state = await self.hass.async_add_executor_job(_sync_state)

            volume = state.pop("current_volume", None)
            status = state.pop("current_status", None)

            if volume is not None:
                self._volume = volume / 100
                self._muted = volume == 0

            if status == "pause":
                self._attr_state = STATE_OFF
            elif status == "run":
                self._attr_state = STATE_ON
            else:
                self._attr_state = None

            self._attr_available = True

        except DeviceException as ex:  # ✅ Ora funziona
            self._attr_available = False
            _LOGGER.error("Error while fetching state: %s", ex)
