# -*- coding: utf-8 -*-
"""
api_deportes.py
Obtiene los proximos partidos de futbol via TheSportsDB (gratis, sin
necesidad de registrarse ni de API key) - la misma API que ya usa el
bot de Discord de Sebi para estas mismas competiciones.
"""

import json
import os
import time
import unicodedata
from datetime import datetime, timedelta
from difflib import SequenceMatcher

import requests

try:
    from zoneinfo import ZoneInfo
    TZ_UTC = ZoneInfo("UTC")
    TZ_ARG = ZoneInfo("America/Argentina/Buenos_Aires")
except Exception:
    TZ_UTC = None
    TZ_ARG = None

TSDB_KEY = "3"  # key publica de test de TheSportsDB, no requiere registro
BASE_URL = f"https://www.thesportsdb.com/api/v1/json/{TSDB_KEY}"

# Escudos que Sebi cargo a mano (equipos chicos que ninguna API tiene)
# y subio con el "Subidor de Escudos" a esta carpeta del propio repo.
# Se prueban como ultimo recurso, antes de rendirse e ir al icono
# generico.
GITHUB_OWNER = "squiven"
GITHUB_REPO = "futbol-recordatorios-papa"
GITHUB_BRANCH = "main"
ESCUDOS_MANUALES_BASE = (f"https://raw.githubusercontent.com/{GITHUB_OWNER}/"
                          f"{GITHUB_REPO}/{GITHUB_BRANCH}/escudos_manuales")

# Mismo mecanismo que escudos_manuales/, pero para el logo de cada
# competicion (Liga Profesional, Libertadores, etc). Se prueba solo si
# TheSportsDB no tiene el escudo de esa liga cargado.
LOGOS_LIGA_MANUALES_BASE = (f"https://raw.githubusercontent.com/{GITHUB_OWNER}/"
                             f"{GITHUB_REPO}/{GITHUB_BRANCH}/logos_competiciones_manuales")

# Cache separada (archivo aparte) para el canal de TV de cada partido
# puntual -- a diferencia de los escudos (que son por equipo y no
# cambian nunca), el canal es por PARTIDO, asi que se cachea por ID de
# evento y solo tiene sentido mientras ese partido siga en la lista de
# proximos partidos.
CANALES_TV_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "canales_tv_cache.json")

# Grilla de Telecentro (nombre de canal -> numero), cargada una sola
# vez. La arma y actualiza Sebi a mano editando canales_telecentro.json
# en el repo -- no hay forma automatica de sacar esto de ninguna API.
CANALES_TELECENTRO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "canales_telecentro.json")

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
ESPN_LIGAS = {
    "liga_argentina": "arg.1",
    "copa_argentina": "arg.copa",
    "libertadores": "conmebol.libertadores",
    "sudamericana": "conmebol.sudamericana",
    "mls": "usa.1",
    "champions": "uefa.champions",
}

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
ESCUDOS_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "escudos_cache.json")

# IDs de TheSportsDB para las competiciones que le interesan a papa.
# Son los mismos IDs que ya estan probados y funcionando en el bot de
# Discord (burdel-bot), asi que no dependen de una busqueda ambigua.
LIGAS = [
    {"clave": "liga_argentina", "ids": ["4406", "5342"], "nombre_visible": "Liga Profesional Argentina"},
    {"clave": "copa_argentina", "ids": ["4960"], "nombre_visible": "Copa Argentina"},
    {"clave": "libertadores", "ids": ["4144"], "nombre_visible": "Copa Libertadores"},
    {"clave": "sudamericana", "ids": ["4145"], "nombre_visible": "Copa Sudamericana"},
    {"clave": "mls", "ids": ["4346"], "nombre_visible": "MLS (Inter Miami)"},
    {"clave": "champions", "ids": ["4480"], "nombre_visible": "Champions League"},
]

# Para poder ir del nombre visible de la competicion (el que ya trae
# cada partido armado) a sus IDs de TheSportsDB, sin tener que guardar
# ese ID en cada partido por separado.
_LIGA_POR_NOMBRE = {liga["nombre_visible"]: liga for liga in LIGAS}

# Equipos que se destacan sin importar la competicion (amistosos, etc
# incluidos). A diferencia de LIGAS, aca se busca por equipo, no por
# torneo, asi no importa en que competicion jueguen.
EQUIPOS_DESTACADOS = [
    {"clave": "boca", "id": "135156", "nombre_visible": "Boca Juniors"},
    {"clave": "seleccion", "id": "134509", "nombre_visible": "Selecci\u00f3n Argentina"},
]

# Para algunas competiciones solo interesa un equipo puntual, no toda
# la liga (ej: de la MLS solo importa cuando juega el Inter Miami).
FILTRO_EQUIPO = {
    "mls": "inter miami",
}


