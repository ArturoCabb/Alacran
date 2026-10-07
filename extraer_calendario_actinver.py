"""Carga una página con Selenium y analiza su HTML con BeautifulSoup."""

import argparse
import getpass
import json
import time
from datetime import date, datetime
from pathlib import Path

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromiumOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


DEFAULT_URL = "https://www.retoactinver.com/RetoActinver/#/eventos"
DATE_FIELDS_SELECTOR = 'input[placeholder="dd/mm/aaaa"]'
CALENDAR_HEADER_SELECTOR = "app-input-header-date-picker .example-header"
EVENT_CARD_SELECTOR = "mat-card.event-card"
PAGINATOR_SELECTOR = "div.custom-paginator"
PAGINATOR_BUTTON_SELECTOR = "button.paginator-button"
CALENDAR_MONTHS = {
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


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Carga una página web en Edge o Chromium."
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="URL que se va a cargar.")
    parser.add_argument(
        "--browser",
        choices=("edge", "chromium"),
        default="edge",
        help="Navegador que usará Selenium (predeterminado: edge).",
    )
    parser.add_argument(
        "--chromium-binary",
        help="Ruta al ejecutable de Chromium; si se omite, Selenium usa Chrome.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Ejecuta el navegador sin mostrar su ventana.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Segundos máximos para esperar a que la página termine de cargar.",
    )
    parser.add_argument(
        "--start-date",
        help="Fecha inicial dd/mm/aaaa; si se omite, se pregunta al ejecutar.",
    )
    parser.add_argument(
        "--end-date",
        help="Fecha final dd/mm/aaaa; si se omite, se pregunta al ejecutar.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("eventos_actinver.json"),
        help="Archivo JSON de salida (predeterminado: eventos_actinver.json).",
    )
    return parser.parse_args(argv)


def validate_date_range(start_date: str, end_date: str) -> None:
    try:
        start = datetime.strptime(start_date, "%d/%m/%Y")
        end = datetime.strptime(end_date, "%d/%m/%Y")
    except ValueError as error:
        raise ValueError("Las fechas deben tener formato dd/mm/aaaa.") from error

    if start > end:
        raise ValueError("La fecha inicial no puede ser posterior a la fecha final.")


def date_input_matches(value: str | None, expected_date: datetime) -> bool:
    if not value:
        return False

    for date_format in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, date_format).date() == expected_date.date()
        except ValueError:
            continue
    return False


def extract_event_cards(page_source: str) -> list[dict[str, str | None]]:
    soup = BeautifulSoup(page_source, "html.parser")
    events: list[dict[str, str | None]] = []

    for card in soup.select(EVENT_CARD_SELECTOR):
        title = card.select_one("mat-card-title")
        date = card.select_one("p.date-event")
        speaker = card.select_one("p.author-event")
        event_type = card.select_one("p.type-event")
        level = card.select_one("div.d-flex.flex-wrap.w-100.pb-2 span.mx-2")

        events.append(
            {
                "titulo": title.get_text(" ", strip=True) if title else None,
                "fecha": date.get_text(" ", strip=True) if date else None,
                "ponente": (
                    speaker.get_text(" ", strip=True).removeprefix("Ponente:").strip()
                    if speaker
                    else None
                ),
                "tipo": (
                    event_type.get_text(" ", strip=True).removeprefix("Tipo:").strip()
                    if event_type
                    else None
                ),
                "nivel": level.get_text(" ", strip=True) if level else None,
            }
        )

    return events


def get_event_page_signature(
    driver: webdriver.Remote,
) -> tuple[tuple[str | None, ...], ...]:
    return tuple(
        (
            event["titulo"],
            event["fecha"],
            event["ponente"],
            event["tipo"],
            event["nivel"],
        )
        for event in extract_event_cards(driver.page_source)
    )


def is_disabled(button: WebElement) -> bool:
    classes = (button.get_attribute("class") or "").lower().split()
    return (
        not button.is_enabled()
        or button.get_attribute("disabled") is not None
        or (button.get_attribute("aria-disabled") or "").lower() == "true"
        or "disabled" in classes
    )


def find_next_page_button(driver: webdriver.Remote) -> WebElement | None:
    paginators = [
        paginator
        for paginator in driver.find_elements(By.CSS_SELECTOR, PAGINATOR_SELECTOR)
        if paginator.is_displayed()
    ]
    if not paginators:
        return None

    if len(paginators) > 1:
        raise RuntimeError("Se encontró más de un paginador visible.")

    buttons = paginators[0].find_elements(By.CSS_SELECTOR, PAGINATOR_BUTTON_SELECTOR)
    if len(buttons) < 2:
        raise RuntimeError(
            f"Se esperaban al menos 2 botones en el paginador; se encontraron "
            f"{len(buttons)}."
        )

    return buttons[-2]


