"""
    Este archivo contiene las funciones que permite ejecutar comandos a
    MicrosoftGraph para interactuar con las funciones de la cuenta de
    Microsoft Outlook
"""

from configparser import SectionProxy
from urllib.parse import quote, urlencode
from azure.identity import DeviceCodeCredential
from msgraph.graph_service_client import GraphServiceClient
from msgraph.generated.models.event import Event
from msgraph.generated.models.event_collection_response import EventCollectionResponse
from msgraph.generated.users.item.user_item_request_builder import (
    UserItemRequestBuilder,
)
from kiota_abstractions.base_request_configuration import RequestConfiguration

from auth import MSALCredential


class Graph:
    """Clase para interactuar con Microsoft Graph."""
    settings: SectionProxy
    device_code_credential: DeviceCodeCredential
    user_client: GraphServiceClient
    msal_credential: MSALCredential

    def __init__(self, config: SectionProxy):
        self.settings = config
        self.client_id = self.settings["clientId"]
        self.tenant_id = self.settings["tenantId"]
        self.graph_scopes = self.settings["graphUserScopes"].split(" ")

        authority = None
        if self.tenant_id and self.tenant_id.lower() == "consumers":
            authority = "https://login.microsoftonline.com/consumers"
        elif self.tenant_id:
            authority = f"https://login.microsoftonline.com/{self.tenant_id}"

        # con auth persistente
        self.msal_credential = MSALCredential(
            client_id=self.client_id,
            authority=authority,
            default_scopes=self.graph_scopes,
        )
        # GraphServiceClient acepta un TokenCredential-like; pasamos la MSALCredential
        self.user_client = GraphServiceClient(self.msal_credential, self.graph_scopes)

        # sin auth persistente
        # self.device_code_credential = DeviceCodeCredential(
        # self.client_id,
        # tenant_id = self.tenant_id
        # )
        # self.user_client = GraphServiceClient(self.device_code_credential, self.graph_scopes)

    async def get_user_token(self):
        """Permite obtener el token del cliente para esta aplicación

        Returns:
            str: access token
        """
        # con auth
        access_token = self.msal_credential.get_token(self.settings['graphUserScopes'])
        return access_token.token
        # sin auth
        # graph_scopes = self.settings["graphUserScopes"]
        # access_token = self.device_code_credential.get_token(graph_scopes)
        # return access_token.token

    async def get_user(self):
        """Obtiene los detalles del usuario

        Returns:
            User: un objeto con los detalles del usuario
        """
        # Only request specific properties using $select
        query_params = UserItemRequestBuilder.UserItemRequestBuilderGetQueryParameters(
            select=["displayName", "mail", "userPrincipalName"]
        )

        request_config = (
            UserItemRequestBuilder.UserItemRequestBuilderGetRequestConfiguration(
                query_parameters=query_params
            )
        )

        user = await self.user_client.me.get(request_configuration=request_config)
        return user

    async def get_time_zone(self):
        """Obtiene la fecha predefinida de la cuenta
        Returns:
            SupportedTimeZonesGetResponse: objeto con la fecha
            con la qwue esta configurada la cuenta
        """
        time_zone = await self.user_client.me.outlook.supported_time_zones.get()
        return time_zone

    async def get_calendars(self):
        """Obtiene los calendarios de la cuenta

        Returns:
            CalendarCollectionResponse: regresa un objeto con los calendarios
            de la cuenta
        """
        calendars = await self.user_client.me.calendars.get()
        return calendars

    async def get_events(self, start_date: str | None = None, end_date: str | None = None):
        """Regresa los eventos que tiene el usuario en su calendario

        Returns:
            Colección de eventos del calendario.
        """
        if start_date is None and end_date is None:
            events_url = (
                "https://graph.microsoft.com/v1.0/me/calendar/events?"
                + urlencode(
                    {
                        "$select": "subject,start,end,location,id,body",
                        "$orderby": "start/dateTime",
                        "$top": 100,
                    }
                )
            )
            events = await self.user_client.me.events.with_url(events_url).get()
            return await self._get_all_event_pages(events)

        if start_date is None or end_date is None:
            raise ValueError(
                "start_date y end_date deben proporcionarse juntos para consultar calendarView."
            )

        calendar_view_url = (
            "https://graph.microsoft.com/v1.0/me/calendarView?"
            + urlencode(
                {
                    "startDateTime": start_date,
                    "endDateTime": end_date,
                    "$select": "subject,start,end,location,id,body",
                    "$orderby": "start/dateTime",
                    "$top": 100,
                }
            )
        )
        events = await self.user_client.me.calendar_view.with_url(
            calendar_view_url
        ).get(
            request_configuration=self._calendar_view_request_configuration()
        )
        return await self._get_all_event_pages(events)

    @staticmethod
    def _calendar_view_request_configuration() -> RequestConfiguration:
        request_configuration = RequestConfiguration()
        request_configuration.headers.add(
            "Prefer", 'outlook.timezone="Central Standard Time (Mexico)"'
        )
        return request_configuration

    async def _get_all_event_pages(
        self, events: EventCollectionResponse | None
    ) -> EventCollectionResponse | None:
        """Sigue @odata.nextLink y acumula todas las páginas de eventos."""
        if events is None:
            return None

        while events.odata_next_link:
            next_page = await self.user_client.me.events.with_url(
                events.odata_next_link
            ).get(
                request_configuration=self._calendar_view_request_configuration()
            )
            if next_page is None:
                raise RuntimeError("Microsoft Graph devolvió una página vacía inesperada.")

            events.value = (events.value or []) + (next_page.value or [])
            events.odata_next_link = next_page.odata_next_link

        return events

    async def update_event(self, event_id: str, event: Event):
        """Actualiza los campos proporcionados de un evento existente."""
        event_url = (
            f"https://graph.microsoft.com/v1.0/me/events/{quote(event_id, safe='')}"
        )
        return await self.user_client.me.events.by_event_id(event_id).with_url(
            event_url
        ).patch(event)

    async def create_event(self, event: Event) -> Event | None:
        """Crea un evento en el calendario predeterminado del usuario."""
        request_config = RequestConfiguration()
        request_config.headers.add(
            "Prefer", 'outlook.timezone="Central Standard Time (Mexico)"'
        )
        events_request = self.user_client.me.events.with_url(
            "https://graph.microsoft.com/v1.0/me/events"
        )
        created_event = await events_request.post(
            event, request_configuration=request_config
        )
        return created_event
