# -*- coding: utf-8 -*-
"""
app.py
Programa de recordatorios para papa:
 - Avisa proximos partidos de sus competiciones favoritas (Liga Argentina,
   Copa Argentina, Libertadores, Sudamericana, MLS/Inter Miami, Champions),
   mas los de Boca y la Seleccion Argentina en cualquier competicion.
 - Boton grande para arrancar el temporizador de 2 horas para medirse la
   insulina (se toca cuando lo llaman a comer, en el almuerzo y en la cena).

Para arrancar el programa: doble click en iniciar.bat
"""

import hashlib
import io
import json
import math
import os
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

try:
    import winsound
except ImportError:
    winsound = None

try:
    import winreg
except ImportError:
    winreg = None

import requests
from plyer import notification
import pystray
from PIL import Image, ImageDraw, ImageTk

import api_deportes as api
import actualizador
from panel_timer import PanelTimer, _redondear, _puntos_redondeado
from generador_sopa import generar_sopa

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "registro.log")
ICONO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icono.ico")
ESCUDOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "escudos_cache")
RANKING_SOPA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ranking_sopa.json")
SOPA_ACTUAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sopa_actual.json")

# Sistema de puntos de la sopa de letras (Etapa 5): cuanto mas rapido
# se resuelve, mas puntos. Con la grilla/cantidad de palabras actual
# (22x22, 24 palabras) 1000 puntos de base y 1 punto menos por cada
# segundo que pasa parecen numeros razonables -- por ejemplo, resolverla
# en 5 minutos (300s) da 700 puntos, en 10 minutos (600s) da 400. Nunca
# baja de 100 (para que resolverla, por lenta que haya sido, siempre
# sume algo). Si mas adelante vemos que en la practica tarda mucho mas
# o mucho menos que esto, es cuestion de ajustar estos 3 numeros.
SOPA_PUNTAJE_BASE = 1000
SOPA_PUNTAJE_MINIMO = 100
SOPA_PENALIZACION_POR_SEGUNDO = 1

ANCHO_VENTANA = 760
ALTO_VENTANA = 760

# Ancho de la columna de "PARTIDOS DE HOY" una vez que la ventana ya
# esta maximizada. Mas ancha que el panel del timer (que se queda en
# ANCHO_VENTANA para no tocar su diseno) para darle a cada fila de
# partido lugar de sobra para una letra mas grande, sin llegar a
# estirarse borde a borde de la pantalla (eso queda para el rediseno
# completo de la Etapa 3).
ANCHO_SECCION_PARTIDOS = 1080

# Escalas de letra disponibles para el boton A-/A+ del header (Etapa
# 3). 1.0 es el tamano "normal" con el que se disenaron las fuentes de
# la fila de partido; el resto son multiplicadores sobre esos mismos
# valores base.
ESCALAS_TEXTO = [0.85, 1.0, 1.15, 1.3, 1.5]


def log(mensaje):
    linea = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {mensaje}"
    print(linea)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except Exception:
        pass


def crear_imagen_icono():
    """Icono de pelota de futbol para la bandeja del sistema."""
    try:
        return Image.open(ICONO_PATH)
    except Exception:
        # Respaldo por si falta el archivo icono.ico
        img = Image.new("RGB", (64, 64), "white")
        d = ImageDraw.Draw(img)
        d.ellipse((4, 4, 60, 60), fill=(34, 139, 34))
        return img


# ---------------- TEMA CLARO / OSCURO ----------------
TEMAS = {
    "claro": {
        "ventana_bg": "#f5f8f6",
        "panel_bg": "#e9f4ec",
        "panel_borde": "#d7e8db",
        "card_bg": "#ffffff",
        "card_borde": "#e3e8ec",
        "texto_primario": "#152238",
        "texto_secundario": "#69737d",
        "verde": "#2e8b57",
        "verde_oscuro": "#256d46",
        "rojo": "#c0392b",
        "rojo_oscuro": "#a93226",
        "gris_deshabilitado": "#aab2b8",
        "badge_hora_bg": "#e1f2e6",
        "badge_hora_texto": "#237a4a",
        "trough": "#dde5e0",
        "dorado": "#9c7a12",
        "dorado_bg": "#fbf1da",
        "dorado_borde": "#e9cd7c",
        "blanco_boton": "#ffffff",
        "azul_link": "#1a6fb0",
        # Paleta para la sopa de letras: un color distinto para cada
        # palabra que se va encontrando (Etapa 5), rotando de a 10.
        "paleta_sopa": [
            "#9c7a12", "#1a6fb0", "#2e8b57", "#c0392b", "#7d3c98",
            "#16a085", "#d35400", "#c2185b", "#7b5427", "#5b3fa0",
        ],
    },
    "oscuro": {
        "ventana_bg": "#121822",
        "panel_bg": "#1b2430",
        "panel_borde": "#2a3542",
        "card_bg": "#1e2733",
        "card_borde": "#2c3947",
        "texto_primario": "#eef2f6",
        "texto_secundario": "#98a4b3",
        "verde": "#37a165",
        "verde_oscuro": "#2e8b57",
        "rojo": "#d6584a",
        "rojo_oscuro": "#c0392b",
        "gris_deshabilitado": "#3d454e",
        "badge_hora_bg": "#1f3226",
        "badge_hora_texto": "#5fce8c",
        "trough": "#2a333d",
        "dorado": "#e0b84b",
        "dorado_bg": "#332c18",
        "dorado_borde": "#5a4a1e",
        "blanco_boton": "#ffffff",
        "azul_link": "#6fb3e0",
        "paleta_sopa": [
            "#e0b84b", "#6fb3e0", "#37a165", "#d6584a", "#b58cdb",
            "#4fd1c5", "#f0935a", "#f06fa0", "#c9a26a", "#8e9ff2",
        ],
    },
}


def _color_texto_legible(color_hex):
    """Para las lineas de colores de la sopa de letras (Etapa 5): dado
    un color de fondo en hex, devuelve blanco o negro segun cual de
    los dos se lea mejor encima -- asi la letra siempre se distingue
    sin importar cual de los 10 colores de la paleta le toco a esa
    palabra."""
    color_hex = color_hex.lstrip("#")
    r, g, b = int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
    luminancia = 0.299 * r + 0.587 * g + 0.114 * b
    return "#1a1a1a" if luminancia > 150 else "#ffffff"


def _tema_windows_es_oscuro():
    """Lee el registro de Windows para saber si el usuario tiene el tema
    oscuro activado (Configuracion > Personalizacion > Colores). Si no
    se puede leer (no es Windows, error, version vieja), se asume claro."""
    if not winreg:
        return False
    try:
        clave = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        valor, _ = winreg.QueryValueEx(clave, "AppsUseLightTheme")
        return valor == 0
    except Exception:
        return False


def _fuente(size, weight="normal", condensada=True):
    """Bahnschrift viene instalada de fabrica desde Windows 10 y tiene
    un look condensado en mayusculas muy parecido al de referencia. Si
    no esta disponible (por ejemplo en Mac/Linux), Tkinter cae solo en
    una fuente parecida sin romper nada."""
    familia = "Bahnschrift SemiBold" if condensada else "Segoe UI"
    return tkfont.Font(family=familia, size=size, weight=weight)