def extract_all_events(
    driver: webdriver.Remote, timeout: int
) -> list[dict[str, str | None]]:
    wait = WebDriverWait(driver, timeout)
    wait.until(
        lambda current_driver: current_driver.find_elements(
            By.CSS_SELECTOR, EVENT_CARD_SELECTOR
        )
    )

    all_events: list[dict[str, str | None]] = []

    while True:
        page_events = extract_event_cards(driver.page_source)
        all_events.extend(page_events)

        next_button = find_next_page_button(driver)
        if next_button is None or is_disabled(next_button):
            break

        old_signature = get_event_page_signature(driver)
        next_button.click()
        try:
            wait.until(
                lambda current_driver: (
                    signature := get_event_page_signature(current_driver)
                )
                and signature != old_signature
            )
        except TimeoutException as error:
            raise RuntimeError(
                "Se hizo clic en el botón de paginación, pero las tarjetas no "
                "cambiaron. Verifica cuál de los botones es el de página siguiente."
            ) from error

    return all_events


def select_calendar_date(
    driver: webdriver.Remote, field_index: int, date_value: str, timeout: int
) -> None:
    target_date = datetime.strptime(date_value, "%d/%m/%Y")
    wait = WebDriverWait(driver, timeout)
    fields = wait.until(
        lambda current_driver: (
            found
            if len(
                found := current_driver.find_elements(
                    By.CSS_SELECTOR, DATE_FIELDS_SELECTOR
                )
            )
            > field_index
            else False
        )
    )
    field = fields[field_index]
    picker_id = field.get_attribute("aria-owns") or field.get_attribute(
        "data-mat-calendar"
    )
    if not picker_id:
        raise RuntimeError(
            f"El campo de fecha {field_index + 1} no indica su calendario asociado."
        )
    field.click()

    def get_visible_picker(current_driver: webdriver.Remote) -> WebElement | bool:
        picker = next(
            (
                element
                for element in current_driver.find_elements(By.ID, picker_id)
                if element.is_displayed()
            ),
            None,
        )
        return picker if picker is not None else False

    def get_visible_header(current_driver: webdriver.Remote) -> WebElement | bool:
        picker = get_visible_picker(current_driver)
        if not isinstance(picker, WebElement):
            return False
        headers = [
            header
            for header in picker.find_elements(
                By.CSS_SELECTOR, CALENDAR_HEADER_SELECTOR
            )
            if header.is_displayed()
        ]
        return headers[0] if len(headers) == 1 else False

    wait.until(get_visible_header)

    def header_changed(
        current_driver: webdriver.Remote, previous: tuple[str, int]
    ) -> bool:
        current_header = get_visible_header(current_driver)
        if not isinstance(current_header, WebElement):
            return False
        current_labels = current_header.find_elements(
            By.CSS_SELECTOR, ".example-header-label"
        )
        return (
            len(current_labels) >= 2
            and (
                current_labels[0].text.strip().lower(),
                int(current_labels[1].text.strip()),
            )
            != previous
        )

    target_month_number = target_date.year * 12 + target_date.month
    while True:
        header = get_visible_header(driver)
        if not isinstance(header, WebElement):
            raise RuntimeError("No se encontró el encabezado del calendario abierto.")
        labels = header.find_elements(By.CSS_SELECTOR, ".example-header-label")
        if len(labels) < 2:
            raise RuntimeError("No se encontraron los controles de mes y año.")

        displayed_month = labels[0].text.strip().lower()
        displayed_year = int(labels[1].text.strip())
        if displayed_month not in CALENDAR_MONTHS:
            raise RuntimeError(
                f"No se reconoce el mes mostrado en el calendario: {displayed_month!r}."
            )

        displayed_month_number = displayed_year * 12 + CALENDAR_MONTHS[displayed_month]
        if displayed_month_number == target_month_number:
            break

        image_index = 0 if displayed_month_number < target_month_number else 1
        arrows = header.find_elements(By.CSS_SELECTOR, "img")
        if len(arrows) < 2:
            raise RuntimeError("No se encontraron las flechas para cambiar de mes.")

        old_header = (displayed_month, displayed_year)
        arrows[image_index].click()
        wait.until(
            lambda current_driver: header_changed(current_driver, old_header)
        )

    def find_day_button(current_driver: webdriver.Remote) -> WebElement | bool:
        picker = get_visible_picker(current_driver)
        if not isinstance(picker, WebElement):
            return False

        first_day = target_date.replace(day=1)
        sunday_based_offset = (first_day.weekday() + 1) % 7
        day_position = sunday_based_offset + target_date.day - 1
        row, column = divmod(day_position, 7)
        cell_selector = (
            f'td.mat-calendar-body-cell-container'
            f'[data-mat-row="{row}"][data-mat-col="{column}"]'
            " > button.mat-calendar-body-cell"
        )
        button = next(
            iter(picker.find_elements(By.CSS_SELECTOR, cell_selector)), None
        )
        if (
            button is None
            or button.find_element(
                By.CSS_SELECTOR, ".mat-calendar-body-cell-content"
            ).text.strip()
            != str(target_date.day)
            or not button.is_displayed()
            or not button.is_enabled()
        ):
            return False
        return button

    day_button = wait.until(find_day_button)
    if not isinstance(day_button, WebElement):
        raise RuntimeError(f"No se encontró el día {date_value} en el calendario.")
    if not day_button.is_displayed() or not day_button.is_enabled():
        raise RuntimeError(f"El día {date_value} no está disponible para seleccionar.")
    day_button.click()
    try:
        wait.until(
            lambda current_driver: (
                len(
                    found := current_driver.find_elements(
                        By.CSS_SELECTOR, DATE_FIELDS_SELECTOR
                    )
                )
                > field_index
                and date_input_matches(
                    found[field_index].get_attribute("value"), target_date
                )
                and found[field_index].get_attribute("aria-invalid") == "false"
            )
        )
    except TimeoutException as error:
        current_fields = driver.find_elements(
            By.CSS_SELECTOR, DATE_FIELDS_SELECTOR
        )
        actual_value = (
            current_fields[field_index].get_attribute("value")
            if len(current_fields) > field_index
            else "(campo no encontrado)"
        )
        raise RuntimeError(
            f"No se pudo confirmar la fecha {date_value} en el campo "
            f"{field_index + 1}; valor actual: {actual_value!r}."
        ) from error
    wait.until(EC.invisibility_of_element_located((By.ID, picker_id)))


