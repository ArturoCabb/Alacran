"""Sincroniza eventos de Actinver con el calendario de Microsoft Outlook."""

import argparse
import asyncio
import configparser
import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from msgraph.generated.models.body_type import BodyType
from msgraph.generated.models.date_time_time_zone import DateTimeTimeZone
from msgraph.generated.models.event import Event
from msgraph.generated.models.item_body import ItemBody
from msgraph.generated.models.location import Location

import extraer_calendario_actinver
from graph import Graph


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
CONFIG_FILES = (
    SCRIPT_DIRECTORY / "config.cfg",
    SCRIPT_DIRECTORY / "config.dev.cfg",
)
OUTPUT_FILE = SCRIPT_DIRECTORY / "eventos_actinver.json"
LOCAL_TIMEZONE = timezone(timedelta(hours=-6))
GRAPH_TIMEZONE = "Central Standard Time (Mexico)"
EVENT_LOCATION = "https://www.retoactinver.com/RetoActinver/#/eventos"
MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}
EVENT_DATE_PATTERN = re.compile(
    r"^\s*(?P<day>\d{1,2})\s+de\s+"
    r"(?P<month>[a-záéíóú]+)\s+"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*"
    r"(?P<period>[ap])\.?\s*m\.?\s*$",
    re.IGNORECASE,
)


def parse_event_datetime(event_date: str, year: int) -> datetime:
    """Convierte la fecha visible de Actinver a hora local de Ciudad de México."""
    normalized_date = " ".join(event_date.replace("\u00a0", " ").split())
    match = EVENT_DATE_PATTERN.match(normalized_date)
    if match is None:
        raise ValueError(f"No se reconoce el formato de fecha del evento: {event_date!r}")

    month_name = match.group("month").lower()
    if month_name not in MONTHS:
        raise ValueError(f"Mes desconocido en la fecha del evento: {month_name!r}")

    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    period = match.group("period").lower()
    if not 1 <= hour <= 12:
        raise ValueError(f"Hora fuera de rango en la fecha del evento: {event_date!r}")
    if period == "p" and hour != 12:
        hour += 12
    elif period == "a" and hour == 12:
        hour = 0

    return datetime(
        year,
        MONTHS[month_name],
        int(match.group("day")),
        hour,
        minute,
        tzinfo=LOCAL_TIMEZONE,
    )


def build_graph_event(source_event: dict[str, Any], year: int) -> Event:
    """Construye el evento de Graph con los datos que se sincronizan."""
    title = source_event.get("titulo")
    event_date = source_event.get("fecha")
    if not title or not event_date:
        raise ValueError(f"El evento de Actinver no tiene título o fecha: {source_event!r}")

    start = parse_event_datetime(event_date, year)
    end = start + timedelta(hours=1)
    body_content = (
        f"{title} {event_date} {source_event.get('ponente') or ''} "
        f"{source_event.get('tipo') or ''} "
        f"Nivel: {source_event.get('nivel') or ''}"
    ).strip()

    return Event(
        subject=title,
        body=ItemBody(content_type=BodyType.Html, content=body_content),
        start=DateTimeTimeZone(
            date_time=start.isoformat(timespec="seconds"),
            time_zone=GRAPH_TIMEZONE,
        ),
        end=DateTimeTimeZone(
            date_time=end.isoformat(timespec="seconds"),
            time_zone=GRAPH_TIMEZONE,
        ),
        location=Location(display_name=EVENT_LOCATION),
    )


def graph_event_needs_update(existing: Event, desired: Event) -> bool:
    if existing.subject != desired.subject:
        return True

    desired_start = desired.start
    desired_end = desired.end
    if (
        desired_start is None
        or desired_end is None
    ):
        raise ValueError("El evento deseado debe tener inicio y fin.")

    for current, expected in (
        (existing.start, desired_start),
        (existing.end, desired_end),
    ):
        if (
            current is None
            or current.date_time is None
            or expected.date_time is None
        ):
            return True
        try:
            current_datetime = datetime.fromisoformat(
                current.date_time.replace("Z", "+00:00")
            )
            expected_datetime = datetime.fromisoformat(
                expected.date_time.replace("Z", "+00:00")
            )
        except ValueError:
            return True
        if current_datetime.replace(tzinfo=None) != expected_datetime.replace(
            tzinfo=None
        ):
            return True

    desired_body = (
        BeautifulSoup(desired.body.content or "", "html.parser").get_text(
            " ", strip=True
        )
        if desired.body
        else None
    )
    existing_body = (
        BeautifulSoup(existing.body.content or "", "html.parser").get_text(
            " ", strip=True
        )
        if existing.body
        else None
    )
    if existing_body != desired_body:
        return True

    desired_location = desired.location.display_name if desired.location else None
    existing_location = existing.location.display_name if existing.location else None
    return existing_location != desired_location