class App:
    def __init__(self, root):
        self.root = root
        self.config = api.cargar_config()

        self.partidos = []
        self.notificados = set(self.config.get("notificados", []))
        self.tray_icon = None

        self.tema = TEMAS["oscuro"] if _tema_windows_es_oscuro() else TEMAS["claro"]
        self._escudo_cache = {}  # (url, tamano) -> PhotoImage | "cargando" | None

        # Tema manual: None = seguir automaticamente el tema de Windows
        # (comportamiento de siempre). "claro"/"oscuro" = el usuario lo
        # forzo a mano con el selector del header, y entonces
        # _revisar_cambio_tema deja de pisarlo solo.
        self.tema_manual = None

        # Vista activa dentro del contenedor de navegacion (Etapa 1).
        # "futbol" es la unica vista real por ahora; "sopa" y
        # "solitario" son placeholders hasta las etapas 5 y 6.
        self.vista_actual = "futbol"

        # Tamano de letra: INDEPENDIENTE por pestana (Futbol / Sopa /
        # Solitario) y guardado en config.json para que quede como lo
        # dejo la ultima vez, en cada una por separado -- asi si Sebi
        # quiere letra grande en Partidos pero normal en la Sopa, cada
        # una mantiene la suya. Si config.json todavia tiene el
        # formato viejo (un solo numero para las tres) se migra solo:
        # ese numero se usa como punto de partida para las tres.
        guardado = self.config.get("escala_texto", 1.0)
        if isinstance(guardado, dict):
            self.escalas_texto = {
                vista: (guardado.get(vista, 1.0) if guardado.get(vista, 1.0) in ESCALAS_TEXTO else 1.0)
                for vista in ("futbol", "sopa", "solitario")
            }
        else:
            valor = guardado if guardado in ESCALAS_TEXTO else 1.0
            self.escalas_texto = {"futbol": valor, "sopa": valor, "solitario": valor}

        # Sopa de letras (Etapa 5): se intenta retomar la que quedo a
        # medias la ultima vez que se uso el programa (persistida en
        # disco, sobrevive a apagar la PC); si no hay ninguna guardada
        # o esta corrupta, se genera una nueva la primera vez que se
        # entra a la pestana. Cada vez que se encuentra una palabra
        # nueva se vuelve a guardar, asi nunca se pierde mas de una
        # palabra de progreso si se corta la luz.
        self.sopa = self._cargar_sopa_guardada()
        self._sopa_letra_ids = {}      # (fila, columna) -> id de texto en el Canvas
        self._sopa_preview_id = None   # linea de arrastre en curso (se borra o se confirma)
        self._sopa_inicio_arrastre = None
        self._sopa_inicio_pixeles = None
        self._sopa_direccion_bloqueada = None  # direccion del arrastre en curso, ver _sopa_arrastrando
        self._sopa_labels_palabras = {}  # palabra -> (Label, Font)

        # Temporizador de "llamado a comer" (Etapa 2): la logica y el
        # dibujo viven en panel_timer.py, esta es la UNICA instancia
        # -- se puede montar en distintas vistas (mas adelante, Sopa y
        # Solitario) pero el estado (activo/restante) es compartido.
        self.timer = PanelTimer(self)

        self._configurar_ventana_base()
        self._armar_ventana()
        self._armar_tray()
        self.timer.revisar_guardado()

        threading.Thread(target=self._ciclo_de_fondo, daemon=True).start()

    # ---------------- INTERFAZ ----------------
    def _configurar_ventana_base(self):
        """Todo lo que solo tiene sentido configurar UNA vez al abrir el
        programa: tamano/estado de la ventana, icono, protocolo de
        cierre. Antes esto vivia adentro de _armar_ventana(), que se
        vuelve a llamar cada vez que cambia el tema o el tamano de
        letra (_reconstruir_ui) -- eso hacia que Windows "reafirmara"
        la ventana como maximizada en cada cambio (root.state("zoomed")
        sobre una ventana que YA esta maximizada) y se viera como un
        salto/parpadeo raro, como si el programa se cerrara y abriera.
        Separado aca, ese salto desaparece porque _armar_ventana ya no
        toca nada de esto."""
        self.root.title("Futbol y Recordatorios")
        self.root.resizable(True, True)
        try:
            self.root.state("zoomed")
        except Exception:
            self.root.geometry(f"{ANCHO_VENTANA}x{ALTO_VENTANA}")
        self.root.minsize(ANCHO_VENTANA, ALTO_VENTANA)
        self.root.protocol("WM_DELETE_WINDOW", self._minimizar_a_bandeja)
        try:
            self.root.iconbitmap(ICONO_PATH)
        except Exception:
            pass

    def _armar_ventana(self):
        t = self.tema
        self.root.configure(bg=t["ventana_bg"])

        self._f_titulo = _fuente(24, "bold")
        self._f_subtitulo_seccion = _fuente(17, "bold")
        self._f_boton = _fuente(14, "bold")
        self._f_boton_sub = tkfont.Font(family="Segoe UI", size=9)
        self._f_timer_label = _fuente(11, "bold")
        self._f_timer_valor = _fuente(30, "bold", condensada=False)
        self._f_timer_caption = tkfont.Font(family="Segoe UI", size=8)
        # Fuentes de la fila de partido -- agrandadas respecto de la
        # version original (760px) porque ahora la fila tiene mas
        # ancho disponible (ver ANCHO_SECCION_PARTIDOS), y multiplicadas
        # por la escala de texto PROPIA de la pestana Futbol (Etapa 3;
        # ahora cada pestana tiene la suya -- OJO ACA: aunque el
        # usuario este parado en Sopa cuando cambia de tema y esto se
        # vuelve a armar, estas fuentes son las de las FILAS DE
        # PARTIDOS, asi que tienen que usar SIEMPRE la escala guardada
        # para "futbol", nunca la de la pestana en la que este parado
        # en este momento).
        e = self.escalas_texto["futbol"]
        self._f_hora = _fuente(round(16 * e), "bold")
        self._f_fecha = tkfont.Font(family="Segoe UI", size=round(10 * e))
        self._f_equipo = tkfont.Font(family="Segoe UI", size=round(14 * e), weight="bold")
        self._f_vs = tkfont.Font(family="Segoe UI", size=round(11 * e))
        self._f_competicion = tkfont.Font(family="Segoe UI", size=round(11 * e))
        self._f_canal = tkfont.Font(family="Segoe UI", size=round(11 * e), weight="bold")
        self._f_canal_numero = tkfont.Font(family="Segoe UI", size=round(9 * e))
        self._f_footer = tkfont.Font(family="Segoe UI", size=9)
        self._f_nav = _fuente(13, "bold")

        self._armar_header()

        # El temporizador "LLAMADO A COMER" ahora vive en modo
        # "compacto" (ver panel_timer.py -- ya estaba escrito desde la
        # Etapa 2, solo faltaba usarlo), pegado arriba a la izquierda,
        # en vez de ocupar todo el ancho de la ventana en modo
        # "grande" como antes. Sebi tenia razon: quedaba demasiado
        # espacio de pantalla sin aprovechar, sobre todo en la sopa de
        # letras. El contenido de la vista activa arranca inmediato al
        # lado (misma fila) y ocupa TODO el resto del ancho y del alto.
        frame_fila_superior = tk.Frame(self.root, bg=t["ventana_bg"])
        frame_fila_superior.pack(fill="both", expand=True)

        frame_timer = tk.Frame(frame_fila_superior, bg=t["ventana_bg"])
        frame_timer.pack(side="left", anchor="n", padx=(20, 10), pady=20)
        self.timer.armar(frame_timer, ancho=250, alto=140, modo="compacto")

        # Contenedor de la vista activa. A partir de aca, cada vista
        # (Futbol / Sopa / Solitario) se arma dentro de este frame en
        # vez de colgar directamente del root -- eso es lo que permite
        # cambiar de vista sin reconstruir header ni navegacion (ni,
        # ahora, el temporizador).
        self.frame_contenido = tk.Frame(frame_fila_superior, bg=t["ventana_bg"])
        self.frame_contenido.pack(side="left", fill="both", expand=True)

        self._mostrar_vista(self.vista_actual)

    def _armar_header(self):
        t = self.tema
        header = tk.Frame(self.root, bg=t["panel_bg"])
        header.pack(fill="x")

        # Franja de contenido del header, con margen interno, para no
        # pegar todo a los bordes de la ventana.
        interior = tk.Frame(header, bg=t["panel_bg"])
        interior.pack(fill="x", padx=24, pady=14)

        # --- titulo, a la izquierda ---
        frame_titulo = tk.Frame(interior, bg=t["panel_bg"])
        frame_titulo.pack(side="left")
        tk.Label(frame_titulo, text="\u26bd", font=("Segoe UI Emoji", 22),
                 bg=t["panel_bg"], fg=t["texto_primario"]).pack(side="left", padx=(0, 8))
        tk.Label(frame_titulo, text="FUTBOL Y RECORDATORIOS", font=self._f_titulo,
                 bg=t["panel_bg"], fg=t["texto_primario"]).pack(side="left")

        # --- selector de tema, a la derecha ---
        # Boton unico que alterna claro/oscuro a mano. Mientras no se
        # toque, el tema sigue decidiendose solo segun Windows (ver
        # _revisar_cambio_tema); apenas se usa este boton, esa deteccion
        # automatica se deja de aplicar hasta que se cierre el programa.
        icono_tema = "\u2600" if self.tema is TEMAS["oscuro"] else "\U0001F319"
        self.boton_tema = tk.Label(
            interior, text=icono_tema, font=("Segoe UI Emoji", 14),
            bg=t["card_bg"], fg=t["texto_primario"], padx=14, pady=6, cursor="hand2")
        self.boton_tema.pack(side="right")
        self.boton_tema.bind("<Button-1>", lambda e: self._alternar_tema_manual())

        # --- tamano de letra, tambien a la derecha (Etapa 3) ---
        # Dos botones simples, A- / A+, para que el tamano de letra de
        # los partidos se pueda ajustar a lo que le resulte comodo a
        # mi viejo, sin tener que entrar a ningun menu.
        frame_letra = tk.Frame(interior, bg=t["card_bg"])
        frame_letra.pack(side="right", padx=(0, 10))
        btn_menos = tk.Label(frame_letra, text="A\u2212", font=_fuente(13, "bold"),
                              bg=t["card_bg"], fg=t["texto_primario"],
                              padx=12, pady=6, cursor="hand2")
        btn_menos.pack(side="left")
        btn_mas = tk.Label(frame_letra, text="A+", font=_fuente(13, "bold"),
                            bg=t["card_bg"], fg=t["texto_primario"],
                            padx=12, pady=6, cursor="hand2")
        btn_mas.pack(side="left")
        btn_menos.bind("<Button-1>", lambda e: self._cambiar_escala_texto(-1))
        btn_mas.bind("<Button-1>", lambda e: self._cambiar_escala_texto(1))

        # --- navegacion entre vistas, centrada ---
        self._armar_navegacion(interior)

    def _armar_navegacion(self, parent):
        t = self.tema
        nav = tk.Frame(parent, bg=t["panel_bg"])
        nav.pack(side="left", expand=True)

        self._botones_nav = {}
        opciones = [
            ("futbol", "\u26bd", "FUTBOL"),
            ("sopa", "\U0001F524", "SOPA"),
            ("solitario", "\U0001F0CF", "SOLITARIO"),
        ]
        for clave, emoji, texto in opciones:
            # El emoji necesita su propia fuente ("Segoe UI Emoji"),
            # igual que en el titulo del header -- si se lo mezcla con
            # la fuente Bahnschrift del texto, Windows puede no
            # encontrar el glifo de color y mostrar un simbolo generico.
            btn = tk.Frame(nav, bg=t["card_bg"], padx=22, pady=10, cursor="hand2")
            btn.pack(side="left", padx=8)
            lbl_emoji = tk.Label(btn, text=emoji, font=("Segoe UI Emoji", 14),
                                  bg=t["card_bg"], fg=t["texto_primario"])
            lbl_emoji.pack(side="left", padx=(0, 8))
            lbl_texto = tk.Label(btn, text=texto, font=self._f_nav, bg=t["card_bg"],
                                  fg=t["texto_primario"])
            lbl_texto.pack(side="left")

            for widget in (btn, lbl_emoji, lbl_texto):
                widget.bind("<Button-1>", lambda e, c=clave: self._cambiar_vista(c))
            self._botones_nav[clave] = (btn, lbl_emoji, lbl_texto)

        self._pintar_navegacion_activa()

    def _pintar_navegacion_activa(self):
        """Resalta el boton de la vista actual y deja los otros dos con
        aspecto neutro, sin tocar nada mas del header."""
        t = self.tema
        for clave, (frame, lbl_emoji, lbl_texto) in self._botones_nav.items():
            activo = clave == self.vista_actual
            bg = t["verde"] if activo else t["card_bg"]
            fg = "white" if activo else t["texto_primario"]
            frame.config(bg=bg)
            lbl_emoji.config(bg=bg, fg=fg)
            lbl_texto.config(bg=bg, fg=fg)

    def _alternar_tema_manual(self):
        nuevo = "claro" if self.tema is TEMAS["oscuro"] else "oscuro"
        self.tema_manual = nuevo
        self.tema = TEMAS[nuevo]
        log(f"Tema cambiado a mano por el usuario: {nuevo}.")
        self._reconstruir_ui()

    def _escala_actual(self):
        """La escala de texto de la pestana en la que se esta parado
        AHORA (cada una tiene la suya, ver __init__)."""
        return self.escalas_texto.get(self.vista_actual, 1.0)

    def _cambiar_escala_texto(self, direccion):
        """direccion: -1 (A-) o +1 (A+). Se mueve un paso dentro de
        ESCALAS_TEXTO, PERO SOLO PARA LA PESTANA ACTUAL, y se guarda en
        config.json para la proxima vez que se abra el programa."""
        escala_vista = self.escalas_texto[self.vista_actual]
        indice_actual = ESCALAS_TEXTO.index(escala_vista)
        nuevo_indice = max(0, min(len(ESCALAS_TEXTO) - 1, indice_actual + direccion))
        if nuevo_indice == indice_actual:
            return  # ya esta en el minimo o el maximo
        self.escalas_texto[self.vista_actual] = ESCALAS_TEXTO[nuevo_indice]
        self.config["escala_texto"] = self.escalas_texto
        api.guardar_config(self.config)
        log(f"Tamano de letra de '{self.vista_actual}' cambiado a {ESCALAS_TEXTO[nuevo_indice]}x.")
        self._reconstruir_ui()

    # ---------------- NAVEGACION / VISTAS ----------------
    def _cambiar_vista(self, nombre):
        if nombre == self.vista_actual:
            return
        self.vista_actual = nombre
        self._pintar_navegacion_activa()
        self._mostrar_vista(nombre)

    def _mostrar_vista(self, nombre):
        for widget in self.frame_contenido.winfo_children():
            widget.destroy()

        if nombre == "futbol":
            self._armar_vista_futbol(self.frame_contenido)
        elif nombre == "sopa":
            self._armar_vista_sopa(self.frame_contenido)
        elif nombre == "solitario":
            self._armar_vista_placeholder(
                self.frame_contenido, "\U0001F0CF",
                "SOLITARIO",
                "Esta seccion todavia no esta implementada (llega en una proxima etapa).")

    def _armar_vista_futbol(self, parent):
        """Vista Futbol: por ahora es exactamente lo que antes era toda
        la ventana (timer + partidos + footer), solo que ahora se
        arma dentro del contenedor de la vista activa en vez de
        colgar directamente del root. La logica interna de cada una
        no se toco.

        El timer se saco de aca (ver _armar_ventana) porque ahora
        tiene que verse en TODAS las pestanas, no solo en esta."""
        self._armar_seccion_partidos(parent)
        self._armar_footer(parent)

    def _armar_vista_placeholder(self, parent, emoji, titulo, subtitulo):
        t = self.tema
        frame = tk.Frame(parent, bg=t["ventana_bg"])
        frame.pack(fill="both", expand=True)
        centro = tk.Frame(frame, bg=t["ventana_bg"])
        centro.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(centro, text=emoji, font=("Segoe UI Emoji", 48),
                 bg=t["ventana_bg"], fg=t["texto_secundario"]).pack()
        tk.Label(centro, text=titulo, font=self._f_titulo,
                 bg=t["ventana_bg"], fg=t["texto_primario"]).pack(pady=(10, 4))
        tk.Label(centro, text=subtitulo, font=self._f_footer,
                 bg=t["ventana_bg"], fg=t["texto_secundario"]).pack()

    # ---------------- SOPA DE LETRAS (Etapa 5) ----------------
    def _calcular_dimensiones_sopa(self, parent):
        """Calcula cuantas columnas/filas entran SIN que el tablero se
        salga de la pantalla, en base al espacio realmente disponible
        ahora mismo (ventana actual, resolucion del monitor, tamano de
        letra elegido) -- no un tamano fijo. Como pidio Sebi: el
        tablero no tiene por que ser mas grande de lo que ya era (lo
        tope en 24x24 aunque sobre lugar), pero si la letra esta muy
        grande o la ventana/monitor es mas chico, se achica solo para
        que siempre entre completo. Lo que SI aprovecha el espacio
        libre es la cantidad de palabras: cuantas mas celdas entran,
        mas densa se arma la sopa."""
        e = self.escalas_texto["sopa"]
        celda_px = round(30 * (0.7 + 0.3 * e))

        parent.update_idletasks()
        ancho_total = parent.winfo_width()
        alto_total = parent.winfo_height()
        # La primerisima vez que se arma la ventana, winfo_width/height
        # todavia pueden devolver 1 (no se termino de dibujar nada) --
        # en ese caso se usa la resolucion de la pantalla como base en
        # vez de un numero que nos haria armar una sopa minuscula.
        if ancho_total <= 10:
            ancho_total = self.root.winfo_screenwidth() - 280
        if alto_total <= 10:
            alto_total = self.root.winfo_screenheight() - 260

        # Le resto a lo disponible: la columna de palabras (~240px),
        # el titulo + boton de arriba (~50px), el cronometro de abajo
        # (~40px) y margenes varios. El colchon de seguridad es grande
        # a proposito (mas de lo que en teoria hace falta) porque en
        # la practica, en una PC con Windows real (barra de tareas,
        # bordes de ventana, escalado de pantalla) el espacio que
        # realmente se puede usar termina siendo bastante menos que lo
        # que reportan las medidas "de libro" -- mejor que sobre lugar
        # a que el tablero se corte.
        ancho_para_grilla = max(300, ancho_total - 240 - 130)
        alto_para_grilla = max(300, alto_total - 50 - 40 - 130)

        columnas = min(22, max(10, ancho_para_grilla // celda_px))
        filas = min(22, max(10, alto_para_grilla // celda_px))
        # Densidad: antes era ~1 palabra cada 20 celdas (12 palabras en
        # 17x17), ahora ~1 cada 12 -- notablemente mas apretado, que
        # es lo que pidio Sebi ("mas palabras, no tablero mas grande").
        cantidad_palabras = min(45, max(14, (columnas * filas) // 12))

        return columnas, filas, cantidad_palabras, celda_px

    def _iniciar_sopa_nueva(self, parent):
        """Arma los datos de una sopa desde cero (grilla + palabras +
        metadatos de cronometro/puntaje), con el tamano justo para el
        espacio disponible ahora mismo. Separado de _nueva_sopa() para
        que tanto la primera vez que se entra a la pestana como el
        boton "Empezar sopa nueva" usen exactamente el mismo camino."""
        columnas, filas, cantidad_palabras, _ = self._calcular_dimensiones_sopa(parent)
        sopa = generar_sopa(ancho=columnas, alto=filas,
                             cantidad_palabras=cantidad_palabras, permitir_reversa=True)
        sopa["siguiente_color"] = 0
        sopa["tiempo_inicio"] = time.time()
        sopa["completada"] = False
        sopa["tiempo_final"] = None
        self._guardar_sopa_actual(sopa)
        return sopa

    def _guardar_sopa_actual(self, sopa=None):
        """Persiste la sopa en curso a disco (sopa_actual.json) para
        que sobreviva a cerrar el programa o apagar la PC -- se llama
        cada vez que cambia algo importante (arranca una sopa nueva,
        se encuentra una palabra). Si falla al guardar (disco lleno,
        sin permisos, etc.) solo lo anota en el log y sigue: es un
        "nice to have", no algo que tenga que frenar el juego."""
        sopa = sopa if sopa is not None else self.sopa
        if sopa is None:
            return
        try:
            with open(SOPA_ACTUAL_PATH, "w", encoding="utf-8") as f:
                json.dump(sopa, f, ensure_ascii=False)
        except Exception as e:
            log(f"No se pudo guardar el progreso de la sopa en curso: {e}")

    def _cargar_sopa_guardada(self):
        """Intenta retomar la sopa que habia quedado a medias la
        ultima vez que se cerro el programa. Si no hay ninguna, o el
        archivo esta corrupto / tiene un formato viejo que ya no
        coincide con lo que espera el resto del codigo, se descarta
        sin romper nada y arranca todo de cero la primera vez que se
        entre a la pestana (ver _armar_vista_sopa)."""
        if not os.path.exists(SOPA_ACTUAL_PATH):
            return None
        try:
            with open(SOPA_ACTUAL_PATH, "r", encoding="utf-8") as f:
                sopa = json.load(f)
            claves_necesarias = {"ancho", "alto", "grilla", "palabras",
                                  "tiempo_inicio", "completada"}
            if not claves_necesarias.issubset(sopa.keys()):
                return None
            return sopa
        except Exception as e:
            log(f"No se pudo retomar la sopa guardada, se arranca una nueva: {e}")
            return None

    def _armar_vista_sopa(self, parent):
        t = self.tema
        e = self.escalas_texto["sopa"]

        # Si todavia no hay ninguna sopa, se arma una. Si ya hay una
        # pero el espacio disponible cambio de forma notoria (letra
        # agrandada, ventana/monitor mas chico) se arma una nueva que
        # entre bien -- como aviso Sebi, es preferible perder el
        # progreso de una sopa que ya no entra en pantalla a que quede
        # un pedazo invisible e imposible de terminar. Un cambio
        # chico (1 celda de diferencia, por redondeos) NO dispara esto,
        # para no perder progreso por nada.
        columnas, filas, _, _ = self._calcular_dimensiones_sopa(parent)
        if self.sopa is None or (abs(self.sopa["ancho"] - columnas) >= 2
                                  or abs(self.sopa["alto"] - filas) >= 2):
            self.sopa = self._iniciar_sopa_nueva(parent)

        frame = tk.Frame(parent, bg=t["ventana_bg"])
        frame.pack(fill="both", expand=True)

        col = tk.Frame(frame, bg=t["ventana_bg"])
        col.pack(pady=(20, 10), fill="both", expand=True, padx=(10, 10))

        # --- encabezado: titulo + boton de sopa nueva ---
        frame_tit = tk.Frame(col, bg=t["ventana_bg"])
        frame_tit.pack(fill="x", pady=(0, 14))
        frame_tit_izq = tk.Frame(frame_tit, bg=t["ventana_bg"])
        frame_tit_izq.pack(side="left")
        tk.Label(frame_tit_izq, text="\U0001F524", font=("Segoe UI Emoji", 15),
                 bg=t["ventana_bg"], fg=t["texto_primario"]).pack(side="left", padx=(0, 8))
        tk.Label(frame_tit_izq, text="SOPA DE LETRAS", font=self._f_subtitulo_seccion,
                 bg=t["ventana_bg"], fg=t["texto_primario"]).pack(side="left")

        btn_nueva = tk.Label(frame_tit, text="\U0001F504  Empezar sopa nueva",
                              font=self._f_boton, bg=t["verde"], fg="white",
                              padx=16, pady=8, cursor="hand2")
        self._btn_nueva_sopa_widget = btn_nueva
        btn_nueva.pack(side="right")
        btn_nueva.bind("<Button-1>", lambda ev: self._nueva_sopa())

        # --- zona con scroll: grilla + lista de palabras ---
        # Envuelvo todo esto en un Canvas con scrollbar horizontal Y
        # vertical (a diferencia de la lista de partidos, que solo
        # necesita vertical) porque si la ventana queda mas chica que
        # la grilla -- por ejemplo si a Sebi le cambia la resolucion
        # del monitor, o la desmaximiza -- antes se cortaba un pedazo
        # del tablero sin ninguna forma de llegar a verlo. Ahora
        # siempre se puede scrollear hasta cualquier punto.
        estilo_v = self._estilo_scrollbar("vertical")
        estilo_h = self._estilo_scrollbar("horizontal")

        contenedor_scroll = tk.Frame(col, bg=t["card_borde"], bd=0)
        contenedor_scroll.pack(fill="both", expand=True)
        interior_scroll = tk.Frame(contenedor_scroll, bg=t["ventana_bg"])
        interior_scroll.pack(padx=1, pady=1, fill="both", expand=True)

        canvas_scroll = tk.Canvas(interior_scroll, bg=t["ventana_bg"], highlightthickness=0)
        scrollbar_v = ttk.Scrollbar(interior_scroll, orient="vertical",
                                     command=canvas_scroll.yview, style=estilo_v)
        scrollbar_h = ttk.Scrollbar(interior_scroll, orient="horizontal",
                                     command=canvas_scroll.xview, style=estilo_h)
        cuerpo = tk.Frame(canvas_scroll, bg=t["ventana_bg"])

        cuerpo.bind("<Configure>",
                    lambda ev: canvas_scroll.configure(scrollregion=canvas_scroll.bbox("all")))
        id_ventana_cuerpo = canvas_scroll.create_window((0, 0), window=cuerpo, anchor="nw")
        canvas_scroll.configure(yscrollcommand=scrollbar_v.set, xscrollcommand=scrollbar_h.set)

        # La grilla + lista de palabras se centran horizontalmente
        # dentro del area visible en vez de quedar pegadas contra el
        # borde izquierdo (que era lo que pasaba antes: como el
        # contenido nunca llega a ocupar TODO el ancho disponible,
        # sobraba un hueco grande a la derecha y se veia desprolijo).
        # Si en algun momento el contenido termina siendo MAS ancho
        # que el area visible (un caso limite que no deberia pasar
        # gracias al calculo adaptativo, pero por las dudas), se cae
        # solo al scroll horizontal en vez de romper nada.
        def _centrar_cuerpo(_ev=None):
            canvas_scroll.update_idletasks()
            ancho_canvas = canvas_scroll.winfo_width()
            ancho_cuerpo = cuerpo.winfo_reqwidth()
            alto_canvas = canvas_scroll.winfo_height()
            alto_cuerpo = cuerpo.winfo_reqheight()
            x = max(0, (ancho_canvas - ancho_cuerpo) // 2)
            y = max(0, (alto_canvas - alto_cuerpo) // 2)
            canvas_scroll.coords(id_ventana_cuerpo, x, y)
            canvas_scroll.configure(scrollregion=canvas_scroll.bbox("all"))

        canvas_scroll.bind("<Configure>", _centrar_cuerpo)
        cuerpo.bind("<Configure>", _centrar_cuerpo)

        def _rueda_vertical(evento):
            canvas_scroll.yview_scroll(int(-1 * (evento.delta / 120)), "units")

        def _rueda_horizontal(evento):
            canvas_scroll.xview_scroll(int(-1 * (evento.delta / 120)), "units")

        # El mouse sobre la grilla scrollea vertical (rueda normal) u
        # horizontal (Shift + rueda) -- pero solo mientras el cursor
        # esta arriba de esta zona, para no robarle la rueda del mouse
        # a otras partes del programa (por eso se ata/desata en
        # Enter/Leave en vez de dejarla pegada para siempre).
        def _activar_rueda(_ev=None):
            canvas_scroll.bind_all("<MouseWheel>", _rueda_vertical)
            canvas_scroll.bind_all("<Shift-MouseWheel>", _rueda_horizontal)

        def _desactivar_rueda(_ev=None):
            canvas_scroll.unbind_all("<MouseWheel>")
            canvas_scroll.unbind_all("<Shift-MouseWheel>")

        canvas_scroll.bind("<Enter>", _activar_rueda)
        canvas_scroll.bind("<Leave>", _desactivar_rueda)

        canvas_scroll.pack(side="left", fill="both", expand=True)
        scrollbar_v.pack(side="right", fill="y")
        scrollbar_h.pack(side="bottom", fill="x")

        # --- grilla ---
        self._sopa_celda_px = round(30 * (0.7 + 0.3 * e))
        margen = 6
        ancho_grilla = self.sopa["ancho"] * self._sopa_celda_px + margen * 2
        alto_grilla = self.sopa["alto"] * self._sopa_celda_px + margen * 2
        self._sopa_margen = margen

        panel_grilla = tk.Frame(cuerpo, bg=t["card_bg"], highlightthickness=1,
                                 highlightbackground=t["card_borde"])
        panel_grilla.pack(side="left", anchor="n", padx=(4, 0), pady=4)
        cv = tk.Canvas(panel_grilla, width=ancho_grilla, height=alto_grilla,
                        bg=t["card_bg"], highlightthickness=0)
        cv.pack(padx=4, pady=4)
        self.sopa_canvas = cv

        self._f_sopa_letra = tkfont.Font(family="Segoe UI", size=round(13 * e), weight="bold")

        self._sopa_letra_ids = {}
        for f, fila in enumerate(self.sopa["grilla"]):
            for c, letra in enumerate(fila):
                cx = margen + c * self._sopa_celda_px + self._sopa_celda_px / 2
                cy = margen + f * self._sopa_celda_px + self._sopa_celda_px / 2
                id_letra = cv.create_text(cx, cy, text=letra, font=self._f_sopa_letra,
                                           fill=t["texto_primario"])
                self._sopa_letra_ids[(f, c)] = id_letra

        # Las palabras ya encontradas en una sopa anterior a un cambio
        # de tema/letra (que reconstruye toda la vista) se vuelven a
        # pintar de una, para no perder el progreso visual.
        for palabra_info in self.sopa["palabras"]:
            if palabra_info["encontrada"]:
                self._pintar_palabra_encontrada(palabra_info, permanente=True, sin_animacion=True)

        cv.bind("<ButtonPress-1>", self._sopa_click_inicio)
        cv.bind("<B1-Motion>", self._sopa_arrastrando)
        cv.bind("<ButtonRelease-1>", self._sopa_soltar)

        # --- panel de palabras a buscar, con SU PROPIO scroll vertical
        # (independiente del de la grilla) para cuando la lista de 24
        # palabras no entra completa en el alto disponible ---
        ancho_panel_palabras = 220
        panel_palabras_borde = tk.Frame(cuerpo, bg=t["card_borde"], bd=0,
                                         width=ancho_panel_palabras + 20, height=alto_grilla + 8)
        panel_palabras_borde.pack(side="left", anchor="n", padx=(14, 4), pady=4)
        panel_palabras_borde.pack_propagate(False)
        panel_palabras_int = tk.Frame(panel_palabras_borde, bg=t["ventana_bg"])
        panel_palabras_int.pack(padx=1, pady=1, fill="both", expand=True)

        canvas_pal = tk.Canvas(panel_palabras_int, bg=t["ventana_bg"], highlightthickness=0)
        scrollbar_pal = ttk.Scrollbar(panel_palabras_int, orient="vertical",
                                       command=canvas_pal.yview, style=estilo_v)
        panel_palabras = tk.Frame(canvas_pal, bg=t["ventana_bg"])
        self._panel_palabras_widget = panel_palabras

        panel_palabras.bind(
            "<Configure>", lambda ev: canvas_pal.configure(scrollregion=canvas_pal.bbox("all")))
        id_ventana_pal = canvas_pal.create_window((0, 0), window=panel_palabras, anchor="nw")
        canvas_pal.configure(yscrollcommand=scrollbar_pal.set)
        canvas_pal.bind("<Configure>",
                         lambda ev: canvas_pal.itemconfig(id_ventana_pal, width=ev.width))

        def _rueda_palabras(evento):
            canvas_pal.yview_scroll(int(-1 * (evento.delta / 120)), "units")

        canvas_pal.bind("<Enter>", lambda ev: canvas_pal.bind_all("<MouseWheel>", _rueda_palabras))
        canvas_pal.bind("<Leave>", lambda ev: canvas_pal.unbind_all("<MouseWheel>"))

        canvas_pal.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=6)
        scrollbar_pal.pack(side="right", fill="y", pady=6)

        tk.Label(panel_palabras, text="PALABRAS", font=self._f_boton_sub,
                 bg=t["ventana_bg"], fg=t["texto_secundario"]).pack(anchor="w", pady=(0, 6))

        self._sopa_labels_palabras = {}
        for palabra_info in sorted(self.sopa["palabras"], key=lambda pi: (pi["encontrada"], pi["palabra"])):
            palabra = palabra_info["palabra"]
            fuente_palabra = tkfont.Font(family="Segoe UI", size=round(11 * e))
            encontrada = palabra_info["encontrada"]
            if encontrada:
                fuente_palabra.configure(overstrike=1)
            lbl = tk.Label(panel_palabras, text=palabra.capitalize(), font=fuente_palabra,
                            bg=t["ventana_bg"],
                            fg=self._color_sopa(palabra_info) if encontrada else t["texto_primario"],
                            anchor="w")
            lbl.pack(anchor="w", pady=2)
            self._sopa_labels_palabras[palabra] = (lbl, fuente_palabra)

        # --- pie fijo (fuera del area con scroll, siempre visible):
        # cronometro mientras se juega, cartel de COMPLETADA al
        # terminar ---
        frame_pie = tk.Frame(col, bg=t["ventana_bg"])
        frame_pie.pack(fill="x", pady=(10, 0))
        self._sopa_label_tiempo = tk.Label(
            frame_pie, text="", font=self._f_subtitulo_seccion,
            bg=t["ventana_bg"], fg=t["dorado"] if self.sopa["completada"] else t["texto_secundario"])
        self._sopa_label_tiempo.pack(anchor="w")

        self._sopa_actualizar_label_tiempo()
        if not self.sopa["completada"]:
            self._sopa_tick()

    def _sopa_formatear_tiempo(self, segundos):
        segundos = int(segundos)
        return f"{segundos // 60:02d}:{segundos % 60:02d}"

    def _sopa_actualizar_label_tiempo(self):
        if not hasattr(self, "_sopa_label_tiempo") or not self._sopa_label_tiempo.winfo_exists():
            return
        if self.sopa["completada"]:
            texto_tiempo = self._sopa_formatear_tiempo(self.sopa["tiempo_final"])
            puntaje = self._calcular_puntaje_sopa(self.sopa["tiempo_final"])
            self._sopa_label_tiempo.config(
                text=f"\U0001F389 ¡COMPLETADA!  \u00b7  Tiempo: {texto_tiempo}  \u00b7  Puntaje: {puntaje}",
                fg=self.tema["dorado"])
        else:
            transcurrido = time.time() - self.sopa["tiempo_inicio"]
            texto_tiempo = self._sopa_formatear_tiempo(transcurrido)
            self._sopa_label_tiempo.config(
                text=f"\u23f1 Tiempo: {texto_tiempo}", fg=self.tema["texto_secundario"])

    def _sopa_tick(self):
        # Se corta solo si la vista ya no esta en pantalla (se cambio
        # de pestana, o se reconstruyo por un cambio de tema/letra --
        # en ese caso _armar_vista_sopa ya arranco un tick nuevo, asi
        # que este viejo simplemente no tiene mas nada que actualizar)
        # o si la sopa se completo mientras tanto.
        if not hasattr(self, "sopa_canvas") or not self.sopa_canvas.winfo_exists():
            return
        if self.sopa["completada"]:
            return
        self._sopa_actualizar_label_tiempo()
        self.root.after(1000, self._sopa_tick)

    def _calcular_puntaje_sopa(self, segundos):
        return max(SOPA_PUNTAJE_MINIMO,
                    SOPA_PUNTAJE_BASE - int(segundos * SOPA_PENALIZACION_POR_SEGUNDO))

    def _guardar_puntaje_sopa(self, segundos, puntaje):
        """Guarda un registro en ranking_sopa.json (fecha, tiempo,
        puntaje). Por ahora nadie lee este archivo todavia -- es la
        base de datos para la vista de "mejores puntajes" que armamos
        mas adelante. Si el archivo no existe o esta corrupto, arranca
        una lista nueva en vez de romper el programa."""
        registro = {
            "fecha": datetime.now().isoformat(timespec="seconds"),
            "segundos": int(segundos),
            "puntaje": puntaje,
            "palabras": len(self.sopa["palabras"]),
            "grilla": f'{self.sopa["ancho"]}x{self.sopa["alto"]}',
        }
        ranking = []
        try:
            if os.path.exists(RANKING_SOPA_PATH):
                with open(RANKING_SOPA_PATH, "r", encoding="utf-8") as f:
                    cargado = json.load(f)
                if isinstance(cargado, list):
                    ranking = cargado
        except Exception as e:
            log(f"No se pudo leer ranking_sopa.json, se arranca uno nuevo: {e}")

        ranking.append(registro)
        ranking = ranking[-200:]  # tope razonable, no crece para siempre

        try:
            with open(RANKING_SOPA_PATH, "w", encoding="utf-8") as f:
                json.dump(ranking, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log(f"No se pudo guardar el puntaje de la sopa: {e}")

    def _nueva_sopa(self):
        self.sopa = self._iniciar_sopa_nueva(self.frame_contenido)
        self._mostrar_vista("sopa")

    def _sopa_fila_col_desde_evento(self, evento):
        c = int((evento.x - self._sopa_margen) // self._sopa_celda_px)
        f = int((evento.y - self._sopa_margen) // self._sopa_celda_px)
        if 0 <= f < self.sopa["alto"] and 0 <= c < self.sopa["ancho"]:
            return f, c
        return None

    def _sopa_centro_celda(self, f, c):
        x = self._sopa_margen + c * self._sopa_celda_px + self._sopa_celda_px / 2
        y = self._sopa_margen + f * self._sopa_celda_px + self._sopa_celda_px / 2
        return x, y

    def _sopa_click_inicio(self, evento):
        celda = self._sopa_fila_col_desde_evento(evento)
        self._sopa_inicio_arrastre = celda
        self._sopa_inicio_pixeles = (evento.x, evento.y)
        self._sopa_direccion_bloqueada = None
        if self._sopa_preview_id is not None:
            self.sopa_canvas.delete(self._sopa_preview_id)
            self._sopa_preview_id = None

    def _sopa_arrastrando(self, evento):
        if self._sopa_inicio_arrastre is None:
            return
        f0, c0 = self._sopa_inicio_arrastre

        if self._sopa_direccion_bloqueada is None:
            # Todavia no se definio una direccion para este arrastre.
            # OJO ACA -- esta es la parte que estaba mal antes: decidia
            # la direccion apenas el mouse cruzaba a la celda de al
            # lado (es decir, con un solo paso de diferencia). A esa
            # distancia tan corta, un arrastre en diagonal
            # practicamente SIEMPRE cruza primero el borde de una
            # columna o el de una fila (nunca los dos exactamente al
            # mismo tiempo), asi que lo que se terminaba detectando
            # como "primer movimiento" era horizontal o vertical puro
            # por pura casualidad del orden de los pixeles, aunque la
            # mano se estuviera moviendo en diagonal. Por eso "no
            # funcionaba" la diagonal.
            #
            # Ahora se espera a que el mouse se haya alejado un poco
            # mas del punto de partida (en PIXELES, no en celdas) antes
            # de decidir -- con mas distancia recorrida, el angulo real
            # del arrastre se nota mucho mejor y no lo arruina ese
            # primer paso ambiguo.
            x0, y0 = self._sopa_inicio_pixeles
            dx, dy = evento.x - x0, evento.y - y0
            distancia = math.hypot(dx, dy)
            if distancia < self._sopa_celda_px * 1.2:
                return  # todavia no se alejo lo suficiente para saber bien el angulo
            angulo = math.atan2(dy, dx)
            octantes = [(0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)]
            indice = round(angulo / (math.pi / 4)) % 8
            self._sopa_direccion_bloqueada = octantes[indice]

        celda = self._sopa_fila_col_desde_evento(evento)
        if celda is None:
            return
        df, dc = self._sopa_direccion_bloqueada
        largo = self._sopa_proyectar_largo(f0, c0, celda[0], celda[1], df, dc)

        if self._sopa_preview_id is not None:
            self.sopa_canvas.delete(self._sopa_preview_id)
            self._sopa_preview_id = None
        if largo == 0:
            return
        f1, c1 = f0 + df * largo, c0 + dc * largo
        x0, y0 = self._sopa_centro_celda(f0, c0)
        x1, y1 = self._sopa_centro_celda(f1, c1)
        t = self.tema
        self._sopa_preview_id = self.sopa_canvas.create_line(
            x0, y0, x1, y1, width=self._sopa_celda_px * 0.75,
            fill=t["azul_link"], capstyle="round", stipple="gray50")
        self.sopa_canvas.tag_lower(self._sopa_preview_id)

    @staticmethod
    def _sopa_proyectar_largo(f0, c0, f_actual, c_actual, df, dc):
        """Con la direccion YA fija (ver _sopa_arrastrando), calcula
        cuantos pasos hay que dar en esa direccion para llegar lo mas
        cerca posible de donde esta el mouse ahora -- si el mouse se
        desvia un poco de la linea recta (mano temblorosa, diagonal
        imperfecta) esto lo "endereza" en vez de resetear la
        direccion elegida."""
        if df != 0 and dc != 0:
            largo = round(((f_actual - f0) * df + (c_actual - c0) * dc) / 2)
        elif df != 0:
            largo = (f_actual - f0) * df
        else:
            largo = (c_actual - c0) * dc
        return max(0, largo)

    def _sopa_soltar(self, evento):
        if self._sopa_inicio_arrastre is None:
            return
        celda = self._sopa_fila_col_desde_evento(evento)
        f0, c0 = self._sopa_inicio_arrastre
        direccion = self._sopa_direccion_bloqueada
        x0, y0 = self._sopa_inicio_pixeles if self._sopa_inicio_pixeles else (evento.x, evento.y)
        self._sopa_inicio_arrastre = None
        self._sopa_inicio_pixeles = None
        self._sopa_direccion_bloqueada = None

        if self._sopa_preview_id is not None:
            self.sopa_canvas.delete(self._sopa_preview_id)
            self._sopa_preview_id = None

        if celda is None:
            return
        if direccion is None:
            # El arrastre se solto antes de llegar al umbral de
            # distancia que usa _sopa_arrastrando para fijar una
            # direccion (arrastre corto y rapido, tipico de una
            # palabra de pocas letras) -- se calcula la direccion con
            # lo que hay, en vez de descartar la seleccion sin mas.
            dx, dy = evento.x - x0, evento.y - y0
            if dx == 0 and dy == 0:
                return
            angulo = math.atan2(dy, dx)
            octantes = [(0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1), (-1, 0), (-1, 1)]
            indice = round(angulo / (math.pi / 4)) % 8
            direccion = octantes[indice]
        df, dc = direccion
        largo = self._sopa_proyectar_largo(f0, c0, celda[0], celda[1], df, dc)
        if largo == 0:
            return
        f1, c1 = f0 + df * largo, c0 + dc * largo

        for palabra_info in self.sopa["palabras"]:
            if palabra_info["encontrada"]:
                continue
            largo_palabra = len(palabra_info["palabra"])
            pf0, pc0 = palabra_info["fila"], palabra_info["columna"]
            pf1 = pf0 + palabra_info["df"] * (largo_palabra - 1)
            pc1 = pc0 + palabra_info["dc"] * (largo_palabra - 1)
            coincide_derecho = (f0, c0) == (pf0, pc0) and (f1, c1) == (pf1, pc1)
            coincide_reves = (f0, c0) == (pf1, pc1) and (f1, c1) == (pf0, pc0)
            if coincide_derecho or coincide_reves:
                palabra_info["encontrada"] = True
                palabra_info["color_indice"] = self.sopa.get("siguiente_color", 0)
                self.sopa["siguiente_color"] = palabra_info["color_indice"] + 1
                self._pintar_palabra_encontrada(palabra_info, permanente=True)
                self._marcar_palabra_encontrada_en_lista(palabra_info)
                self._sopa_reordenar_lista_palabras()
                if all(p["encontrada"] for p in self.sopa["palabras"]):
                    self.sopa["completada"] = True
                    self.sopa["tiempo_final"] = time.time() - self.sopa["tiempo_inicio"]
                    puntaje = self._calcular_puntaje_sopa(self.sopa["tiempo_final"])
                    self._guardar_puntaje_sopa(self.sopa["tiempo_final"], puntaje)
                    self._sopa_actualizar_label_tiempo()
                self._guardar_sopa_actual()
                return

    def _sopa_reordenar_lista_palabras(self):
        """Las palabras ya encontradas bajan al final de la lista,
        dejando arriba (en orden alfabetico) las que todavia faltan --
        no hace falta reconstruir nada, alcanza con volver a "empacar"
        cada Label en el nuevo orden (Tkinter respeta el orden de
        los .pack() para decidir que va arriba de que)."""
        orden = sorted(self.sopa["palabras"], key=lambda pi: (pi["encontrada"], pi["palabra"]))
        for palabra_info in orden:
            par = self._sopa_labels_palabras.get(palabra_info["palabra"])
            if par:
                lbl, _fuente = par
                lbl.pack_forget()
                lbl.pack(anchor="w", pady=2)

    def _color_sopa(self, palabra_info):
        t = self.tema
        paleta = t["paleta_sopa"]
        indice = palabra_info.get("color_indice", 0) % len(paleta)
        return paleta[indice]

    def _pintar_palabra_encontrada(self, palabra_info, permanente=False, sin_animacion=False):
        color = self._color_sopa(palabra_info)
        largo = len(palabra_info["palabra"])
        f0, c0 = palabra_info["fila"], palabra_info["columna"]
        f1 = f0 + palabra_info["df"] * (largo - 1)
        c1 = c0 + palabra_info["dc"] * (largo - 1)
        x0, y0 = self._sopa_centro_celda(f0, c0)
        x1, y1 = self._sopa_centro_celda(f1, c1)
        linea_id = self.sopa_canvas.create_line(
            x0, y0, x1, y1, width=self._sopa_celda_px * 0.75,
            fill=color, capstyle="round")
        self.sopa_canvas.tag_lower(linea_id)
        f, c = f0, c0
        for _ in range(largo):
            id_letra = self._sopa_letra_ids.get((f, c))
            if id_letra is not None:
                # Blanco/negro segun tan clara u oscura es la linea de
                # fondo, asi la letra siempre se lee bien encima de
                # cualquiera de los 10 colores de la paleta.
                self.sopa_canvas.itemconfig(id_letra, fill=_color_texto_legible(color))
            f += palabra_info["df"]
            c += palabra_info["dc"]

    def _marcar_palabra_encontrada_en_lista(self, palabra_info):
        par = self._sopa_labels_palabras.get(palabra_info["palabra"])
        if not par:
            return
        lbl, fuente = par
        fuente.configure(overstrike=1)
        lbl.config(fg=self._color_sopa(palabra_info))

    def _estilo_scrollbar(self, orientacion="vertical"):
        """
        La Scrollbar de Tkinter de fabrica es la clasica gris con
        flechitas de los 90 y no respeta el tema. Con ttk + el theme
        'clam' (el unico que permite recolorear todo a mano) se arma
        una mas fina, sin flechas, en los colores del tema actual.
        orientacion: "vertical" u "horizontal" (la sopa de letras usa
        las dos; la lista de partidos solo la vertical).
        """
        t = self.tema
        nombre = f"Delgada.{orientacion.capitalize()}.TScrollbar"
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(nombre, gripcount=0, background=t["texto_secundario"],
                        darkcolor=t["texto_secundario"], lightcolor=t["texto_secundario"],
                        troughcolor=t["card_bg"], bordercolor=t["card_bg"],
                        arrowsize=0, arrowcolor=t["card_bg"], relief="flat", width=9)
        style.map(nombre, background=[("active", t["verde"])])
        return nombre

    def _armar_seccion_partidos(self, parent):
        t = self.tema

        # Columna centrada de ancho fijo (mas generosa que la del panel
        # del temporizador, para que los partidos tengan lugar de sobra
        # para una letra mas grande) en vez de estirarse a lo ancho de
        # toda la ventana maximizada -- eso es lo que antes dejaba un
        # hueco vacio enorme a la derecha de cada fila.
        col = tk.Frame(parent, bg=t["ventana_bg"], width=ANCHO_SECCION_PARTIDOS)
        col.pack(pady=(20, 10), fill="y", expand=True)
        col.pack_propagate(False)

        frame_tit = tk.Frame(col, bg=t["ventana_bg"])
        frame_tit.pack(anchor="w")
        tk.Label(frame_tit, text="\U0001F4C5", font=("Segoe UI Emoji", 15),
                 bg=t["ventana_bg"], fg=t["texto_primario"]).pack(side="left", padx=(0, 8))
        tk.Label(frame_tit, text="PARTIDOS DE HOY", font=self._f_subtitulo_seccion,
                 bg=t["ventana_bg"], fg=t["texto_primario"]).pack(side="left")

        contenedor = tk.Frame(col, bg=t["card_borde"], bd=0)
        contenedor.pack(pady=(8, 10), fill="both", expand=True)
        interior = tk.Frame(contenedor, bg=t["card_bg"])
        interior.pack(padx=1, pady=1, fill="both", expand=True)

        canvas_scroll = tk.Canvas(interior, bg=t["card_bg"], highlightthickness=0)
        estilo_barra = self._estilo_scrollbar()
        scrollbar = ttk.Scrollbar(interior, orient="vertical", command=canvas_scroll.yview,
                                   style=estilo_barra)
        self.frame_lista = tk.Frame(canvas_scroll, bg=t["card_bg"])

        self.frame_lista.bind(
            "<Configure>",
            lambda e: canvas_scroll.configure(scrollregion=canvas_scroll.bbox("all")),
        )
        self._id_ventana_lista = canvas_scroll.create_window((0, 0), window=self.frame_lista,
                                                               anchor="nw")
        canvas_scroll.configure(yscrollcommand=scrollbar.set)
        canvas_scroll.bind(
            "<Configure>",
            lambda e: canvas_scroll.itemconfig(self._id_ventana_lista, width=e.width),
        )

        def _rueda(evento):
            canvas_scroll.yview_scroll(int(-1 * (evento.delta / 120)), "units")

        canvas_scroll.bind_all("<MouseWheel>", _rueda)

        canvas_scroll.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        scrollbar.pack(side="right", fill="y")
        self.canvas_scroll_lista = canvas_scroll

        # Si ya se habian traido partidos en una actualizacion anterior
        # (por ejemplo, se volvio a esta pestaña despues de andar en
        # Sopa/Solitario), se muestran de una en vez de decir
        # "Buscando partidos..." y dejar al usuario esperando hasta la
        # proxima actualizacion en segundo plano (que puede tardar
        # horas).
        if self.partidos:
            self._refrescar_lista_ui()
        else:
            self._mostrar_texto_lista("Buscando partidos...")

    def _armar_footer(self, parent):
        t = self.tema
        tk.Label(parent, text="(si se cierra esta ventana con la X, queda"
                               " minimizada abajo en la barra de tareas)",
                 font=self._f_footer, bg=t["ventana_bg"], fg=t["texto_secundario"]
                 ).pack(pady=(0, 12))

    def _armar_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Abrir", self._mostrar_ventana, default=True),
            pystray.MenuItem("Salir", self._salir),
        )
        self.tray_icon = pystray.Icon("futbol_recordatorios", crear_imagen_icono(),
                                       "Futbol y Recordatorios", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _minimizar_a_bandeja(self):
        self.root.iconify()

    def _mostrar_ventana(self, icon=None, item=None):
        self.root.after(0, self.root.deiconify)

    def _salir(self, icon=None, item=None):
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.after(0, self.root.destroy)
        os._exit(0)

    # ---------------- TEMA ----------------
    def _revisar_cambio_tema(self):
        # Si el usuario ya eligio un tema a mano con el selector del
        # header, se respeta esa eleccion y se deja de seguir el tema
        # de Windows automaticamente (hasta que se reinicie el
        # programa).
        if self.tema_manual is not None:
            return
        nuevo = TEMAS["oscuro"] if _tema_windows_es_oscuro() else TEMAS["claro"]
        if nuevo is not self.tema:
            self.tema = nuevo
            log("Cambio de tema de Windows detectado, redibujando la interfaz.")
            self._reconstruir_ui()

    def _reconstruir_ui(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        self._armar_ventana()
        # La lista de partidos solo existe si la vista activa es
        # Futbol (en Sopa/Solitario ese frame ni se crea).
        if self.vista_actual == "futbol":
            self._refrescar_lista_ui()

    def _popup_aviso(self):
        """Popup grande de 'ES HORA DE MEDIRSE' -- lo dispara
        PanelTimer._finalizar() cuando el temporizador llega a cero,
        pero se queda aca en App porque no es parte del panel en si
        (igual que la alerta de partido de Boca, es una accion puntual
        que dispara el timer, no el widget del timer)."""
        t = self.tema
        ventana = tk.Toplevel(self.root)
        ventana.title("Recordatorio")
        ventana.geometry("460x300")
        ventana.configure(bg=t["rojo"])
        ventana.resizable(False, False)
        ventana.attributes("-topmost", True)
        try:
            ventana.iconbitmap(ICONO_PATH)
        except Exception:
            pass

        frame_top = tk.Frame(ventana, bg=t["rojo"])
        frame_top.pack(fill="both", expand=True)

        circulo = tk.Canvas(frame_top, width=80, height=80, bg=t["rojo"],
                            highlightthickness=0)
        circulo.pack(pady=(26, 10))
        circulo.create_oval(4, 4, 76, 76, fill="white", outline="")
        circulo.create_text(40, 40, text="\u23f0", font=("Segoe UI Emoji", 30))

        tk.Label(frame_top, text="\u00a1ES HORA DE\nMEDIRSE!", font=_fuente(20, "bold"),
                 bg=t["rojo"], fg="white", justify="center").pack(pady=(0, 10))
        tk.Label(frame_top, text="Pasaron las 2 horas de la comida",
                 font=("Segoe UI", 11), bg=t["rojo"], fg="#ffe4e0").pack()

        frame_bottom = tk.Frame(ventana, bg="white")
        frame_bottom.pack(fill="x", side="bottom")

        cv_boton = tk.Canvas(frame_bottom, width=400, height=60, bg="white",
                             highlightthickness=0)
        cv_boton.pack(pady=(18, 6))
        rect = _redondear(cv_boton, 0, 0, 400, 60, 14, fill=t["rojo"], outline="")
        texto = cv_boton.create_text(200, 30, text="\u2705  YA ME MED\u00cd, CERRAR",
                                      font=_fuente(13, "bold"), fill="white")
        for iid in (rect, texto):
            cv_boton.tag_bind(iid, "<Button-1>", lambda e: ventana.destroy())
        cv_boton.tag_bind(rect, "<Enter>", lambda e: cv_boton.config(cursor="hand2"))

        tk.Label(frame_bottom, text="Este recordatorio se puede cerrar cuando termines.",
                 font=("Segoe UI", 9), bg="white", fg="#888").pack(pady=(0, 14))

        ventana.lift()
        ventana.focus_force()

    # ---------------- ESCUDOS ----------------
    def _ruta_escudo_en_disco(self, url, tamano):
        """Todos los escudos ya procesados (recortados y del tamano
        justo que se usa en pantalla) se guardan como archivos .png
        sueltos en la carpeta escudos_cache/, aparte del resto del
        codigo. El nombre de archivo es un hash del link original,
        para no depender de caracteres raros que traigan los nombres
        de equipo."""
        os.makedirs(ESCUDOS_DIR, exist_ok=True)
        nombre = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return os.path.join(ESCUDOS_DIR, f"{nombre}_{tamano}.png")

    def _obtener_imagen_escudo(self, url, tamano=34):
        if not url:
            return None
        clave = (url, tamano)
        actual = self._escudo_cache.get(clave)
        if actual == "cargando":
            return None
        if actual is not None:
            return actual

        # Antes de salir a internet, se fija si ya la tiene guardada
        # en disco de una corrida anterior (esto es lo que hace que,
        # con el tiempo, cada vez haga falta pedirle menos cosas a las
        # APIs externas).
        ruta = self._ruta_escudo_en_disco(url, tamano)
        if os.path.exists(ruta):
            try:
                foto = ImageTk.PhotoImage(Image.open(ruta))
                self._escudo_cache[clave] = foto
                return foto
            except Exception:
                pass  # el archivo esta corrupto o similar, se vuelve a bajar

        self._escudo_cache[clave] = "cargando"
        threading.Thread(target=self._descargar_escudo, args=(url, tamano),
                          daemon=True).start()
        return None

    def _descargar_escudo(self, url, tamano):
        try:
            headers = {"User-Agent": "FutbolYRecordatorios/1.0 (uso personal, app de escritorio)"}
            r = requests.get(url, timeout=8, headers=headers)
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content)).convert("RGBA")
            img.thumbnail((tamano, tamano), Image.LANCZOS)
            lienzo = Image.new("RGBA", (tamano, tamano), (0, 0, 0, 0))
            lienzo.paste(img, ((tamano - img.width) // 2, (tamano - img.height) // 2), img)

            try:
                lienzo.save(self._ruta_escudo_en_disco(url, tamano))
            except Exception as e:
                log(f"No se pudo guardar el escudo en disco (no es grave): {e}")

            self.root.after(0, self._guardar_escudo_descargado, url, tamano, lienzo)
        except Exception as e:
            log(f"No se pudo descargar un escudo: {e}")
            self.root.after(0, self._marcar_escudo_fallido, url, tamano)

    def _guardar_escudo_descargado(self, url, tamano, imagen_pil):
        try:
            foto = ImageTk.PhotoImage(imagen_pil)
        except Exception:
            foto = None
        self._escudo_cache[(url, tamano)] = foto
        self._refrescar_lista_ui()

    def _marcar_escudo_fallido(self, url, tamano):
        self._escudo_cache[(url, tamano)] = None

    # ---------------- PARTIDOS ----------------
    def _revisar_actualizacion(self):
        try:
            if actualizador.revisar_actualizacion(self.config, log=log):
                log("Reiniciando el programa para aplicar la actualizacion...")
                actualizador.reiniciar_programa()
        except Exception as e:
            log(f"Error revisando actualizacion: {e}")

    def _ciclo_de_fondo(self):
        self._revisar_actualizacion()
        log("Resolviendo competiciones...")
        api.resolver_ligas(self.config, log=log)
        ultimo_chequeo_actualizacion = time.time()
        while True:
            self._actualizar_partidos()
            intervalo = self.config.get("intervalo_actualizacion_minutos", 240) * 60
            transcurrido = 0
            while transcurrido < intervalo:
                self._chequear_avisos_previos()
                self.root.after(0, self._revisar_cambio_tema)
                time.sleep(60)
                transcurrido += 60
                if time.time() - ultimo_chequeo_actualizacion > 24 * 3600:
                    ultimo_chequeo_actualizacion = time.time()
                    self._revisar_actualizacion()

    def _actualizar_partidos(self):
        log("Actualizando lista de proximos partidos...")
        partidos = api.obtener_proximos_partidos(self.config, log=log)
        self.partidos = partidos
        self.root.after(0, self._refrescar_lista_ui)

    def _lista_partidos_visible(self):
        """True solo si la vista Futbol esta activa Y el frame de la
        lista todavia existe. Hace falta este chequeo doble porque la
        actualizacion de partidos corre en el hilo de fondo cada varias
        horas: si mientras tanto se cambio a la pestaña Sopa o
        Solitario, ese frame ya fue destruido por _mostrar_vista y
        tocarlo desde aca tira 'bad window path name' (era el error
        que aparecia en el registro.log al cambiar de pestaña)."""
        frame = getattr(self, "frame_lista", None)
        return (self.vista_actual == "futbol" and frame is not None
                and frame.winfo_exists())

    def _mostrar_texto_lista(self, texto):
        if not self._lista_partidos_visible():
            return
        t = self.tema
        for widget in self.frame_lista.winfo_children():
            widget.destroy()
        tk.Label(self.frame_lista, text=texto, font=self._f_equipo, bg=t["card_bg"],
                 fg=t["texto_secundario"]).pack(pady=30)

    def _refrescar_lista_ui(self):
        if not self._lista_partidos_visible():
            return
        if not self.partidos:
            self._mostrar_texto_lista("No hay partidos programados para hoy.")
            return

        for widget in self.frame_lista.winfo_children():
            widget.destroy()

        for p in self.partidos[:15]:
            self._crear_fila_partido(p)

    def _crear_fila_partido(self, p):
        t = self.tema
        # Fila UNICA (Etapa 3, rediseno v2): a la izquierda hora +
        # equipos + escudos, a la derecha -- separada por una linea
        # vertical -- una columnita angosta con la competicion arriba
        # (logo + nombre) y el canal de TV abajo (logo + nombre, o el
        # link de "buscar en internet" si no se encontro). Mismos
        # datos de siempre (p["local"], p["destacado"], escudos) mas
        # p["logo_competicion"] y p["canal_tv"] de la Etapa 3.
        #
        # Todo lo horizontal del bloque izquierdo queda FIJO (no se
        # escala con la escala de texto): el wrap automatico de Canvas
        # ya se encarga de pasar un nombre de equipo largo a una
        # segunda linea cuando la letra es grande, sin pisar el "vs".
        # Escalar tambien los anchos aca terminaba comiendose el
        # espacio de la columna derecha (competicion/canal), que es la
        # que mas lo necesita cuando el texto es grande. Lo unico que
        # crece con la escala es el ALTO de la fila, para darle lugar
        # a esas lineas extra sin que se pisen. Uso explicitamente la
        # escala de "futbol" (no self._escala_actual()) porque esta
        # funcion dibuja SIEMPRE filas de partidos, sin importar en que
        # pestana este parado el usuario cuando esto se reconstruye.
        e = self.escalas_texto["futbol"]

        ancho_fila = ANCHO_SECCION_PARTIDOS - 78
        alto_fila = max(80, round(92 + (e - 1.0) * 140))
        tamano_escudo = 40

        cv = tk.Canvas(self.frame_lista, width=ancho_fila, height=alto_fila,
                       bg=t["card_bg"], highlightthickness=0)
        cv.pack(fill="x", padx=8, pady=5)

        destacado = bool(p.get("destacado"))
        fondo = t["dorado_bg"] if destacado else t["card_bg"]
        borde = t["dorado_borde"] if destacado else t["card_borde"]
        _redondear(cv, 1, 1, ancho_fila - 1, alto_fila - 1, 14, fill=fondo, outline=borde)

        cv._referencias = []

        # ==================== BLOQUE IZQUIERDO: hora + equipos ====================
        ym = alto_fila / 2

        bx1, by1, bx2, by2 = 12, 10, 104, alto_fila - 10
        badge_bg = t["dorado_bg"] if destacado else t["badge_hora_bg"]
        badge_fg = t["dorado"] if destacado else t["badge_hora_texto"]
        _redondear(cv, bx1, by1, bx2, by2, 10, fill=badge_bg, outline="")
        bxm = (bx1 + bx2) / 2
        cv.create_text(bxm, ym - 10, text=p["fecha"].strftime("%H:%M"),
                        font=self._f_hora, fill=badge_fg)
        cv.create_text(bxm, ym + 11, text=p["fecha"].strftime("%d/%m"),
                        font=self._f_fecha, fill=badge_fg)

        if destacado:
            # La estrella de "destacado" va aparte, como una insignia en
            # la esquina de toda la tarjeta -- si se mete adentro del
            # badge de la hora, descentra la hora respecto de la fecha
            # (una linea queda mas ancha que la otra al llevar la
            # estrella pegada).
            cv.create_text(7, 4, text="\u2b50", font=("Segoe UI Emoji", 10),
                            fill=t["dorado"], anchor="nw")

        x = 120
        radio_escudo = tamano_escudo / 2
        ancho_equipo = 210
        ancho_vs = 32

        img_local = self._obtener_imagen_escudo(p.get("escudo_local"), tamano=tamano_escudo)
        if img_local:
            cv.create_image(x + radio_escudo, ym, image=img_local)
            cv._referencias.append(img_local)
        else:
            cv.create_text(x + radio_escudo, ym, text="\u26bd",
                            font=("Segoe UI Emoji", 17), fill=t["texto_secundario"])
        x += tamano_escudo + 8

        cv.create_text(x, ym, text=p["local"], font=self._f_equipo,
                        fill=t["texto_primario"], anchor="w", width=ancho_equipo)
        x += ancho_equipo + 14

        cv.create_text(x, ym, text="vs", font=self._f_vs, fill=t["texto_secundario"])
        x += ancho_vs

        cv.create_text(x, ym, text=p["visitante"], font=self._f_equipo,
                        fill=t["texto_primario"], anchor="w", width=ancho_equipo)
        x += ancho_equipo + 8

        img_visitante = self._obtener_imagen_escudo(p.get("escudo_visitante"), tamano=tamano_escudo)
        if img_visitante:
            cv.create_image(x + radio_escudo, ym, image=img_visitante)
            cv._referencias.append(img_visitante)
        else:
            cv.create_text(x + radio_escudo, ym, text="\u26bd",
                            font=("Segoe UI Emoji", 17), fill=t["texto_secundario"])
        x += tamano_escudo

        # ==================== linea vertical separadora ====================
        # Un poco mas marcada que "borde" (el borde de la tarjeta es muy
        # sutil a proposito, pero ahi adentro esta linea es la unica
        # pista visual de que hay dos zonas separadas, asi que conviene
        # que se note un poco mas).
        x_div = x + 20
        color_divisor = t["dorado_borde"] if destacado else t["texto_secundario"]
        cv.create_line(x_div, 12, x_div, alto_fila - 12, fill=color_divisor)

        # ============== COLUMNA DERECHA: competicion (arriba) + canal (abajo) ==============
        # Mido el ancho real de cada texto ANTES de decidir donde va
        # cada uno -- asi se si de verdad necesita 2 lineas (nombre
        # largo) o le alcanza con 1 (el caso de casi siempre). Antes
        # se reservaba siempre el alto de 2 lineas "por las dudas",
        # aunque el texto entrara comodo en una sola, y eso era
        # exactamente lo que dejaba ese hueco vacio enorme en el medio
        # que se veia desprolijo.
        x_col = x_div + 16
        ancho_col = ancho_fila - x_col - 14

        tamano_logo_liga = 20
        logo_liga = self._obtener_imagen_escudo(p.get("logo_competicion"), tamano=tamano_logo_liga)
        ancho_texto_comp = self._f_competicion.measure(p["competicion"])
        ancho_logo_comp = (tamano_logo_liga + 7) if logo_liga else 0
        ancho_bloque_comp = min(ancho_col, ancho_logo_comp + ancho_texto_comp)

        canal = p.get("canal_tv")
        if canal and canal.get("canal"):
            tamano_logo_canal = 20
            logo_canal = self._obtener_imagen_escudo(canal.get("logo"), tamano=tamano_logo_canal)
            numero = canal.get("numero_telecentro")
            texto_canal = canal["canal"]
            if numero:
                texto_canal = f"{texto_canal} \u00b7 Telecentro {numero}"
            ancho_icono_canal = (tamano_logo_canal + 7) if logo_canal else 22
        else:
            texto_canal = "\U0001F50D Buscar en internet"
            ancho_icono_canal = 0
        ancho_texto_canal = self._f_canal_numero.measure(texto_canal)
        ancho_bloque_canal = min(ancho_col, ancho_icono_canal + ancho_texto_canal)

        linea_h_comp = self._f_competicion.metrics("linespace")
        linea_h_canal = self._f_canal_numero.metrics("linespace")
        lineas_comp = 1 if ancho_bloque_comp <= ancho_col else 2
        lineas_canal = 1 if ancho_bloque_canal <= ancho_col else 2
        gap_central = 6
        alto_bloque = linea_h_comp * lineas_comp + gap_central + linea_h_canal * lineas_canal
        ym_col = alto_fila / 2
        y_arriba = max(10, ym_col - alto_bloque / 2)
        y_abajo = min(alto_fila - 10, ym_col + alto_bloque / 2)

        # --- arriba: logo + nombre de la competicion ---
        # Centrado como bloque (logo+texto juntos) dentro del ancho
        # disponible de la columna, en vez de pegado contra la linea
        # separadora -- antes quedaba todo el texto corto flotando a
        # la izquierda con un hueco enorme a la derecha, se veia
        # desprolijo.
        xc = x_col + max(0, (ancho_col - ancho_bloque_comp) / 2)
        if logo_liga:
            cv.create_image(xc + tamano_logo_liga / 2, y_arriba, image=logo_liga, anchor="n")
            cv._referencias.append(logo_liga)
            xc += tamano_logo_liga + 7
        cv.create_text(xc, y_arriba, text=p["competicion"], font=self._f_competicion,
                        fill=t["texto_secundario"], anchor="nw",
                        width=max(60, x_col + ancho_col - xc), justify="left")

        # --- abajo: canal de TV (o "buscar en internet") ---
        # Mismo criterio de centrado que arriba.
        if canal and canal.get("canal"):
            xt = x_col + max(0, (ancho_col - ancho_bloque_canal) / 2)
            if logo_canal:
                cv.create_image(xt + tamano_logo_canal / 2, y_abajo, image=logo_canal, anchor="s")
                cv._referencias.append(logo_canal)
                xt += tamano_logo_canal + 7
            else:
                cv.create_text(xt, y_abajo, text="\U0001F4FA", font=("Segoe UI Emoji", 12),
                                fill=t["texto_secundario"], anchor="sw")
                xt += 22

            cv.create_text(xt, y_abajo, text=texto_canal, font=self._f_canal_numero,
                            fill=t["texto_primario"], anchor="sw",
                            width=x_col + ancho_col - xt, justify="left")
        else:
            xt = x_col + max(0, (ancho_col - ancho_bloque_canal) / 2)
            id_link = cv.create_text(
                xt, y_abajo, text=texto_canal, font=self._f_canal_numero,
                fill=t["azul_link"], anchor="sw")
            cv.tag_bind(id_link, "<Button-1>", lambda e, p=p: self._buscar_partido_en_internet(p))
            cv.tag_bind(id_link, "<Enter>", lambda e: cv.config(cursor="hand2"))
            cv.tag_bind(id_link, "<Leave>", lambda e: cv.config(cursor=""))

    def _buscar_partido_en_internet(self, p):
        consulta = f"{p['local']} vs {p['visitante']} donde ver por tv"
        url = "https://www.google.com/search?q=" + urllib.parse.quote(consulta)
        try:
            webbrowser.open(url)
        except Exception as e:
            log(f"No se pudo abrir el navegador para buscar el partido: {e}")

    def _chequear_avisos_previos(self):
        if not self.partidos:
            return
        ahora = datetime.now(tz=self.partidos[0]["fecha"].tzinfo)
        minutos_previo = self.config.get("minutos_aviso_previo", 15)
        cambios = False
        for p in self.partidos:
            if p["id"] in self.notificados:
                continue
            delta_minutos = (p["fecha"] - ahora).total_seconds() / 60
            if 0 <= delta_minutos <= minutos_previo:
                if p.get("destacado"):
                    self._avisar_partido(p)
                else:
                    log(f"Partido por arrancar (sin notificacion push): "
                        f"{p['local']} vs {p['visitante']} ({p['competicion']})")
                self.notificados.add(p["id"])
                cambios = True
        if cambios:
            self.config["notificados"] = list(self.notificados)
            api.guardar_config(self.config)

    def _avisar_partido(self, p):
        titulo = f"\u26bd {p['competicion']}"
        mensaje = f"{p['local']} vs {p['visitante']} - arranca pronto"
        log(f"Notificando partido: {mensaje}")
        try:
            notification.notify(title=titulo, message=mensaje, timeout=30)
        except Exception as e:
            log(f"No se pudo notificar partido: {e}")

        # Ademas del aviso de Windows (que se puede pasar facil por
        # alto), se muestra una alerta grande adentro de la propia
        # app. Esto se llama desde el hilo de fondo (_ciclo_de_fondo),
        # asi que hay que pasarlo al hilo principal con root.after --
        # Tkinter no es thread-safe y tocar la UI directo desde otro
        # hilo puede romper la ventana.
        self.root.after(0, self._mostrar_alerta_partido, p)

    def _mostrar_alerta_partido(self, p):
        t = self.tema

        # Si la ventana estaba minimizada en la bandeja, se restaura
        # antes de mostrar la alerta -- si no, puede quedar escondida
        # detras de todo y pasar totalmente desapercibida para mi
        # viejo.
        self.root.deiconify()
        self.root.lift()

        ventana = tk.Toplevel(self.root)
        ventana.title("Partido en vivo")
        ventana.configure(bg=t["ventana_bg"])
        ventana.resizable(False, False)
        ventana.attributes("-topmost", True)
        try:
            ventana.iconbitmap(ICONO_PATH)
        except Exception:
            pass

        ancho, alto = 560, 340
        ventana.update_idletasks()
        x = (ventana.winfo_screenwidth() - ancho) // 2
        y = (ventana.winfo_screenheight() - alto) // 2
        ventana.geometry(f"{ancho}x{alto}+{x}+{y}")

        contenido = tk.Frame(ventana, bg=t["ventana_bg"])
        contenido.pack(fill="both", expand=True, padx=34, pady=30)

        tk.Label(contenido, text="\u26bd", font=("Segoe UI Emoji", 44),
                 bg=t["ventana_bg"], fg=t["dorado"]).pack(pady=(0, 6))
        tk.Label(contenido, text="\u00a1ARRANCA PRONTO!", font=_fuente(22, "bold"),
                 bg=t["ventana_bg"], fg=t["texto_primario"]).pack()
        tk.Label(contenido, text=f"{p['local']} vs {p['visitante']}",
                 font=_fuente(18, "bold"), bg=t["ventana_bg"], fg=t["texto_primario"],
                 wraplength=480, justify="center").pack(pady=(12, 2))
        tk.Label(contenido, text=p["competicion"], font=self._f_competicion,
                 bg=t["ventana_bg"], fg=t["texto_secundario"]).pack()

        boton = tk.Label(contenido, text="VOY A MIRARLA", font=_fuente(16, "bold"),
                          bg=t["verde"], fg="white", padx=24, pady=16, cursor="hand2")
        boton.pack(pady=(26, 0), fill="x")
        boton.bind("<Button-1>", lambda e: ventana.destroy())

        # Se puede cerrar tambien con la X de esta ventana puntual sin
        # que eso cierre el programa entero (es un Toplevel aparte,
        # no la ventana principal).
        ventana.protocol("WM_DELETE_WINDOW", ventana.destroy)

        if winsound:
            try:
                winsound.MessageBeep()
            except Exception:
                pass


def _fijar_icono_barra_tareas():
    """En Windows, evita que la barra de tareas use el icono generico de
    Python y en su lugar respete el icono propio de la app (icono.ico)."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "FutbolYRecordatorios.App.1"
        )
    except Exception:
        pass


def _fijar_dpi_consciente():
    """MUY IMPORTANTE para que la sopa de letras calcule bien cuanto
    entra en pantalla (ver _calcular_dimensiones_sopa): si Windows
    tiene activado el escalado de pantalla (125%, 150%, etc. -- que en
    la gran mayoria de las PCs con monitores modernos viene activado
    de fabrica) y el programa no avisa que sabe manejar esa escala,
    Windows le "miente" a Tkinter sobre el tamano real de la ventana
    en pixeles, y los calculos de cuantas columnas/filas entran quedan
    mal aunque la cuenta este bien hecha -- eso es lo que hacia que el
    tablero de la sopa se cortara. Avisandole a Windows ACA, antes de
    crear la ventana, que el programa ya tiene en cuenta el escalado,
    Tkinter empieza a recibir las medidas reales y correctas."""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main():
    _fijar_dpi_consciente()
    _fijar_icono_barra_tareas()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
