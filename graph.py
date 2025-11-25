from configparser import SectionProxy
from azure.identity import DeviceCodeCredential
from msgraph import GraphServiceClient
from msgraph.generated.users.item.user_item_request_builder import UserItemRequestBuilder
from kiota_abstractions.base_request_configuration import RequestConfiguration

from auth import MSALCredential

class Graph:
    settings: SectionProxy
    device_code_credential: DeviceCodeCredential
    user_client: GraphServiceClient
    msal_credential: MSALCredential

    def __init__(self, config: SectionProxy):
        self.settings = config
        self.client_id = self.settings['clientId']
        self.tenant_id = self.settings['tenantId']
        self.graph_scopes = self.settings['graphUserScopes'].split(' ')

        authority = None
        if self.tenant_id and self.tenant_id.lower() == 'consumers':
            authority = "https://login.microsoftonline.com/consumers"
        elif self.tenant_id:
            authority = f"https://login.microsoftonline.com/{self.tenant_id}"


        # con auth persistente
        self.msal_credential = MSALCredential(client_id=self.client_id, authority=authority, default_scopes=self.graph_scopes)
        # GraphServiceClient acepta un TokenCredential-like; pasamos la MSALCredential
        self.user_client = GraphServiceClient(self.msal_credential, self.graph_scopes)

        # sin auth persistente
        #self.device_code_credential = DeviceCodeCredential(self.client_id, tenant_id = self.tenant_id)
        #self.user_client = GraphServiceClient(self.device_code_credential, self.graph_scopes)
    
    async def get_user_token(self):
        # con auth
        #access_token = self.msal_credential.get_token(self.settings['graphUserScopes'])
        #return access_token.token
        # sin auth
        graph_scopes = self.settings['graphUserScopes']
        access_token = self.device_code_credential.get_token(graph_scopes)
        return access_token.token
    
    async def get_user(self):
        # Only request specific properties using $select
        query_params = UserItemRequestBuilder.UserItemRequestBuilderGetQueryParameters(
            select=['displayName', 'mail', 'userPrincipalName']
        )

        request_config = UserItemRequestBuilder.UserItemRequestBuilderGetRequestConfiguration(
            query_parameters=query_params
        )

        user = await self.user_client.me.get(request_configuration=request_config)
        return user
    
    async def get_time_zone(self):
        time_zone = await self.user_client.me.outlook.supported_time_zones.get()
        return time_zone
    
    async def get_calendars(self):
        calendars = await self.user_client.me.calendars.get()
        return calendars

    
    async def create_Event(self, event):
        request_config = RequestConfiguration()
        request_config.headers.add("Prefer", "outlook.timezone=\"Central Standard Time (Mexico)\"")
        created_event = await self.user_client.me.events.post(event, request_configuration=request_config)
        return created_event