"""Cliente mínimo de Microsoft Graph: lista todos los archivos de la carpeta de un caso.

Solo lee. Dos modos de autenticación, elegidos por el `.env`:
- Delegado (sin GRAPH_CLIENT_SECRET): entra como el usuario y ve lo mismo que él. La
  primera vez abre el navegador; después usa el token guardado en GRAPH_TOKEN_CACHE.
- Aplicación (con GRAPH_CLIENT_SECRET): credenciales de la app registration.
"""

import logging
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from urllib.parse import quote

import msal
import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"
ALCANCES_DELEGADOS = ["Sites.Read.All"]
# Solo para aplicar un plan de revisión (renombrar, mover, crear carpetas).
ALCANCES_ESCRITURA = ["Sites.ReadWrite.All"]
ALCANCES_APLICACION = ["https://graph.microsoft.com/.default"]
TIMEOUT_SEGUNDOS = 60
MAX_INTENTOS = 6
ESPERA_MAXIMA_SEGUNDOS = 60
CAMPOS_ITEM = "id,name,size,folder,file,webUrl,lastModifiedDateTime"
ELEMENTOS_POR_PAGINA = 999
ESTADOS_REINTENTABLES = {HTTPStatus.TOO_MANY_REQUESTS, HTTPStatus.SERVICE_UNAVAILABLE}
# Los casos se llaman '<cliente> - [Closed - ]<número> - <índice>'.
SEPARADOR_CASO = " - "
ESTADOS_DE_CASO = {"closed", "open", "active"}
LARGO_MINIMO_NUMERO_CASO = 5


class SharePointError(RuntimeError):
    """Fallo al hablar con SharePoint."""


class SharePointNoConfiguradoError(SharePointError):
    """Faltan GRAPH_TENANT_ID / GRAPH_CLIENT_ID en el `.env`."""


class CasoNoEncontradoError(SharePointError):
    """La carpeta del caso no existe en SharePoint."""


class ConflictoError(SharePointError):
    """Ya existe un elemento con ese nombre en la carpeta (HTTP 409)."""


class SoloLecturaError(SharePointError):
    """Se intentó escribir con un cliente creado en modo lectura."""


@dataclass(frozen=True)
class ArchivoSharePoint:
    id: str
    carpeta: str  # relativa a la carpeta del caso; "" es la raíz del caso
    nombre: str
    tamano_bytes: int
    hash: str  # quickXorHash
    url: str

    @property
    def ruta(self) -> str:
        return f"{self.carpeta}/{self.nombre}" if self.carpeta else self.nombre