def cargar_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def resolver_ligas(config, log=print):
    """
    Ya no hace falta buscar nada en una API: los IDs de TheSportsDB
    estan fijos y probados de antemano. Se deja esta funcion (no hace
    ningun pedido) solo para no romper como la llama app.py.
    """
    for liga in LIGAS:
        log(f"[OK] {liga['nombre_visible']} -> id(s) TheSportsDB {', '.join(liga['ids'])}")
    return LIGAS


def _pedir(url, params, log, contexto, intentos=3):
    """
    Hace un pedido GET con reintentos si la API responde 429 (demasiados
    pedidos). Siempre hace una pausa chica antes de devolver, para no
    encadenar pedidos demasiado rapido y volver a chocar con el limite.
    """
    resultado = None
    for intento in range(intentos):
        try:
            r = requests.get(url, params=params, timeout=15)
        except Exception as e:
            log(f"[ERROR] {contexto}: {e}")
            break

        if r.status_code == 429:
            espera = 3 * (intento + 1)
            log(f"[AVISO] {contexto}: demasiados pedidos seguidos, esperando {espera}s...")
            time.sleep(espera)
            continue

        try:
            r.raise_for_status()
            resultado = r.json()
        except Exception as e:
            log(f"[ERROR] {contexto}: {e}")
        break

    time.sleep(1.2)  # pausa entre pedidos para no volver a chocar con el limite
    return resultado


_cache_escudos = {}
_cache_escudos_wikidata = {}


