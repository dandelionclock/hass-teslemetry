"""Config Flow for Teslemetry integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiohttp import ClientConnectionError
from tesla_fleet_api import Teslemetry
from tesla_fleet_api.exceptions import (
    InvalidToken,
    SubscriptionRequired,
    TeslaFleetError,
    Forbidden,
)
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, FlowResult
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, LOGGER

TESLEMETRY_SCHEMA = vol.Schema({vol.Required(CONF_ACCESS_TOKEN): str})
DESCRIPTION_PLACEHOLDERS = {
    "short_url": "teslemetry.com/console",
    "url": "[teslemetry.com/console](https://teslemetry.com/console)",
}


class TeslemetryConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config Teslemetry API connection."""

    VERSION = 1
    _entry: ConfigEntry | None = None

    async def async_auth(self, user_input: Mapping[str, Any]) -> dict[str, str]:
        """Reusable Auth Helper."""
        user_input[CONF_ACCESS_TOKEN] = user_input[CONF_ACCESS_TOKEN].strip()

        teslemetry = Teslemetry(
            session=async_get_clientsession(self.hass),
            access_token=user_input[CONF_ACCESS_TOKEN],
        )
        try:
            metadata = await teslemetry.metadata()
        except InvalidToken:
            return {CONF_ACCESS_TOKEN: "invalid_access_token"}
        except SubscriptionRequired:
            return {"base": "subscription_required"}
        except Forbidden:
            return {"base": "forbidden"}
        except ClientConnectionError:
            return {"base": "cannot_connect"}
        except TeslaFleetError as e:
            LOGGER.error(str(e))
            return {"base": "unknown"}

        await self.async_set_unique_id(metadata["uid"])
        return {}

    async def async_step_user(
        self, user_input: Mapping[str, Any] | None = None
    ) -> FlowResult:
        """Get configuration from the user."""
        errors: dict[str, str] = {}
        if user_input and not (errors := await self.async_auth(user_input)):
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Teslemetry",
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=TESLEMETRY_SCHEMA,
            description_placeholders=DESCRIPTION_PLACEHOLDERS,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        """Handle reauth on failure."""
        self._entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm(entry_data)

    async def async_step_reauth_confirm(
        self, user_input: Mapping[str, Any] | None = None
    ) -> FlowResult:
        """Handle users reauth credentials."""

        errors: dict[str, str] | None = None

        if user_input and not (errors := await self.async_auth(user_input)):
            if self._entry:
                self.hass.config_entries.async_update_entry(
                    self._entry,
                    data=user_input,
                )
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(self._entry.entry_id)
                )
                return self.async_abort(reason="reauth_successful")
            return self.async_create_entry(title="Teslemetry", data=user_input)

        return self.async_show_form(
            step_id="reauth_confirm",
            description_placeholders=DESCRIPTION_PLACEHOLDERS,
            data_schema=TESLEMETRY_SCHEMA,
            errors=errors,
        )