class ClienteGraph:
    def __init__(self, escritura: bool = False) -> None:
        if not (settings.GRAPH_TENANT_ID and settings.GRAPH_CLIENT_ID):
            raise SharePointNoConfiguradoError(
                "Faltan GRAPH_TENANT_ID y GRAPH_CLIENT_ID en el .env (ver .env.example)."
            )
        self._candado = threading.Lock()
        self._token: str | None = None
        self._drive_id: str | None = None
        self._casos: dict[str, str] | None = None
        self._sesion = requests.Session()
        self._app: msal.ClientApplication | None = None
        self._cache: msal.SerializableTokenCache | None = None
        self._escritura = escritura
        self._alcances = ALCANCES_ESCRITURA if escritura else ALCANCES_DELEGADOS

    # ------------------------------------------------------------------ autenticación

    def _aplicacion_msal(self) -> msal.ClientApplication:
        """Se crea al pedir el primer token: MSAL consulta a Microsoft al construirse."""
        if self._app is not None:
            return self._app
        autoridad = f"https://login.microsoftonline.com/{settings.GRAPH_TENANT_ID}"
        if settings.GRAPH_CLIENT_SECRET:
            self._app = msal.ConfidentialClientApplication(
                settings.GRAPH_CLIENT_ID,
                authority=autoridad,
                client_credential=settings.GRAPH_CLIENT_SECRET,
            )
        else:
            self._cache = msal.SerializableTokenCache()
            if settings.GRAPH_TOKEN_CACHE.exists():
                self._cache.deserialize(settings.GRAPH_TOKEN_CACHE.read_text(encoding="utf-8"))
            self._app = msal.PublicClientApplication(
                settings.GRAPH_CLIENT_ID, authority=autoridad, token_cache=self._cache
            )
        return self._app

    def _pedir_token(self) -> dict:
        app = self._aplicacion_msal()
        if isinstance(app, msal.ConfidentialClientApplication):
            return app.acquire_token_for_client(scopes=ALCANCES_APLICACION)
        cuentas = app.get_accounts()
        if cuentas:
            resultado = app.acquire_token_silent(self._alcances, account=cuentas[0])
            if resultado:
                return resultado
        logger.warning("Abriendo el navegador: elige tu cuenta de @petroffamshen.com.")
        return app.acquire_token_interactive(scopes=self._alcances, prompt="select_account")

    def _obtener_token(self, renovar: bool = False) -> str:
        with self._candado:
            if self._token and not renovar:
                return self._token
            resultado = self._pedir_token()
            if "access_token" not in resultado:
                raise SharePointError(
                    f"No se pudo iniciar sesión en Microsoft: {resultado.get('error')}: "
                    f"{resultado.get('error_description')}"
                )
            if self._cache is not None and self._cache.has_state_changed:
                settings.GRAPH_TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
                settings.GRAPH_TOKEN_CACHE.write_text(self._cache.serialize(), encoding="utf-8")
            self._token = resultado["access_token"]
            return self._token

    # ------------------------------------------------------------------ HTTP

    def _pedir(self, metodo: str, url: str, cuerpo: dict | None = None) -> dict:
        """Llamada a Graph con reintentos ante throttling y un token renovado ante 401."""
        destino = url if url.startswith("http") else f"{GRAPH}{url}"
        renovar = False
        for intento in range(MAX_INTENTOS):
            cabeceras = {"Authorization": f"Bearer {self._obtener_token(renovar)}"}
            respuesta = self._sesion.request(
                metodo, destino, headers=cabeceras, json=cuerpo, timeout=TIMEOUT_SEGUNDOS
            )
            renovar = False
            if respuesta.ok:
                return respuesta.json() if respuesta.content else {}
            if respuesta.status_code == HTTPStatus.UNAUTHORIZED:
                renovar = True
            elif respuesta.status_code in ESTADOS_REINTENTABLES:
                espera = int(respuesta.headers.get("Retry-After", 2**intento))
                time.sleep(min(espera, ESPERA_MAXIMA_SEGUNDOS))
            else:
                _lanzar(respuesta, destino)
        raise SharePointError(f"Graph no respondió tras {MAX_INTENTOS} intentos: {destino}")

    def _get(self, url: str) -> dict:
        return self._pedir("GET", url)

    def _escribir(self, metodo: str, url: str, cuerpo: dict | None) -> dict:
        if not self._escritura:
            raise SoloLecturaError("Este cliente es de solo lectura: créalo con escritura=True.")
        return self._pedir(metodo, url, cuerpo)

    # ------------------------------------------------------------------ carpetas

    def _drive(self) -> str:
        if self._drive_id is None:
            sitio = self._get(f"/sites/{settings.SHAREPOINT_SITIO}")
            self._drive_id = self._get(f"/sites/{sitio['id']}/drive")["id"]
        return self._drive_id

    def _hijos(self, item_id: str) -> list[dict]:
        url = (
            f"/drives/{self._drive()}/items/{item_id}/children"
            f"?$top={ELEMENTOS_POR_PAGINA}&$select={CAMPOS_ITEM}"
        )
        hijos: list[dict] = []
        while url:
            pagina = self._get(url)
            hijos.extend(pagina["value"])
            url = pagina.get("@odata.nextLink", "")
        return hijos

    # ------------------------------------------------------------------ escritura

    def obtener(self, item_id: str) -> dict:
        """El elemento con su nombre y su carpeta padre (parentReference.id)."""
        return self._get(
            f"/drives/{self._drive()}/items/{item_id}?$select=id,name,parentReference,folder"
        )

    def hijos(self, item_id: str) -> list[dict]:
        return self._hijos(item_id)

    def eliminar(self, item_id: str) -> None:
        """Manda el elemento a la papelera de reciclaje del sitio (no es un borrado definitivo)."""
        self._escribir("DELETE", f"/drives/{self._drive()}/items/{item_id}", None)

    def renombrar(self, item_id: str, nombre: str) -> dict:
        return self._escribir(
            "PATCH",
            f"/drives/{self._drive()}/items/{item_id}",
            {"name": nombre, "@microsoft.graph.conflictBehavior": "fail"},
        )

    def mover(self, item_id: str, padre_id: str) -> dict:
        """Mueve dentro de la misma biblioteca: el id y el historial de versiones se conservan."""
        return self._escribir(
            "PATCH",
            f"/drives/{self._drive()}/items/{item_id}",
            {"parentReference": {"id": padre_id}, "@microsoft.graph.conflictBehavior": "fail"},
        )

    def crear_carpeta(self, padre_id: str, nombre: str) -> tuple[str, bool]:
        """(id, creada). Si ya existe una carpeta con ese nombre, devuelve la existente."""
        existente = next(
            (h for h in self._hijos(padre_id) if h["name"].casefold() == nombre.casefold()), None
        )
        if existente is not None:
            return existente["id"], False
        nueva = self._escribir(
            "POST",
            f"/drives/{self._drive()}/items/{padre_id}/children",
            {"name": nombre, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"},
        )
        return nueva["id"], True

    def descargar(self, item_id: str) -> bytes:
        """El contenido de un archivo, en memoria, con los mismos reintentos que _pedir."""
        destino = f"{GRAPH}/drives/{self._drive()}/items/{item_id}/content"
        renovar = False
        for intento in range(MAX_INTENTOS):
            cabeceras = {"Authorization": f"Bearer {self._obtener_token(renovar)}"}
            respuesta = self._sesion.get(destino, headers=cabeceras, timeout=TIMEOUT_SEGUNDOS)
            renovar = False
            if respuesta.ok:
                return respuesta.content
            if respuesta.status_code == HTTPStatus.UNAUTHORIZED:
                renovar = True
            elif respuesta.status_code in ESTADOS_REINTENTABLES:
                espera = int(respuesta.headers.get("Retry-After", 2**intento))
                time.sleep(min(espera, ESPERA_MAXIMA_SEGUNDOS))
            else:
                _lanzar(respuesta, item_id)
        raise SharePointError(f"No se pudo descargar {item_id} tras {MAX_INTENTOS} intentos")

    def hijos_de_ruta(self, ruta: str) -> list[dict]:
        """Los elementos de una carpeta de la biblioteca, por su ruta ('JSONL/Casos_rafael')."""
        carpeta = self._get(f"/drives/{self._drive()}/root:/{quote(ruta)}")
        return self._hijos(carpeta["id"])

    def carpetas_de_casos(self) -> dict[str, str]:
        return self._carpetas_de_casos()

    def _carpetas_de_casos(self) -> dict[str, str]:
        """{nombre: id} de cada carpeta de caso en SHAREPOINT_CARPETA_CASOS. Se pide una vez."""
        if self._casos is None:
            ruta = quote(settings.SHAREPOINT_CARPETA_CASOS)
            raiz = self._get(f"/drives/{self._drive()}/root:/{ruta}")
            self._casos = {h["name"]: h["id"] for h in self._hijos(raiz["id"]) if "folder" in h}
        return self._casos

    def resolver_caso(self, caso: str) -> str:
        """El nombre con que está la carpeta del caso en SharePoint.

        Un caso cambia de nombre al cerrarse ('Alvarez, Brianna - 400029 - 0' pasa a
        'Alvarez, Brianna - Closed - 400029 - 0'), así que si no está el nombre exacto se
        busca sin el estado y, si no, por el número del caso. Solo se acepta si hay UNA
        carpeta que encaje: con dos o más no se adivina.
        """
        carpetas = self._carpetas_de_casos()
        if caso in carpetas:
            return caso
        for clave in (_sin_estado, _numero_de_caso):
            buscada = clave(caso)
            candidatas = [n for n in carpetas if buscada and clave(n) == buscada]
            if len(candidatas) == 1:
                return candidatas[0]
            if len(candidatas) > 1:
                raise CasoNoEncontradoError(
                    f"No existe la carpeta '{caso}' y hay varias parecidas: "
                    + "; ".join(sorted(candidatas))
                )
        raise CasoNoEncontradoError(
            f"No existe la carpeta '{caso}' en {settings.SHAREPOINT_CARPETA_CASOS}/"
        )

    def listar_caso(self, caso: str) -> list[ArchivoSharePoint]:
        """Todos los archivos de la carpeta del caso, recorriendo todas sus subcarpetas.

        `caso` es el nombre exacto de la carpeta (ver resolver_caso).
        """
        carpetas = self._carpetas_de_casos()
        if caso not in carpetas:
            raise CasoNoEncontradoError(
                f"No existe la carpeta '{caso}' en {settings.SHAREPOINT_CARPETA_CASOS}/"
            )

        return self.listar_carpeta(carpetas[caso])

    def listar_carpeta(self, carpeta_id: str) -> list[ArchivoSharePoint]:
        """Todos los archivos bajo una carpeta, por su id, recorriendo sus subcarpetas."""
        archivos: list[ArchivoSharePoint] = []
        pendientes = [(carpeta_id, "")]
        while pendientes:
            item_id, carpeta = pendientes.pop()
            for hijo in self._hijos(item_id):
                if "folder" in hijo:
                    subcarpeta = f"{carpeta}/{hijo['name']}" if carpeta else hijo["name"]
                    pendientes.append((hijo["id"], subcarpeta))
                else:
                    archivos.append(_archivo_desde_item(hijo, carpeta))
        return archivos


def _partes(caso: str) -> list[str]:
    return [p.strip() for p in caso.split(SEPARADOR_CASO) if p.strip()]


def _sin_estado(caso: str) -> str:
    """'Alvarez, Brianna - Closed - 400029 - 0' -> 'alvarez, brianna - 400029 - 0'."""
    partes = [p for p in _partes(caso) if p.casefold() not in ESTADOS_DE_CASO]
    return SEPARADOR_CASO.join(partes).casefold()


def _numero_de_caso(caso: str) -> str:
    """El número del caso: la primera parte solo de dígitos y con largo de número."""
    return next(
        (p for p in _partes(caso) if p.isdigit() and len(p) >= LARGO_MINIMO_NUMERO_CASO), ""
    )


def _lanzar(respuesta: requests.Response, destino: str) -> None:
    if respuesta.status_code == HTTPStatus.NOT_FOUND:
        raise CasoNoEncontradoError(f"No existe en SharePoint: {destino}")
    if respuesta.status_code == HTTPStatus.CONFLICT:
        raise ConflictoError(f"Ya existe un elemento con ese nombre: {respuesta.text[:200]}")
    raise SharePointError(f"Graph respondió {respuesta.status_code}: {respuesta.text[:200]}")


def _archivo_desde_item(item: dict, carpeta: str) -> ArchivoSharePoint:
    hashes = (item.get("file") or {}).get("hashes") or {}
    return ArchivoSharePoint(
        id=item["id"],
        carpeta=carpeta,
        nombre=item["name"],
        tamano_bytes=int(item.get("size") or 0),
        hash=hashes.get("quickXorHash", ""),
        url=item.get("webUrl", ""),
    )
