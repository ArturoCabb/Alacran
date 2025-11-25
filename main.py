import asyncio
import configparser
from json import load
from msgraph.generated.models.o_data_errors.o_data_error import ODataError
from graph import Graph
from msgraph.generated.models.event import Event
from msgraph.generated.models.item_body import ItemBody
from msgraph.generated.models.body_type import BodyType
from msgraph.generated.models.date_time_time_zone import DateTimeTimeZone
from msgraph.generated.models.location import Location

MONTH_MAP = {
    "Enero": "01",
    "Febrero": "02",
    "Marzo": "03",
    "Abril": "04",
    "Mayo": "05",
    "Junio": "06",
    "Julio": "07",
    "Agosto": "08",
    "Septiembre": "09",
    "Octubre": "10",
    "Noviembre": "11",
    "Diciembre": "12"
}

def parse_event_date(date_str: str):
    date = date_str.get("date").split(" ")
    month = MONTH_MAP.get(date[2])
    is_pm = "p. m." in date_str.get("date")
    hour_min = date[3].split(":")
    hour = int(hour_min[0])
    end_hour = 0
    if is_pm:
        if hour == 12:
            pass
        else:
            hour += 12
        end_hour = hour + 1
    else:
        end_hour = hour + 1
        if len(str(hour)) == 1:
            hour = f"0{hour}"
        if len(str(end_hour)) == 1:
            end_hour = f"0{end_hour}"
    
    minute = hour_min[1]
    print(hour)
    print(end_hour)
    return month, date, hour, minute, end_hour

async def main():
    print('Python Graph Tutorial\n')

    # Load settings
    config = configparser.ConfigParser()
    config.read(['config.cfg', 'config.dev.cfg'])
    azure_settings = config['azure']

    graph: Graph = Graph(azure_settings)

    await greet_user(graph)

    choice = -1

    while choice != 0:
        print('Please choose one of the following options:')
        print('0. Exit')
        print('1. Display access token')
        print('2. List my inbox')
        print('3. Send mail')
        print("4. Crear eventos en el calendario")
        print('5. Make a Graph call')

        try:
            choice = int(input())
        except ValueError:
            choice = -1

        try:
            match(choice):
                case 0:
                    print('Goodbye...')
                case 1:
                    await display_access_token(graph)
                case 2:
                    await list_inbox(graph)
                case 3:
                    await send_mail(graph)
                case 4:
                    list_events = read_data_from_json("events.json")
                    await create_event(list_events, graph)
                case 5:
                    await make_graph_call(graph)
                case _:
                    print('Invalid choice!\n')
        except ODataError as odata_error:
            print('Error:')
            if odata_error.error:
                print(odata_error.error.code, odata_error.error.message)

def read_data_from_json(file_path: str) -> list[dict]:
    """Lee un archivo JSON y devuelve una lista de diccionarios."""
    with open(file_path, 'r', encoding='utf-8-sig') as f:
        data = load(f)
    return data

async def greet_user(graph: Graph):
    user = await graph.get_user()
    if user:
        print('Hello,', user.display_name)
        # For Work/school accounts, email is in mail property
        # Personal accounts, email is in userPrincipalName
        print('Email:', user.mail or user.user_principal_name, '\n')

async def display_access_token(graph: Graph):
    token = await graph.get_user_token()
    print('User token:', token, '\n')

async def list_inbox(graph: Graph):
    # TODO
    return

async def send_mail(graph: Graph):
    # TODO
    return

async def make_graph_call(graph: Graph):
    # TODO
    return

async def list_calendars(graph: Graph):
    result = await graph.get_calendars()
    print(result)

async def create_event(list_events: list[dict], graph: Graph):
    """
    {
        "title": "title",
        "date": "6 de Octubre 10:00 a.m.",
        "speaker": "Key Speakers",
        "link": null
    }
    """
    for event in list_events:
        print(f"Creando evento: {event.get('title')}")
        month, date, hour, minute, end_hour = parse_event_date(event.get("date")) # type: ignore

        request_body = Event(
            subject = event.get("title"),
            body = ItemBody(
                content_type = BodyType.Html,
                content = event.get("title") + "\n   " + event.get("date") + "\n   " + event.get("speaker"), # type: ignore
            ),
            start = DateTimeTimeZone(
                #date_time = "2019-03-15T12:00:00",
                date_time = f"2025-{month}-{date}T{hour}:{minute}:00",
                time_zone = "Central Standard Time (Mexico)",
            ),
            end = DateTimeTimeZone(
                date_time = f"2025-{month}-{date}T{end_hour}:{minute}:00",
                time_zone = "Central Standard Time (Mexico)",
            ),
            location = Location(
                display_name = "Webex",
            )
        )
        result = await graph.create_Event(request_body)
        print(result)

asyncio.run(main())