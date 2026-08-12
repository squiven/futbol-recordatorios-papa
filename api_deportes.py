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


def _texto_normalizado(s):
    """Minusculas, sin acentos, sin espacios de mas -- para comparar
    nombres de equipo que vienen de distintas fuentes."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.lower().strip().split())


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
            if (_mismo_equipo(p["local"], equipo["nombre_visible"])
                    or _mismo_equipo(p["visitante"], equipo["nombre_visible"])):
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

    return partidos


def _completar_escudo(escudo_actual, nombre_equipo, tsdb_id, log):
    if escudo_actual:
        return escudo_actual

    if tsdb_id:
        escudo_actual = _escudo_thesportsdb(tsdb_id, log)
        if escudo_actual:
            return escudo_actual

    clave_disco = f"wiki:{_texto_normalizado(nombre_equipo)}"
    if clave_disco in _cache_escudos_disco:
        return _cache_escudos_disco[clave_disco]

    escudo_actual = _escudo_wikidata(nombre_equipo, log) or _escudo_wikipedia(nombre_equipo, log)
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
