"""Acceso inicial a calendarios de iCloud mediante CalDAV."""

import importlib
import os
from datetime import datetime
from types import ModuleType
from typing import Any


DEFAULT_CALDAV_URL = "https://caldav.icloud.com"


def _load_caldav() -> ModuleType:
    try:
        return importlib.import_module("caldav")
    except ModuleNotFoundError as error:
        if error.name != "caldav":
            raise
        raise RuntimeError(
            "Falta la dependencia CalDAV. Instálala con: "
            "pip install caldav"
        ) from error


class ICloudCalendar:
    """Operaciones básicas para listar calendarios y crear eventos en iCloud."""

    def __init__(
        self,
        username: str | None = None,
        app_password: str | None = None,
        calendar_name: str | None = None,
        url: str = DEFAULT_CALDAV_URL,
    ) -> None:
        self.username = username or os.getenv("ICLOUD_USERNAME")
        self.app_password = app_password or os.getenv("ICLOUD_APP_PASSWORD")
        self.calendar_name = calendar_name or os.getenv("ICLOUD_CALENDAR_NAME")
        self.url = url

        if not self.username:
            raise ValueError("Configura ICLOUD_USERNAME con tu Apple ID.")
        if not self.app_password:
            raise ValueError(
                "Configura ICLOUD_APP_PASSWORD con una contraseña específica "
                "para la app."
            )

    def list_calendars(self) -> list[dict[str, str]]:
        """Devuelve los nombres y las URL de los calendarios accesibles."""
        caldav = _load_caldav()
        with caldav.get_calendars(
            url=self.url,
            username=self.username,
            password=self.app_password,
        ) as calendars:
            return [
                {
                    "name": calendar.get_display_name(),
                    "url": str(calendar.url),
                }
                for calendar in calendars
            ]

    def create_event(
        self,
        summary: str,
        start: datetime,
        end: datetime,
        description: str | None = None,
        location: str | None = None,
        calendar_name: str | None = None,
    ) -> None:
        """Crea un evento en el calendario seleccionado."""
        if not summary.strip():
            raise ValueError("El título del evento no puede estar vacío.")
        if start.tzinfo is None or start.utcoffset() is None:
            raise ValueError("La fecha de inicio debe incluir una zona horaria.")
        if end.tzinfo is None or end.utcoffset() is None:
            raise ValueError("La fecha de fin debe incluir una zona horaria.")
        if end <= start:
            raise ValueError("La fecha de fin debe ser posterior a la de inicio.")

        selected_name = calendar_name or self.calendar_name
        caldav = _load_caldav()
        with caldav.get_calendars(
            url=self.url,
            username=self.username,
            password=self.app_password,
        ) as calendars:
            calendar = self._select_calendar(calendars, selected_name)
            event_data: dict[str, Any] = {
                "dtstart": start,
                "dtend": end,
                "summary": summary.strip(),
            }
            if description is not None:
                event_data["description"] = description
            if location is not None:
                event_data["location"] = location
            calendar.add_event(**event_data)

    @staticmethod
    def _select_calendar(
        calendars: list[Any], selected_name: str | None
    ) -> Any:
        if selected_name:
            matches = [
                calendar
                for calendar in calendars
                if calendar.get_display_name() == selected_name
            ]
            if len(matches) == 1:
                return matches[0]
            if not matches:
                available = ", ".join(
                    calendar.get_display_name() for calendar in calendars
                )
                raise ValueError(
                    f"No se encontró el calendario {selected_name!r}. "
                    f"Disponibles: {available or '(ninguno)'}."
                )
            raise ValueError(
                f"Hay más de un calendario llamado {selected_name!r}; "
                "la selección por nombre no es inequívoca."
            )

        if len(calendars) == 1:
            return calendars[0]
        if not calendars:
            raise RuntimeError("No se encontraron calendarios en la cuenta.")
        raise ValueError(
            "Hay varios calendarios. Define ICLOUD_CALENDAR_NAME o indica "
            "calendar_name al crear el evento."
        )
