import os
import time
import msal
import platform
from azure.core.credentials import AccessToken

CACHE_FILE = os.path.join(os.path.dirname(__file__), "msal_token_cache.bin")

def find_encrypted_system():
    persistence = None
    encryption_method = "sin cifrado"
    system = platform.system()
    try:
        if system == "Windows":
            from msal_extensions import FilePersistenceWithDataProtection
            persistence = FilePersistenceWithDataProtection(CACHE_FILE)
            encryption_method = "dpapi"
        elif system == "Darwin":
            from msal_extensions import KeychainPersistence
            persistence = KeychainPersistence("nombre_de_mi_app", "MSAL token cache")
            encryption_method = "keychain"
        elif system == "Linux":
            from msal_extensions import LibsecretPersistence
            persistence = LibsecretPersistence("nombre_de_mi_app", "MSAL token cache")
            encryption_method = "libsecret"
    except Exception as e:
        print(f"Error detecting encrypted system: {e}")
    return persistence, encryption_method

class MSALCredential:
    """
    Credencial compatible con GraphServiceClient: implementa get_token(scopes...)
    Usa MSAL PublicClientApplication y persiste el token cache en CACHE_FILE.
    """
    def __init__(self, client_id: str, authority: str | None = None, default_scopes: list[str] | None = None):
        self.client_id = client_id
        self.authority = authority or "https://login.microsoftonline.com/common"
        self.default_scopes = default_scopes or []
        self._cache = msal.SerializableTokenCache()
        
        # Carga el archivo sin cifrar
        #if os.path.exists(CACHE_FILE):
        #    try:
        #        with open(CACHE_FILE, "r", encoding="utf-8") as f:
        #            self._cache.deserialize(f.read())
        #    except Exception:
        #        print("Error al deserializar el cache de tokens.")
        # Termina esa parte
        # Inicia la carga del archivo con cifrado
        self._persistence, encryption_method = find_encrypted_system()
        if os.path.exists(CACHE_FILE):
            try:
                if self._persistence:
                    data = self._persistence.load()
                    self._cache.deserialize(data)
                else:
                    # Fallback: cargar sin cifrar (no recomendado en producción)
                    with open(CACHE_FILE, "r", encoding="utf-8") as f:
                        self._cache.deserialize(f.read())
            except Exception as e:
                print(f"Error al deserializar el cache de tokens ({encryption_method}): {e}")
        # Termina la carga del archivo con cifrado
        self._app = msal.PublicClientApplication(client_id=self.client_id, authority=self.authority, token_cache=self._cache)

    def _save_cache(self):
        if self._cache.has_state_changed:
            try:
                # Con el archivo sin cifrado
                #with open(CACHE_FILE, "w", encoding="utf-8") as f:
                #    f.write(self._cache.serialize())
                # Con el archivo cifrado
                if self._persistence:
                # Usar msal-extensions para guardar cifrado
                    self._persistence.save(self._cache.serialize())
                else:
                    # Fallback: guardar sin cifrar (no recomendado en producción)
                    with open(CACHE_FILE, "w", encoding="utf-8") as f:
                        f.write(self._cache.serialize())
                # Termina archivo cifrado
            except Exception as e:
                print(f"Error guardando cache: {e}")

    def get_token(self, *scopes, **kwargs) -> AccessToken:
        # scopes puede venir como lista o strings separados; normalizar
        scopes = list(scopes) if scopes else list(self.default_scopes)
        if len(scopes) == 1 and isinstance(scopes[0], str) and " " in scopes[0]:
            # a veces se pasa "scope1 scope2"
            scopes = scopes[0].split(" ")

        # intentar silent
        accounts = self._app.get_accounts()
        result = None
        if accounts:
            try:
                result = self._app.acquire_token_silent(scopes, account=accounts[0])
            except Exception:
                result = None

        # si no hay token, iniciar device code flow (bloqueante)
        if not result or 'access_token' not in result:
            flow = self._app.initiate_device_flow(scopes=scopes)
            if "message" in flow:
                print(flow["message"])
            else:
                print("Inicie el flujo de dispositivo en la URL indicada.")
            result = self._app.acquire_token_by_device_flow(flow)  # bloqueante

        # guardar cache
        try:
            self._save_cache()
        except Exception:
            pass

        if result and 'access_token' in result:
            expires_on = int(result.get('expires_on') or (int(time.time()) + int(result.get('expires_in', 3600))))
            return AccessToken(result['access_token'], expires_on)
        raise RuntimeError("No se obtuvo access_token: " + str(result))