def _cargar_cache_escudos_disco():
    """
    Cache PERSISTENTE (en un archivo aparte, no se sube a GitHub) de
    escudos ya encontrados. Es la forma real de no chocar todo el
    tiempo con los limites de las APIs gratuitas: una vez que se
    encuentra el escudo de un equipo, no hace falta volver a
    preguntarle a nadie nunca mas por ese mismo equipo. Solo se
    guardan los que SI se encontraron -- los que fallaron se vuelven a
    intentar en el proximo refresco, por si el fallo fue solo por
    limite de pedidos y no porque el equipo realmente no tenga escudo
    en ningun lado.
    """
    try:
        with open(ESCUDOS_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _guardar_cache_escudos_disco():
    try:
        with open(ESCUDOS_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_cache_escudos_disco, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


_cache_escudos_disco = _cargar_cache_escudos_disco()


def _cargar_cache_canales_tv():
    try:
        with open(CANALES_TV_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _guardar_cache_canales_tv():
    try:
        with open(CANALES_TV_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_cache_canales_tv, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


_cache_canales_tv = _cargar_cache_canales_tv()


def _cargar_grilla_telecentro():
    try:
        with open(CANALES_TELECENTRO_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


_GRILLA_TELECENTRO = _cargar_grilla_telecentro()


def _numero_telecentro(nombre_canal):
    """Busca el numero de Telecentro para un nombre de canal, tolerando
    variaciones chicas (mayusculas, espacios de mas, HD pegado o no)
    contra la grilla cargada en canales_telecentro.json."""
    if not nombre_canal:
        return None
    objetivo = _texto_normalizado(nombre_canal)
    for nombre, numero in _GRILLA_TELECENTRO.items():
        if _texto_normalizado(nombre) == objetivo:
            return numero[0] if isinstance(numero, list) else numero
    return None

WIKIMEDIA_HEADERS = {
    # Wikidata/Wikimedia exige un User-Agent descriptivo (y a veces es
    # mas estricto todavia con clientes que no se identifican bien).
    "User-Agent": "FutbolYRecordatorios/1.0 (app de escritorio de uso personal; "
                   "contacto: uso-personal@localhost)"
}


def _pedir_wikidata(params, log, contexto):
    """Igual que _pedir, pero para la API de Wikidata. A diferencia de
    TheSportsDB, ac\u00e1 NO conviene reintentar con esperas largas: el
    limite de Wikidata resulto ser lo bastante estricto como para que
    insistir simplemente alargue el ciclo varios minutos sin mejorar
    mucho la tasa de exito. Mejor un solo intento rapido y, si falla,
    pasarle la posta enseguida a Wikipedia (la siguiente fuente)."""
    try:
        r = requests.get("https://www.wikidata.org/w/api.php", params=params,
                          headers=WIKIMEDIA_HEADERS, timeout=8)
        if r.status_code == 429:
            log(f"[AVISO] {contexto}: Wikidata esta al limite de pedidos "
                f"ahora mismo, se prueba directo con Wikipedia.")
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log(f"[AVISO] {contexto}: {e}")
        return None
    finally:
        time.sleep(0.3)


def _escudo_wikidata(nombre_equipo, log):
    """
    Segunda fuente de escudos, para equipos que TheSportsDB no tiene
    (le pasa con clubes chicos: rondas previas de la Champions, equipos
    de ligas sudamericanas menores, etc). Busca el equipo en Wikidata y
    usa su propiedad "logo image" (P154), que es especificamente el
    escudo/logo (no una foto cualquiera del club).

    El nombre de un equipo suele ser ambiguo en Wikidata (ej: "Lyon" es
    ante todo la ciudad francesa, no el club; "NEC" es tambien una
    marca de electronica) asi que se piden varios resultados y se
    prioriza el que tenga pinta de club de futbol segun su
    descripcion, en vez de quedarse a ciegas con el primero.
    """
    if not nombre_equipo or nombre_equipo == "?":
        return None
    if nombre_equipo in _cache_escudos_wikidata:
        return _cache_escudos_wikidata[nombre_equipo]

    _cache_escudos_wikidata[nombre_equipo] = None  # por si algo falla a mitad de camino

    qid = _buscar_qid_club(nombre_equipo, log)
    if not qid:
        return None

    datos2 = _pedir_wikidata(
        {"action": "wbgetclaims", "entity": qid, "property": "P154", "format": "json"},
        log, f"escudo (wikidata, logo) {nombre_equipo}",
    )
    claims = ((datos2.get("claims") if datos2 else None) or {}).get("P154")
    if not claims:
        return None

    try:
        archivo = claims[0]["mainsnak"]["datavalue"]["value"]
    except (KeyError, IndexError):
        return None

    archivo = archivo.replace(" ", "_")
    url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{archivo}?width=200"
    _cache_escudos_wikidata[nombre_equipo] = url
    return url


_cache_escudos_wikipedia = {}


def _escudo_wikipedia(nombre_equipo, log):
    """
    Tercera fuente de escudos. Distinta a Wikidata (otro endpoint dentro
    de Wikimedia, con limites de pedidos bastante mas generosos en la
    practica) asi que sirve de red de contencion cuando Wikidata no
    tiene el equipo cargado o esta frenando por limite de pedidos.
    Busca el articulo de Wikipedia del equipo y usa la imagen principal
    del articulo -- en la gran mayoria de los clubes de futbol esa
    imagen ES el escudo (asi arma el infobox Wikipedia), aunque no hay
    garantia absoluta como con el campo "logo" especifico de Wikidata.
    """
    if not nombre_equipo or nombre_equipo == "?":
        return None
    if nombre_equipo in _cache_escudos_wikipedia:
        return _cache_escudos_wikipedia[nombre_equipo]

    _cache_escudos_wikipedia[nombre_equipo] = None

    try:
        r = requests.get(
            "https://es.wikipedia.org/w/api.php",
            params={"action": "query", "generator": "search",
                    "gsrsearch": f"{nombre_equipo} club de futbol",
                    "gsrlimit": 1, "prop": "pageimages", "piprop": "thumbnail",
                    "pithumbsize": 200, "format": "json"},
            headers=WIKIMEDIA_HEADERS, timeout=8,
        )
        r.raise_for_status()
        paginas = ((r.json().get("query") or {}).get("pages")) or {}
        for pagina in paginas.values():
            thumb = (pagina.get("thumbnail") or {}).get("source")
            if thumb:
                _cache_escudos_wikipedia[nombre_equipo] = thumb
                return thumb
    except Exception as e:
        log(f"[AVISO] Wikipedia no tenia imagen para '{nombre_equipo}': {e}")

    time.sleep(0.3)
    return None


def _escudo_manual(nombre_equipo, log):
    """
    Ultimo fallback antes del icono generico: escudos que Sebi cargo a
    mano y subio a escudos_manuales/ en el repo (con el "Subidor de
    Escudos", una herramienta aparte que corre solo en su PC). Se
    prueba con un pedido HEAD liviano -- si el archivo esta, se usa esa
    URL y despues, como con Wikidata/Wikipedia, queda cacheada en disco
    para no volver a preguntar nunca mas por ese equipo.
    """
    if not nombre_equipo or nombre_equipo == "?":
        return None
    clave = clave_archivo_escudo(nombre_equipo)
    url = f"{ESCUDOS_MANUALES_BASE}/{clave}.png"
    try:
        r = requests.head(url, timeout=6)
        if r.status_code == 200:
            return url
    except Exception as e:
        log(f"[AVISO] escudo manual '{nombre_equipo}': {e}")
    return None


def _logo_liga_manual(nombre_competicion, log):
    """Mismo mecanismo que _escudo_manual, pero para logos de
    competicion subidos a mano a logos_competiciones_manuales/ en el
    repo (mismo workflow de arrastrar-y-soltar en GitHub que ya usa
    Sebi para todo lo demas). En la practica va a hacer falta poco:
    TheSportsDB tiene bien cargados los escudos de las competiciones
    grandes que sigue la app."""
    if not nombre_competicion:
        return None
    clave = clave_archivo_escudo(nombre_competicion)
    url = f"{LOGOS_LIGA_MANUALES_BASE}/{clave}.png"
    try:
        r = requests.head(url, timeout=6)
        if r.status_code == 200:
            return url
    except Exception as e:
        log(f"[AVISO] logo de competicion manual '{nombre_competicion}': {e}")
    return None


PALABRAS_CLUB = ("futbol", "football", "voetbal", "fussball", "fußball", "soccer")


def _buscar_qid_club(nombre_equipo, log):
    """Busca el nombre en Wikidata y devuelve el QID que mejor pinta
    tenga de ser un club de futbol (mirando la descripcion corta que
    ya viene en el mismo pedido de busqueda), en vez de asumir que el
    primer resultado es el correcto."""
    datos = _pedir_wikidata(
        {"action": "wbsearchentities", "search": nombre_equipo, "language": "es",
         "format": "json", "type": "item", "limit": 6},
        log, f"escudo (wikidata, busqueda) {nombre_equipo}",
    )
    if datos is None:
        # El pedido fallo de verdad (ej: choco contra el limite de
        # pedidos incluso despues de reintentar). No tiene sentido
        # insistir con una segunda busqueda ahora mismo -- mejor
        # rendirse por este equipo en este ciclo y no perder mas
        # tiempo; si vuelve a hacer falta en el proximo refresco, se
        # intenta de nuevo.
        return None

    resultados = datos.get("search") or []
    if not resultados:
        # Reintento simple: si el nombre tiene mas de una palabra (ej.
        # "NEC Nijmegen"), a veces el club en Wikidata solo tiene
        # cargada la primera ("NEC") y la busqueda completa no
        # encuentra nada. Esto solo tiene sentido si la busqueda
        # anterior SI respondio (y solo vino vacia), no si fallo por
        # limite de pedidos.
        primera_palabra = nombre_equipo.split(" ")[0]
        if primera_palabra != nombre_equipo:
            datos2 = _pedir_wikidata(
                {"action": "wbsearchentities", "search": primera_palabra,
                 "language": "es", "format": "json", "type": "item", "limit": 6},
                log, f"escudo (wikidata, busqueda 2) {nombre_equipo}",
            )
            resultados = (datos2.get("search") if datos2 else None) or []
        if not resultados:
            return None

    for r in resultados:
        descripcion = _texto_normalizado(r.get("description") or "")
        if any(palabra in descripcion for palabra in PALABRAS_CLUB):
            return r["id"]

    # Ninguna descripcion menciona futbol -- probablemente ninguno de
    # los resultados es el club (ej: solo aparecio la ciudad). Mejor
    # no arriesgarse a poner un escudo equivocado.
    return None


def _escudo_thesportsdb(team_id, log):
    """Busca el escudo de un equipo de TheSportsDB por su ID. Primero
    mira la cache en disco (para no volver a preguntar nunca mas por
    un equipo ya encontrado en una corrida anterior), despues la
    cache en memoria de esta corrida, y solo si no esta en ninguna de
    las dos hace el pedido de verdad."""
    if not team_id:
        return None
    clave_disco = f"tsdb:{team_id}"
    if clave_disco in _cache_escudos_disco:
        return _cache_escudos_disco[clave_disco]
    if team_id in _cache_escudos:
        return _cache_escudos[team_id]
    datos = _pedir(f"{BASE_URL}/lookupteam.php", {"id": team_id}, log,
                    f"escudo equipo {team_id}")
    equipos = (datos.get("teams") if datos else None) or []
    url = equipos[0].get("strTeamBadge") if equipos else None
    _cache_escudos[team_id] = url
    if url:
        _cache_escudos_disco[clave_disco] = url
        _guardar_cache_escudos_disco()
    return url


def _evento_a_partido(ev, nombre_visible, log=print):
    fecha_str = ev.get("dateEvent")
    hora_str = ev.get("strTime")
    if not fecha_str or not hora_str or hora_str in ("00:00:00", ""):
        return None
    try:
        dt = datetime.strptime(f"{fecha_str} {hora_str}", "%Y-%m-%d %H:%M:%S")
        if TZ_UTC and TZ_ARG:
            dt = dt.replace(tzinfo=TZ_UTC).astimezone(TZ_ARG)
    except Exception:
        return None

    return {
        "id": ev.get("idEvent"),
        "competicion": nombre_visible,
        "local": ev.get("strHomeTeam") or "?",
        "visitante": ev.get("strAwayTeam") or "?",
        "fecha": dt,
        "destacado": False,
        "equipo_destacado": None,
        # El escudo NO se busca aca: se busca despues, en
        # obtener_proximos_partidos, y solo para los partidos que
        # sobreviven al filtrado y al deduplicado. Buscarlo aca (por
        # cada evento crudo, incluso los que despues se descartan)
        # multiplica los pedidos y choca enseguida contra el limite de
        # pedidos por minuto de la API gratuita.
        "escudo_local": None,
        "escudo_visitante": None,
        "_tsdb_id_local": ev.get("idHomeTeam"),
        "_tsdb_id_visitante": ev.get("idAwayTeam"),
    }


def _fecha_hoy_arg():
    if TZ_ARG:
        return datetime.now(TZ_ARG).date()
    return datetime.now().date()


def _ventana_dias_utc():
    """
    Devuelve las fechas UTC (como texto) que hay que consultar para
    cubrir el dia de "hoy" en Argentina, sin importar la hora a la que
    se ejecuta el programa.

    Argentina va UTC-3, asi que segun la hora del dia el UTC "de ahora"
    puede ser el mismo dia o ya el dia siguiente al de Argentina (ej: a
    las 21hs en Argentina ya es la madrugada del dia siguiente en UTC).
    Por eso se piden ayer + hoy + mañana en UTC, y despues se filtra por
    la fecha real en horario argentino.
    """
    utc_ahora = datetime.now(TZ_UTC) if TZ_UTC else datetime.utcnow()
    return utc_ahora, sorted({
        (utc_ahora - timedelta(days=1)).strftime("%Y-%m-%d"),
        utc_ahora.strftime("%Y-%m-%d"),
        (utc_ahora + timedelta(days=1)).strftime("%Y-%m-%d"),
    })


def _proximos_por_liga(liga, log):
    """
    Pide los partidos del dia de hoy en Argentina. Como TheSportsDB
    guarda las fechas en UTC, se piden ayer/hoy/mañana en UTC (ver
    _ventana_dias_utc) para no perderse partidos por el desfasaje de
    huso horario, y despues se descartan los que no caen realmente hoy
    en horario argentino. Consulta todos los IDs de TheSportsDB
    asociados a la competicion (algunas tienen mas de uno) y descarta
    duplicados.
    """
    hoy_arg = _fecha_hoy_arg()
    _, dias_a_pedir = _ventana_dias_utc()

    filtro = FILTRO_EQUIPO.get(liga["clave"])
    partidos = []
    vistos = set()

    for liga_id in liga["ids"]:
        for dia in dias_a_pedir:
            datos = _pedir(f"{BASE_URL}/eventsday.php", {"d": dia, "l": liga_id},
                            log, f"{liga['nombre_visible']} (eventsday {dia}, id {liga_id})")
            eventos = (datos.get("events") if datos else None) or []
            log(f"    -> {liga['nombre_visible']} id {liga_id} dia {dia}: "
                f"{len(eventos)} evento(s) crudos de la API")
            for ev in eventos:
                p = _evento_a_partido(ev, liga["nombre_visible"], log)
                if not p or p["fecha"].date() != hoy_arg:
                    continue
                if filtro:
                    texto = f"{p['local']} {p['visitante']}".lower()
                    if filtro not in texto:
                        continue
                clave_dedupe = (p["local"], p["visitante"], p["fecha"])
                if clave_dedupe in vistos:
                    continue
                vistos.add(clave_dedupe)
                partidos.append(p)

    if not partidos:
        log(f"[AVISO] {liga['nombre_visible']}: sin partidos hoy.")

    return partidos


def _proximos_por_equipo(equipo, log):
    """
    Trae los proximos partidos de un equipo puntual (Boca, Seleccion
    Argentina) sin importar la competicion -- asi se cubren tambien
    amistosos, eliminatorias, torneos amistosos de verano, etc, que no
    entran en la lista fija de competiciones de LIGAS. TheSportsDB
    devuelve hasta 15 proximos eventos del equipo; se descartan los que
    no caen hoy en horario argentino.
    """
    hoy_arg = _fecha_hoy_arg()
    datos = _pedir(f"{BASE_URL}/eventsnext.php", {"id": equipo["id"]}, log,
                    f"{equipo['nombre_visible']} (proximos partidos)")
    eventos = (datos.get("events") if datos else None) or []

    partidos = []
    for ev in eventos:
        nombre_torneo = ev.get("strLeague") or "Amistoso"
        p = _evento_a_partido(ev, nombre_torneo, log)
        if not p or p["fecha"].date() != hoy_arg:
            continue
        p["destacado"] = True
        p["equipo_destacado"] = equipo["nombre_visible"]
        partidos.append(p)

    if not partidos:
        log(f"[INFO] {equipo['nombre_visible']}: sin partidos hoy.")
    else:
        log(f"[INFO] {equipo['nombre_visible']}: {len(partidos)} partido(s) hoy "
            f"(destacado).")

    return partidos


def _es_equipo_destacado(nombre_equipo_partido, nombre_destacado):
    """Comparacion ESTRICTA, solo para decidir si un partido es de Boca
    o de la Seleccion (EQUIPOS_DESTACADOS).

    A diferencia de _mismo_equipo (que se usa para unir el mismo
    partido cuando lo reportan dos fuentes con el nombre escrito un
    poco distinto, y ahi si tolera similitud aproximada), aca NUNCA se
    admite un simple parecido: 'Argentinos Juniors' no tiene que poder
    confundirse jamas con 'Boca Juniors' solo por compartir la palabra
    'Juniors' -- eso fue exactamente el bug reportado (River vs
    Argentinos Juniors quedo marcado como destacado). Solo cuenta
    nombre identico, o que uno sea substring completo del otro (asi
    'Argentina' sigue reconociendo a 'Seleccion Argentina', y 'Club
    Atletico Boca Juniors' sigue reconociendo a 'Boca Juniors')."""
    a = _texto_normalizado(nombre_equipo_partido)
    b = _texto_normalizado(nombre_destacado)
    return a == b or a in b or b in a


def _texto_normalizado(s):
    """Minusculas, sin acentos, sin espacios de mas -- para comparar
    nombres de equipo que vienen de distintas fuentes."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.lower().strip().split())


def clave_archivo_escudo(nombre_equipo):
    """
    Convierte un nombre de equipo en un nombre de archivo seguro y
    estable: minusculas, sin acentos, sin apostrofes/puntos/simbolos,
    espacios como '_'. La usan tanto api_deportes.py (para buscar en
    escudos_manuales/) como subidor_escudos.py (para subir con el
    mismo nombre) -- tiene que dar SIEMPRE el mismo resultado en los
    dos lados para un mismo equipo.
    """
    base = _texto_normalizado(nombre_equipo)
    base = "".join(c if (c.isalnum() or c == " ") else "" for c in base)
    return "_".join(base.split())


def _mismo_equipo(nombre_a, nombre_b):
    """
    ESPN y TheSportsDB no siempre nombran igual al mismo equipo (ej:
    'Gimnasia La Plata' vs 'Gimnasia y Esgrima de La Plata'). Se
    considera el mismo equipo si el nombre es identico, si uno esta
    contenido en el otro, o si son lo bastante parecidos.
    """
    a, b = _texto_normalizado(nombre_a), _texto_normalizado(nombre_b)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.6


def obtener_proximos_partidos(config, log=print, cantidad_por_liga=5):
    """
    Combina tres fuentes: ESPN y TheSportsDB por competicion, mas
    TheSportsDB por equipo (Boca, Seleccion Argentina) para agarrar
    tambien amistosos y demas partidos fuera de las competiciones
    trackeadas. El mismo partido puede aparecer por dos fuentes
    distintas (ej: Boca jugando la Libertadores) -- en ese caso no se
    duplica, se marca destacado sobre el que ya estaba.
    """
    partidos = []

    def _mismo_partido(a, b):
        if abs((a["fecha"] - b["fecha"]).total_seconds()) >= 3 * 3600:
            return False
        # Normal: mismo local y mismo visitante. Invertido: alguna
        # fuente (sobre todo el seguimiento por equipo de Boca y
        # Seleccion) a veces reporta local/visitante al reves respecto
        # a como lo trae la fuente por competicion -- si no se
        # contempla este caso, el mismo partido queda duplicado en dos
        # filas (una con el destacado marcado y otra sin marcar).
        normal = _mismo_equipo(a["local"], b["local"]) and _mismo_equipo(a["visitante"], b["visitante"])
        invertido = _mismo_equipo(a["local"], b["visitante"]) and _mismo_equipo(a["visitante"], b["local"])
        return normal or invertido

    def _agregar(lista):
        for p in lista:
            existente = next((q for q in partidos if _mismo_partido(p, q)), None)
            if existente:
                if p.get("destacado") and not existente.get("destacado"):
                    existente["destacado"] = True
                    existente["equipo_destacado"] = p.get("equipo_destacado")
                if not existente.get("escudo_local") and p.get("escudo_local"):
                    existente["escudo_local"] = p["escudo_local"]
                if not existente.get("escudo_visitante") and p.get("escudo_visitante"):
                    existente["escudo_visitante"] = p["escudo_visitante"]
                if not existente.get("_tsdb_id_local") and p.get("_tsdb_id_local"):
                    existente["_tsdb_id_local"] = p["_tsdb_id_local"]
                if not existente.get("_tsdb_id_visitante") and p.get("_tsdb_id_visitante"):
                    existente["_tsdb_id_visitante"] = p["_tsdb_id_visitante"]
                continue
            partidos.append(p)

    try:
        _agregar(_partidos_espn(log))
    except Exception as e:
        log(f"[ERROR] ESPN fallo por completo: {e}")

    for liga in LIGAS:
        _agregar(_proximos_por_liga(liga, log))

    for equipo in EQUIPOS_DESTACADOS:
        try:
            _agregar(_proximos_por_equipo(equipo, log))
        except Exception as e:
            log(f"[ERROR] {equipo['nombre_visible']} fallo por completo: {e}")

    # El seguimiento por equipo (eventsnext.php) solo devuelve partidos
    # que TODAVIA NO ARRANCARON -- apenas empieza (o termina) el
    # partido, deja de aparecer ahi, y el destacado se perdia en el
    # siguiente refresco aunque el partido siguiera en la lista por el
    # lado de la competicion. Por eso, aparte de eso, se marca
    # destacado directamente por nombre en TODOS los partidos ya
    # encontrados, sin importar el estado del partido ni de que fuente
    # haya salido.
    for p in partidos:
        if p.get("destacado"):
            continue
        for equipo in EQUIPOS_DESTACADOS:
            if (_es_equipo_destacado(p["local"], equipo["nombre_visible"])
                    or _es_equipo_destacado(p["visitante"], equipo["nombre_visible"])):
                p["destacado"] = True
                p["equipo_destacado"] = equipo["nombre_visible"]
                break

    partidos.sort(key=lambda p: p["fecha"])

    # Recien aca, uno por uno y solo para los partidos que quedaron en
    # la lista final (ya filtrados y deduplicados), se completa el
    # escudo que todavia falte, probando en orden: ID de TheSportsDB
    # (rapido, si el evento vino de ahi) -> cache en disco por nombre
    # (equipo ya encontrado en una corrida anterior, no pregunta de
    # nuevo) -> Wikidata por nombre -> Wikipedia por nombre (red de
    # contencion final) -> si ninguna lo tiene, se deja el escudo
    # generico.
    for p in partidos:
        p["escudo_local"] = _completar_escudo(p.get("escudo_local"), p["local"],
                                               p.get("_tsdb_id_local"), log)
        p["escudo_visitante"] = _completar_escudo(p.get("escudo_visitante"), p["visitante"],
                                                   p.get("_tsdb_id_visitante"), log)
        p["logo_competicion"] = _completar_logo_liga(p["competicion"], log)
        p["canal_tv"] = _completar_canal_tv(p.get("id"), log)

    return partidos


def _completar_logo_liga(nombre_competicion, log):
    """
    Logo de la competicion (Liga Profesional, Libertadores, etc), con
    el mismo espiritu de cache que los escudos de equipo: una vez
    resuelto, no se vuelve a preguntar nunca mas.

    Orden: cache en disco -> TheSportsDB (lookupleague.php, trae el
    escudo de la gran mayoria de las competiciones que sigue la app)
    -> logos_competiciones_manuales/ del repo, para el caso raro de
    que a alguna le falte.
    """
    clave_disco = f"logoliga:{_texto_normalizado(nombre_competicion)}"
    if clave_disco in _cache_escudos_disco:
        return _cache_escudos_disco[clave_disco]

    liga = _LIGA_POR_NOMBRE.get(nombre_competicion)
    url = None
    if liga:
        for liga_id in liga["ids"]:
            datos = _pedir(f"{BASE_URL}/lookupleague.php", {"id": liga_id}, log,
                            contexto=f"logo de {nombre_competicion}")
            ligas_data = (datos or {}).get("leagues") or []
            if ligas_data and ligas_data[0].get("strBadge"):
                url = ligas_data[0]["strBadge"]
                break

    if not url:
        url = _logo_liga_manual(nombre_competicion, log)

    if url:
        _cache_escudos_disco[clave_disco] = url
        _guardar_cache_escudos_disco()
    return url


def _completar_canal_tv(id_evento, log):
    """
    Canal que transmite ESE partido puntual (a diferencia del logo de
    competicion, esto varia partido a partido, no se puede cachear por
    competicion). Fuente: TheSportsDB (lookuptv.php), filtrando solo
    canales de Argentina.

    OJO: esto solo funciona para partidos cuyo ID es de TheSportsDB.
    Los que vinieron de ESPN tienen un id con el prefijo "espn-" (ver
    _evento_espn_a_partido) y no se pueden cruzar contra este endpoint
    -- para esos, se devuelve None directamente sin gastar un pedido,
    y en la interfaz van a mostrar "Buscar en internet".

    Se cachea por partido en un archivo aparte (canales_tv_cache.json)
    para no volver a preguntar en cada actualizacion del dia por el
    mismo partido.
    """
    if not id_evento or str(id_evento).startswith("espn-"):
        return None

    if id_evento in _cache_canales_tv:
        return _cache_canales_tv[id_evento]

    resultado = None
    datos = _pedir(f"{BASE_URL}/lookuptv.php", {"id": id_evento}, log,
                    contexto=f"canal de TV del partido {id_evento}")
    eventos_tv = (datos or {}).get("tvevent") or []
    for ev in eventos_tv:
        pais = _texto_normalizado(ev.get("strCountry") or "")
        if pais != "argentina":
            continue
        nombre_canal = ev.get("strChannel")
        resultado = {
            "canal": nombre_canal,
            "numero_telecentro": _numero_telecentro(nombre_canal),
            "logo": ev.get("strLogo"),
        }
        break

    _cache_canales_tv[id_evento] = resultado
    _guardar_cache_canales_tv()
    return resultado


def _completar_escudo(escudo_actual, nombre_equipo, tsdb_id, log):
    """
    Orden de prioridad para resolver el escudo de un equipo:

    1. Ya vino resuelto con el partido (ESPN/TheSportsDB lo trajeron
       directo con el evento) -- ni se pregunta.
    2. TheSportsDB por ID de equipo (rapido, un solo pedido).
    3. Cache en disco por nombre (equipo ya resuelto en una corrida
       anterior, sea cual haya sido la fuente que lo encontro).
    4. escudos_manuales/ del repo (lo que Sebi subio a mano con el
       Subidor de Escudos) -- se prueba ANTES que las fuentes externas
       porque si ya esta subido a mano es la fuente mas confiable y
       ademas la mas rapida (un solo pedido HEAD).
    5. Wikidata / Wikipedia, como ultimo recurso -- son las que mas
       tardan (busqueda de QID, varios pedidos), asi que dejarlas al
       final tambien ayuda a que la lista cargue mas rapido para los
       equipos que ya tienen escudo manual o en cache.
    """
    if escudo_actual:
        return escudo_actual

    if tsdb_id:
        escudo_actual = _escudo_thesportsdb(tsdb_id, log)
        if escudo_actual:
            return escudo_actual

    clave_disco = f"wiki:{_texto_normalizado(nombre_equipo)}"
    if clave_disco in _cache_escudos_disco:
        return _cache_escudos_disco[clave_disco]

    escudo_actual = (_escudo_manual(nombre_equipo, log)
                      or _escudo_wikidata(nombre_equipo, log)
                      or _escudo_wikipedia(nombre_equipo, log))
    if escudo_actual:
        _cache_escudos_disco[clave_disco] = escudo_actual
        _guardar_cache_escudos_disco()
    return escudo_actual


def _parsear_fecha_iso_utc(texto):
    """Acepta 'YYYY-MM-DDTHH:MM:SSZ' o 'YYYY-MM-DDTHH:MMZ' (ESPN a veces
    manda la fecha sin segundos)."""
    if not texto:
        return None
    texto = texto.replace("Z", "")
    for formato in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            dt = datetime.strptime(texto, formato)
            if TZ_UTC and TZ_ARG:
                dt = dt.replace(tzinfo=TZ_UTC).astimezone(TZ_ARG)
            return dt
        except ValueError:
            continue
    return None


def _evento_espn_a_partido(ev, nombre_visible):
    dt = _parsear_fecha_iso_utc(ev.get("date"))
    if not dt:
        return None

    competencias = ev.get("competitions") or [{}]
    competidores = (competencias[0] or {}).get("competitors") or []
    local = visitante = "?"
    escudo_local = escudo_visitante = None
    for c in competidores:
        nombre_equipo = (c.get("team") or {}).get("displayName") or "?"
        logo = (c.get("team") or {}).get("logo")
        if c.get("homeAway") == "home":
            local = nombre_equipo
            escudo_local = logo
        elif c.get("homeAway") == "away":
            visitante = nombre_equipo
            escudo_visitante = logo

    return {
        "id": f"espn-{ev.get('id')}",
        "competicion": nombre_visible,
        "local": local,
        "visitante": visitante,
        "fecha": dt,
        "destacado": False,
        "equipo_destacado": None,
        "escudo_local": escudo_local,
        "escudo_visitante": escudo_visitante,
    }


def _partidos_espn(log):
    """
    ESPN tiene un endpoint publico (no oficial, pero muy usado y
    estable) por competicion, con codigos fijos y conocidos. Se piden
    ayer/hoy/mañana en UTC (ver _ventana_dias_utc) para cubrir bien el
    dia de hoy en Argentina sin importar la hora a la que se ejecute.
    """
    hoy_arg = _fecha_hoy_arg()
    _, dias_utc = _ventana_dias_utc()
    fechas = [d.replace("-", "") for d in dias_utc]

    partidos = []
    for liga in LIGAS:
        slug = ESPN_LIGAS.get(liga["clave"])
        if not slug:
            continue
        filtro = FILTRO_EQUIPO.get(liga["clave"])

        for fecha in fechas:
            try:
                r = requests.get(f"{ESPN_BASE}/{slug}/scoreboard",
                                  params={"dates": fecha}, timeout=15)
                r.raise_for_status()
                eventos = r.json().get("events") or []
            except Exception as e:
                log(f"[ERROR] ESPN {liga['nombre_visible']} (dia {fecha}): {e}")
                continue

            for ev in eventos:
                p = _evento_espn_a_partido(ev, liga["nombre_visible"])
                if not p or p["fecha"].date() != hoy_arg:
                    continue
                if filtro:
                    texto = f"{p['local']} {p['visitante']}".lower()
                    if filtro not in texto:
                        continue
                partidos.append(p)

            time.sleep(0.8)

    log(f"[INFO] ESPN aporto {len(partidos)} partido(s) de nuestras competiciones.")
    return partidos