def load_settings() -> tuple[configparser.ConfigParser, Graph]:
    config = configparser.ConfigParser()
    config.read([str(path) for path in CONFIG_FILES])
    if "azure" not in config:
        raise RuntimeError("No se encontró la sección [azure] en config.cfg.")
    if "actinver" not in config:
        raise RuntimeError("No se encontró la sección [actinver] en config.cfg.")
    return config, Graph(config["azure"])


def required_actinver_credentials(
    config: configparser.ConfigParser,
) -> tuple[str, str]:
    settings = config["actinver"]
    email = settings.get("email", "").strip()
    password = settings.get("password", "")
    if not email or not password:
        raise RuntimeError(
            "La opción automática requiere email y password en la sección "
            "[actinver] de config.cfg."
        )
    return email, password


async def synchronize_today(
    graph: Graph, email: str, password: str
) -> tuple[int, int, int]:
    today = datetime.now(LOCAL_TIMEZONE).date()
    today_text = today.strftime("%d/%m/%Y")
    graph_start = datetime.combine(
        today, time.min, tzinfo=LOCAL_TIMEZONE
    ).isoformat(timespec="seconds")
    graph_end = datetime.combine(
        today, time(23, 59, 59), tzinfo=LOCAL_TIMEZONE
    ).isoformat(timespec="seconds")

    print(f"Consultando Actinver para {today_text}.")
    source_events = extraer_calendario_actinver.extract_events(
        start_date=today,
        end_date=today,
        email=email,
        password=password,
        headless=True,
        timeout=30,
        output=OUTPUT_FILE,
    )

    print(f"Consultando Microsoft Graph para {today_text} ({today.year}).")
    response = await graph.get_events(graph_start, graph_end)
    graph_events = response.value if response and response.value else []

    events_by_title: dict[str, list[Event]] = {}
    for existing in graph_events:
        title_key = (existing.subject or "").strip().casefold()
        events_by_title.setdefault(title_key, []).append(existing)

    updated = 0
    created = 0
    unchanged = 0
    matched_graph_ids: set[str] = set()

    for source_event in source_events:
        desired_event = build_graph_event(source_event, today.year)
        title_key = (desired_event.subject or "").strip().casefold()
        matches = events_by_title.get(title_key, [])

        if len(matches) > 1:
            raise RuntimeError(
                f"Hay más de un evento de Microsoft Graph con el título "
                f"{desired_event.subject!r}; no se actualizará para evitar "
                "modificar el evento equivocado."
            )

        if not matches:
            created_event = await graph.create_event(desired_event)
            if created_event is None:
                raise RuntimeError(
                    f"Graph no devolvió el evento creado: {desired_event.subject!r}."
                )
            created += 1
            print(f"Creado: {desired_event.subject}")
            continue

        existing = matches[0]
        if not existing.id:
            raise RuntimeError(
                f"Graph devolvió el evento {existing.subject!r} sin ID; "
                "no se puede actualizar."
            )
        matched_graph_ids.add(existing.id)

        if graph_event_needs_update(existing, desired_event):
            await graph.update_event(existing.id, desired_event)
            updated += 1
            print(f"Actualizado: {desired_event.subject}")
        else:
            unchanged += 1

    graph_only = sum(
        1
        for existing in graph_events
        if existing.id and existing.id not in matched_graph_ids
    )
    print(
        f"Sincronización terminada: {created} creados, {updated} actualizados, "
        f"{unchanged} sin cambios, {graph_only} solo en Microsoft Graph "
        "(no se eliminaron)."
    )
    return created, updated, unchanged


async def create_events_manually(
    graph: Graph, email: str, password: str
) -> int:
    start_text = input("Fecha inicial (dd/mm/aaaa): ").strip()
    end_text = input("Fecha final (dd/mm/aaaa): ").strip()
    start_date = datetime.strptime(start_text, "%d/%m/%Y").date()
    end_date = datetime.strptime(end_text, "%d/%m/%Y").date()
    if start_date > end_date:
        raise ValueError("La fecha inicial no puede ser posterior a la fecha final.")

    source_events = extraer_calendario_actinver.extract_events(
        start_date=start_date,
        end_date=end_date,
        email=email,
        password=password,
        headless=False,
        timeout=30,
        output=OUTPUT_FILE,
    )

    created = 0
    for source_event in source_events:
        await graph.create_event(build_graph_event(source_event, start_date.year))
        created += 1
    print(f"Eventos creados: {created}")
    return created


async def run(mode: int) -> None:
    config, graph = load_settings()
    email, password = required_actinver_credentials(config)

    if mode == 1:
        await synchronize_today(graph, email, password)
    else:
        await create_events_manually(graph, email, password)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sincroniza los eventos de Actinver y Microsoft Graph."
    )
    parser.add_argument(
        "--numero",
        type=int,
        choices=(1, 2),
        default=1,
        help="1: sincronización automática de hoy (predeterminado); "
        "2: creación manual por rango de fechas.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_arguments()
    asyncio.run(run(arguments.numero))