def create_driver(
    browser: str, chromium_binary: str | None, headless: bool
) -> webdriver.Remote:
    if browser == "edge":
        options = EdgeOptions()

        if headless:
            options.add_argument("--headless=new")

        options.add_argument("--window-size=1400,1000")
        return webdriver.Edge(options=options)

    options = ChromiumOptions()
    if chromium_binary:
        options.binary_location = chromium_binary
    if headless:
        options.add_argument("--headless=new")

    options.add_argument("--window-size=1400,1000")
    return webdriver.Chrome(options=options)


def normalize_date(value: str | date | None) -> str:
    if value is None:
        return date.today().strftime("%d/%m/%Y")
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return datetime.strptime(value, "%d/%m/%Y").strftime("%d/%m/%Y")


def extract_events(
    start_date: str | date | None = None,
    end_date: str | date | None = None,
    *,
    email: str | None = None,
    password: str | None = None,
    url: str = DEFAULT_URL,
    browser: str = "edge",
    chromium_binary: str | None = None,
    headless: bool = False,
    timeout: int = 30,
    output: str | Path = "eventos_actinver.json",
) -> list[dict[str, str | None]]:
    """Inicia sesión, filtra el calendario y devuelve sus eventos.

    Si no se indican fechas, consulta únicamente los eventos de hoy.
    La contraseña se solicita de forma oculta si no se proporciona.
    """
    start_date = normalize_date(start_date)
    end_date = normalize_date(end_date)
    validate_date_range(start_date, end_date)

    if email is None:
        email = input("Correo de Actinver: ").strip()
    if password is None:
        password = getpass.getpass("Contraseña de Actinver: ")
    if not email or not password:
        raise ValueError("El correo y la contraseña no pueden estar vacíos.")

    output_path = Path(output)
    driver = create_driver(browser, chromium_binary, headless)

    try:
        driver.get(url)
        WebDriverWait(driver, timeout).until(
            lambda current_driver: current_driver.execute_script(
                "return document.readyState"
            )
            == "complete"
        )

        time.sleep(3)
        email_field = WebDriverWait(driver, timeout).until(
            EC.visibility_of_element_located((By.ID, "login-form-email"))
        )
        password_field = WebDriverWait(driver, timeout).until(
            EC.visibility_of_element_located((By.ID, "login-form-pass"))
        )
        email_field.send_keys(email)
        password_field.send_keys(password)

        login_button = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.ID, "btn-login-form"))
        )
        login_button.click()
        time.sleep(10)

        driver.get(url)
        WebDriverWait(driver, timeout).until(
            lambda current_driver: len(
                current_driver.find_elements(By.CSS_SELECTOR, DATE_FIELDS_SELECTOR)
            )
            >= 2
        )

        select_calendar_date(driver, 0, start_date, timeout)
        select_calendar_date(driver, 1, end_date, timeout)
        time.sleep(2)

        events = extract_all_events(driver, timeout)
        output_path.write_text(
            json.dumps(events, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Eventos extraídos: {len(events)}")
        print(f"Archivo JSON: {output_path.resolve()}")
        return events
    finally:
        driver.quit()


def main() -> None:
    args = parse_arguments()
    today = date.today().strftime("%d/%m/%Y")
    start_date = args.start_date or input(
        f"Fecha inicial (dd/mm/aaaa) [{today}]: "
    ).strip() or today
    end_date = args.end_date or input(
        f"Fecha final (dd/mm/aaaa) [{today}]: "
    ).strip() or today

    extract_events(
        start_date,
        end_date,
        url=args.url,
        browser=args.browser,
        chromium_binary=args.chromium_binary,
        headless=args.headless,
        timeout=args.timeout,
        output=args.output,
    )


if __name__ == "__main__":
    main()
