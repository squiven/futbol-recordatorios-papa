# -*- coding: utf-8 -*-
"""
verificar_ligas.py
Prueba en vivo, contra TheSportsDB, que las 6 competiciones devuelvan
partidos. Correr con doble click en "verificar_ligas.bat".
"""

import api_deportes as api


def main():
    config = api.cargar_config()

    print("=" * 64)
    print(" CHEQUEANDO LAS 6 COMPETICIONES (en vivo, contra TheSportsDB)")
    print("=" * 64)

    partidos = api.obtener_proximos_partidos(config, log=print)

    conteo = {}
    for p in partidos:
        conteo[p["competicion"]] = conteo.get(p["competicion"], 0) + 1

    print()
    print("=" * 64)
    print(" RESUMEN")
    print("=" * 64)
    for liga in api.LIGAS:
        n = conteo.get(liga["nombre_visible"], 0)
        marca = "[OK]" if n else "[??]"
        estado = f"{n} partido(s) encontrados" if n else "sin partidos proximos"
        print(f"{marca}  {liga['nombre_visible']:32s} -> {estado}")
    print("=" * 64)

    input("\nPresiona Enter para cerrar...")


if __name__ == "__main__":
    main()
