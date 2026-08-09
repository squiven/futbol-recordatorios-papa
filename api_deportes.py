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
from datetime import datetime, timedelta

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


def _evento_a_partido(ev, nombre_visible):
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
                p = _evento_a_partido(ev, liga["nombre_visible"])
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
        p = _evento_a_partido(ev, nombre_torneo)
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
        return (
            a["local"].strip().lower() == b["local"].strip().lower()
            and a["visitante"].strip().lower() == b["visitante"].strip().lower()
            and abs((a["fecha"] - b["fecha"]).total_seconds()) < 3 * 3600
        )

    def _agregar(lista):
        for p in lista:
            existente = next((q for q in partidos if _mismo_partido(p, q)), None)
            if existente:
                if p.get("destacado") and not existente.get("destacado"):
                    existente["destacado"] = True
                    existente["equipo_destacado"] = p.get("equipo_destacado")
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

    partidos.sort(key=lambda p: p["fecha"])
    return partidos


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
    for c in competidores:
        nombre_equipo = (c.get("team") or {}).get("displayName") or "?"
        if c.get("homeAway") == "home":
            local = nombre_equipo
        elif c.get("homeAway") == "away":
            visitante = nombre_equipo

    return {
        "id": f"espn-{ev.get('id')}",
        "competicion": nombre_visible,
        "local": local,
        "visitante": visitante,
        "fecha": dt,
        "destacado": False,
        "equipo_destacado": None,
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
