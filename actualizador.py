# -*- coding: utf-8 -*-
"""
actualizador.py
Revisa si hay una version mas nueva del programa publicada en GitHub y,
si la hay, la descarga y reemplaza los archivos de codigo — sin tocar
config.json ni registro.log, que son datos propios de esta computadora.
"""

import io
import os
import shutil
import subprocess
import sys
import zipfile

import requests

CARPETA = os.path.dirname(os.path.abspath(__file__))
VERSION_PATH = os.path.join(CARPETA, "version.txt")

# Archivos/carpetas que NUNCA se tocan al actualizar.
NO_TOCAR = {"config.json", "registro.log", "escudos_cache.json", "__pycache__",
            ".git", ".gitignore"}


def _version_local():
    try:
        with open(VERSION_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return "0"


def _version_remota(repo, rama):
    url = f"https://raw.githubusercontent.com/{repo}/{rama}/version.txt"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.text.strip()


def revisar_actualizacion(config, log=print):
    """
    Devuelve True si actualizo (y hay que reiniciar el programa),
    False si no habia nada nuevo o no esta configurado.
    """
    info = config.get("actualizaciones", {})
    repo = info.get("repo")
    rama = info.get("rama", "main")
    if not repo:
        return False  # todavia no se configuro el repo, no hace nada

    try:
        remota = _version_remota(repo, rama)
    except Exception as e:
        log(f"[ACTUALIZACION] No se pudo chequear la version remota: {e}")
        return False

    local = _version_local()
    if remota == local:
        return False

    log(f"[ACTUALIZACION] Version nueva disponible: {local} -> {remota}. Descargando...")
    try:
        _descargar_y_aplicar(repo, rama, log)
    except Exception as e:
        log(f"[ACTUALIZACION] Fallo al actualizar: {e}")
        return False

    with open(VERSION_PATH, "w", encoding="utf-8") as f:
        f.write(remota)

    log("[ACTUALIZACION] Actualizacion aplicada correctamente.")
    return True


def _descargar_y_aplicar(repo, rama, log):
    url = f"https://codeload.github.com/{repo}/zip/refs/heads/{rama}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        for nombre in z.namelist():
            if nombre.endswith("/"):
                continue
            partes = nombre.split("/", 1)  # saca la carpeta raiz del zip
            if len(partes) < 2 or not partes[1]:
                continue
            ruta_relativa = partes[1]
            primer_elemento = ruta_relativa.split("/")[0]
            if primer_elemento in NO_TOCAR:
                continue

            destino = os.path.join(CARPETA, ruta_relativa)
            os.makedirs(os.path.dirname(destino) or CARPETA, exist_ok=True)
            with z.open(nombre) as origen, open(destino, "wb") as salida:
                shutil.copyfileobj(origen, salida)
            log(f"[ACTUALIZACION] Archivo actualizado: {ruta_relativa}")


def reiniciar_programa():
    """Vuelve a lanzar app.py (silencioso si hay pythonw) y cierra este proceso."""
    python_silencioso = shutil.which("pythonw") or sys.executable
    subprocess.Popen([python_silencioso, os.path.join(CARPETA, "app.py")], cwd=CARPETA)
    os._exit(0)
