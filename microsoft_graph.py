"""_summary_

    Returns:
        _type_: _description_
"""

import asyncio
import configparser
from msgraph.generated.models.o_data_errors.o_data_error import ODataError
from msgraph.generated.models.event import Event
from msgraph.generated.models.item_body import ItemBody
from msgraph.generated.models.body_type import BodyType
from msgraph.generated.models.date_time_time_zone import DateTimeTimeZone
from msgraph.generated.models.location import Location
from graph import Graph

async def main():
    """_summary_
    """
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
        print('6. List events in calendar')

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
                    pass
                case 5:
                    await make_graph_call(graph)
                case 6:
                    await list_events_in_calendar(graph)
                case _:
                    print('Invalid choice!\n')
        except ODataError as odata_error:
            print('Error:')
            if odata_error.error:
                print(odata_error.error.code, odata_error.error.message)

async def greet_user(graph: Graph):
    """_summary_

    Args:
        graph (Graph): _description_
    """
    user = await graph.get_user()
    if user:
        print('Hello,', user.display_name)
        # For Work/school accounts, email is in mail property
        # Personal accounts, email is in userPrincipalName
        print('Email:', user.mail or user.user_principal_name, '\n')

async def display_access_token(graph: Graph):
    """_summary_

    Args:
        graph (Graph): _description_
    """
    token = await graph.get_user_token()
    print('User token:', token, '\n')

async def list_inbox(graph: Graph):
    """_summary_

    Args:
        graph (Graph): _description_
    """
    # TODO
    return

async def send_mail(graph: Graph):
    """_summary_

    Args:
        graph (Graph): _description_
    """
    # TODO # fixme
    return

async def make_graph_call(graph: Graph):
    """_summary_

    Args:
        graph (Graph): _description_
    """
    # TODO: aaaa
    return

async def list_events_in_calendar(graph: Graph, start_date: str | None = None, end_date: str | None = None):
    """_summary_

    Args:
        graph (Graph): _description_
    """
    result = await graph.get_events(start_date, end_date)
    if not result or not result.value:
        print("No se encontraron eventos en el calendario.")
        return []

    list_event = []
    for event in result.value:
        start = event.start.date_time if event.start else "Sin fecha"
        print(f"Título: {event.subject or '(sin título)'}")
        print(f"Fecha: {start}")
        print(f"ID: {event.id}")
        print("-" * 40)
        list_event.append({"titulo": event.subject, ""})

async def actualizar_eventos(graph: Graph, event_body: Event, event_id):
    """_summary_

    Args:
        graph (Graph): _description_
        list_events (list[dict]): _description_
    """
    result = await graph.update_event(event_id, event_body)
    print(result)

async def create_event(event_body: Event, graph: Graph):
    """
    {
        "titulo": "title",
        "fecha": "6 de Octubre 10:00 a.m.",
        "ponente": "Key Speakers",
        "tipo": "tipo",
        "nivel": nivel,
        ""
    }
    """
    result = await graph.create_event(event_body)
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
