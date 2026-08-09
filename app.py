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

import io
import os
import threading
import time
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

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "registro.log")
ICONO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icono.ico")

ANCHO_VENTANA = 760
ALTO_VENTANA = 760


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
    },
}


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


def _redondear(canvas, x1, y1, x2, y2, r, **kw):
    """Dibuja un rectangulo con esquinas redondeadas en un Canvas y
    devuelve su id. Tkinter no tiene esto de fabrica: se arma con un
    poligono suavizado (smooth=True actua como spline en las esquinas)."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    puntos = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(puntos, smooth=True, **kw)


def _puntos_redondeado(x1, y1, x2, y2, r):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]


class App:
    def __init__(self, root):
        self.root = root
        self.config = api.cargar_config()
        self.duracion_timer_seg = self.config.get("duracion_timer_minutos", 120) * 60

        self.partidos = []
        self.notificados = set(self.config.get("notificados", []))
        self.timer_restante = None
        self.timer_activo = False
        self.tray_icon = None

        self.tema = TEMAS["oscuro"] if _tema_windows_es_oscuro() else TEMAS["claro"]
        self._escudo_cache = {}  # (url, tamano) -> PhotoImage | "cargando" | None

        self._armar_ventana()
        self._armar_tray()
        self._revisar_timer_guardado()

        threading.Thread(target=self._ciclo_de_fondo, daemon=True).start()

    # ---------------- INTERFAZ ----------------
    def _armar_ventana(self):
        t = self.tema
        self.root.title("Futbol y Recordatorios")
        self.root.geometry(f"{ANCHO_VENTANA}x{ALTO_VENTANA}")
        self.root.resizable(False, False)
        self.root.configure(bg=t["ventana_bg"])
        self.root.protocol("WM_DELETE_WINDOW", self._minimizar_a_bandeja)

        try:
            self.root.iconbitmap(ICONO_PATH)
        except Exception:
            pass

        self._f_titulo = _fuente(24, "bold")
        self._f_subtitulo_seccion = _fuente(15, "bold")
        self._f_boton = _fuente(14, "bold")
        self._f_boton_sub = tkfont.Font(family="Segoe UI", size=9)
        self._f_timer_label = _fuente(11, "bold")
        self._f_timer_valor = _fuente(30, "bold", condensada=False)
        self._f_timer_caption = tkfont.Font(family="Segoe UI", size=8)
        self._f_hora = _fuente(13, "bold")
        self._f_fecha = tkfont.Font(family="Segoe UI", size=8)
        self._f_equipo = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        self._f_vs = tkfont.Font(family="Segoe UI", size=9)
        self._f_competicion = tkfont.Font(family="Segoe UI", size=8)
        self._f_footer = tkfont.Font(family="Segoe UI", size=9)

        self._armar_header()
        self._armar_panel_timer()
        self._armar_seccion_partidos()
        self._armar_footer()

    def _armar_header(self):
        t = self.tema
        frame = tk.Frame(self.root, bg=t["ventana_bg"])
        frame.pack(pady=(22, 14))
        tk.Frame(frame, bg=t["verde"], width=64, height=3).pack(side="left", padx=(0, 14))
        tk.Label(frame, text="\u26bd", font=("Segoe UI Emoji", 22), bg=t["ventana_bg"],
                 fg=t["texto_primario"]).pack(side="left", padx=(0, 8))
        tk.Label(frame, text="FUTBOL Y RECORDATORIOS", font=self._f_titulo,
                 bg=t["ventana_bg"], fg=t["texto_primario"]).pack(side="left")
        tk.Frame(frame, bg=t["verde"], width=64, height=3).pack(side="left", padx=(14, 0))

    def _armar_panel_timer(self):
        t = self.tema
        W = ANCHO_VENTANA - 40
        H = 190
        cv = tk.Canvas(self.root, width=W, height=H, bg=t["ventana_bg"],
                       highlightthickness=0)
        cv.pack(padx=20, pady=(0, 16))
        self.canvas_panel = cv

        _redondear(cv, 0, 0, W, H, 22, fill=t["panel_bg"], outline=t["panel_borde"])

        # --- columna izquierda: LLAMADO A COMER ---
        cx1, cy1, cx2, cy2 = 18, 20, 228, H - 20
        self._id_boton_comer_rect = _redondear(cv, cx1, cy1, cx2, cy2, 16,
                                                fill=t["verde"], outline="")
        cxm = (cx1 + cx2) / 2
        cv.create_text(cxm, cy1 + 34, text="\U0001F37D", font=("Segoe UI Emoji", 20),
                        fill="white")
        self._id_boton_comer_texto = cv.create_text(
            cxm, cy1 + 68, text="LLAMADO A\nCOMER", font=self._f_boton,
            fill="white", justify="center")
        self._id_boton_comer_sub = cv.create_text(
            cxm, cy2 - 18, text="Iniciar contador de 2 horas",
            font=self._f_boton_sub, fill="white", justify="center")

        tag_comer = "boton_comer"
        for iid in (self._id_boton_comer_rect, self._id_boton_comer_texto, self._id_boton_comer_sub):
            cv.addtag_withtag(tag_comer, iid)
        cv.tag_bind(tag_comer, "<Button-1>", lambda e: self._iniciar_timer())
        cv.tag_bind(tag_comer, "<Enter>", lambda e: cv.config(cursor="hand2"))
        cv.tag_bind(tag_comer, "<Leave>", lambda e: cv.config(cursor=""))

        # --- columna derecha: PARAR TIEMPO ---
        px1, py1, px2, py2 = W - 228, 20, W - 18, H - 20
        self._id_boton_parar_rect = _redondear(cv, px1, py1, px2, py2, 16,
                                                fill=t["gris_deshabilitado"], outline="")
        pxm = (px1 + px2) / 2
        self._id_boton_parar_icono = cv.create_text(
            pxm, py1 + 34, text="\u23f9", font=("Segoe UI Emoji", 18), fill="white")
        self._id_boton_parar_texto = cv.create_text(
            pxm, py1 + 68, text="PARAR TIEMPO", font=self._f_boton, fill="white",
            justify="center")
        self._id_boton_parar_sub = cv.create_text(
            pxm, py2 - 18, text="Detener el contador", font=self._f_boton_sub,
            fill="white", justify="center")

        tag_parar = "boton_parar"
        for iid in (self._id_boton_parar_rect, self._id_boton_parar_icono,
                    self._id_boton_parar_texto, self._id_boton_parar_sub):
            cv.addtag_withtag(tag_parar, iid)
        cv.tag_bind(tag_parar, "<Button-1>", lambda e: self._cancelar_timer())

        # --- columna central: reloj ---
        centro_x = W / 2
        cv.create_text(centro_x, 40, text="TIEMPO RESTANTE", font=self._f_timer_label,
                        fill=t["verde"])
        self._id_timer_valor = cv.create_text(
            centro_x, 78, text="00:00:00", font=self._f_timer_valor,
            fill=t["texto_secundario"])
        self._id_timer_caption = cv.create_text(
            centro_x, 108, text="HORAS  |  MINUTOS  |  SEGUNDOS",
            font=self._f_timer_caption, fill=t["texto_secundario"])

        barra_x1, barra_x2 = centro_x - 130, centro_x + 130
        barra_y1, barra_y2 = 128, 134
        _redondear(cv, barra_x1, barra_y1, barra_x2, barra_y2, 3,
                   fill=t["trough"], outline="")
        self._barra_coords = (barra_x1, barra_y1, barra_x2, barra_y2)
        self._id_progress_fill = _redondear(cv, barra_x1, barra_y1, barra_x1 + 1,
                                             barra_y2, 3, fill=t["verde"], outline="")

        # Linea divisoria entre columnas.
        cv.create_line(cx2 + 10, 30, cx2 + 10, H - 30, fill=t["panel_borde"])
        cv.create_line(px1 - 10, 30, px1 - 10, H - 30, fill=t["panel_borde"])

        # Restaurar visualmente el estado si veniamos de un rebuild (cambio de tema).
        if self.timer_activo:
            self._pintar_timer_activo()
        else:
            self._pintar_timer_inactivo()

    def _estilo_scrollbar(self):
        """
        La Scrollbar de Tkinter de fabrica es la clasica gris con
        flechitas de los 90 y no respeta el tema. Con ttk + el theme
        'clam' (el unico que permite recolorear todo a mano) se arma
        una mas fina, sin flechas, en los colores del tema actual.
        """
        t = self.tema
        nombre = "Delgada.Vertical.TScrollbar"
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

    def _armar_seccion_partidos(self):
        t = self.tema
        frame_tit = tk.Frame(self.root, bg=t["ventana_bg"])
        frame_tit.pack(padx=20, anchor="w")
        tk.Label(frame_tit, text="\U0001F4C5", font=("Segoe UI Emoji", 13),
                 bg=t["ventana_bg"], fg=t["texto_primario"]).pack(side="left", padx=(0, 8))
        tk.Label(frame_tit, text="PARTIDOS DE HOY", font=self._f_subtitulo_seccion,
                 bg=t["ventana_bg"], fg=t["texto_primario"]).pack(side="left")

        contenedor = tk.Frame(self.root, bg=t["card_borde"], bd=0)
        contenedor.pack(padx=20, pady=(8, 10), fill="both", expand=True)
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

        self._mostrar_texto_lista("Buscando partidos...")

    def _armar_footer(self):
        t = self.tema
        tk.Label(self.root, text="(si se cierra esta ventana con la X, queda"
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
        nuevo = TEMAS["oscuro"] if _tema_windows_es_oscuro() else TEMAS["claro"]
        if nuevo is not self.tema:
            self.tema = nuevo
            log("Cambio de tema de Windows detectado, redibujando la interfaz.")
            self._reconstruir_ui()

    def _reconstruir_ui(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        self._armar_ventana()
        self._refrescar_lista_ui()

    # ---------------- TEMPORIZADOR DE INSULINA ----------------
    def _revisar_timer_guardado(self):
        """
        Se llama al arrancar el programa. Si habia un temporizador en
        marcha antes de apagar la computadora, lo retoma calculando
        cuanto tiempo REAL paso (no cuanto estuvo prendido el programa).
        """
        temp = self.config.get("temporizador", {})
        if not temp.get("activo") or not temp.get("inicio"):
            return

        try:
            inicio = datetime.fromisoformat(temp["inicio"])
        except Exception:
            self._guardar_estado_timer(activo=False)
            return

        transcurrido = (datetime.now() - inicio).total_seconds()
        restante = self.duracion_timer_seg - transcurrido

        if restante <= 0:
            log("Se retoma un temporizador que ya se habia cumplido "
                "mientras la compu estaba apagada.")
            self.timer_activo = True
            self._finalizar_timer()
        else:
            log(f"Se retoma un temporizador en marcha, quedan "
                f"{int(restante // 60)} minutos.")
            self.timer_activo = True
            self.timer_restante = int(restante)
            self._pintar_timer_activo()
            self._tick_timer()

    def _guardar_estado_timer(self, activo, inicio=None):
        self.config["temporizador"] = {"activo": activo, "inicio": inicio}
        api.guardar_config(self.config)

    def _pintar_timer_activo(self):
        t = self.tema
        cv = self.canvas_panel
        cv.itemconfig(self._id_boton_comer_rect, fill=t["gris_deshabilitado"])
        cv.itemconfig(self._id_boton_comer_texto, text="TEMPORIZADOR\nEN MARCHA")
        cv.itemconfig(self._id_boton_parar_rect, fill=t["rojo"])

    def _pintar_timer_inactivo(self):
        t = self.tema
        cv = self.canvas_panel
        cv.itemconfig(self._id_boton_comer_rect, fill=t["verde"])
        cv.itemconfig(self._id_boton_comer_texto, text="LLAMADO A\nCOMER")
        cv.itemconfig(self._id_boton_parar_rect, fill=t["gris_deshabilitado"])
        cv.itemconfig(self._id_timer_valor, text="00:00:00", fill=t["texto_secundario"])
        x1, y1, x2, y2 = self._barra_coords
        cv.coords(self._id_progress_fill, *_puntos_redondeado(x1, y1, x1 + 1, y2, 3))

    def _iniciar_timer(self):
        if self.timer_activo:
            return
        self.timer_activo = True
        self.timer_restante = self.duracion_timer_seg
        self._pintar_timer_activo()
        ahora = datetime.now()
        self._guardar_estado_timer(activo=True, inicio=ahora.isoformat())
        log("Temporizador de 2 horas iniciado (llamado a comer).")
        self._tick_timer()

    def _cancelar_timer(self):
        if not self.timer_activo:
            return
        self.timer_activo = False
        self.timer_restante = None
        self._pintar_timer_inactivo()
        self._guardar_estado_timer(activo=False)
        log("Temporizador cancelado manualmente.")

    def _tick_timer(self):
        if self.timer_restante is None:
            return
        if self.timer_restante <= 0:
            self._finalizar_timer()
            return

        t = self.tema
        horas, resto = divmod(self.timer_restante, 3600)
        minutos, segundos = divmod(resto, 60)
        cv = self.canvas_panel
        cv.itemconfig(self._id_timer_valor, text=f"{horas:d}:{minutos:02d}:{segundos:02d}",
                      fill=t["verde"])

        avance = 1 - (self.timer_restante / self.duracion_timer_seg)
        x1, y1, x2, y2 = self._barra_coords
        x_fill = x1 + max(2, (x2 - x1) * avance)
        cv.coords(self._id_progress_fill, *_puntos_redondeado(x1, y1, x_fill, y2, 3))

        self.timer_restante -= 1
        self.root.after(1000, self._tick_timer)

    def _finalizar_timer(self):
        self.timer_activo = False
        self._pintar_timer_inactivo()
        self._guardar_estado_timer(activo=False)
        log("Temporizador cumplido: hay que medirse.")

        try:
            notification.notify(title="Es hora de medirse",
                                 message="Pasaron las 2 horas de la comida.",
                                 timeout=30)
        except Exception as e:
            log(f"No se pudo mandar notificacion: {e}")

        if winsound:
            try:
                winsound.MessageBeep()
            except Exception:
                pass

        self._mostrar_ventana()
        self._popup_aviso()

    def _popup_aviso(self):
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
    def _obtener_imagen_escudo(self, url, tamano=34):
        if not url:
            return None
        clave = (url, tamano)
        actual = self._escudo_cache.get(clave)
        if actual == "cargando":
            return None
        if actual is not None:
            return actual
        self._escudo_cache[clave] = "cargando"
        threading.Thread(target=self._descargar_escudo, args=(url, tamano),
                          daemon=True).start()
        return None

    def _descargar_escudo(self, url, tamano):
        try:
            r = requests.get(url, timeout=8)
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content)).convert("RGBA")
            img.thumbnail((tamano, tamano), Image.LANCZOS)
            lienzo = Image.new("RGBA", (tamano, tamano), (0, 0, 0, 0))
            lienzo.paste(img, ((tamano - img.width) // 2, (tamano - img.height) // 2), img)
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

    def _mostrar_texto_lista(self, texto):
        t = self.tema
        for widget in self.frame_lista.winfo_children():
            widget.destroy()
        tk.Label(self.frame_lista, text=texto, font=self._f_equipo, bg=t["card_bg"],
                 fg=t["texto_secundario"]).pack(pady=30)

    def _refrescar_lista_ui(self):
        if not self.partidos:
            self._mostrar_texto_lista("No hay partidos programados para hoy.")
            return

        for widget in self.frame_lista.winfo_children():
            widget.destroy()

        for p in self.partidos[:15]:
            self._crear_fila_partido(p)

    def _crear_fila_partido(self, p):
        t = self.tema
        ancho_fila = ANCHO_VENTANA - 40 - 18 - 20
        alto_fila = 74

        cv = tk.Canvas(self.frame_lista, width=ancho_fila, height=alto_fila,
                       bg=t["card_bg"], highlightthickness=0)
        cv.pack(fill="x", padx=8, pady=4)

        destacado = bool(p.get("destacado"))
        fondo = t["dorado_bg"] if destacado else t["card_bg"]
        borde = t["dorado_borde"] if destacado else t["card_borde"]
        _redondear(cv, 1, 1, ancho_fila - 1, alto_fila - 1, 14, fill=fondo, outline=borde)

        # --- badge de hora ---
        bx1, by1, bx2, by2 = 10, 10, 92, alto_fila - 10
        badge_bg = t["dorado_bg"] if destacado else t["badge_hora_bg"]
        badge_fg = t["dorado"] if destacado else t["badge_hora_texto"]
        _redondear(cv, bx1, by1, bx2, by2, 10, fill=badge_bg, outline="")
        bxm = (bx1 + bx2) / 2
        prefijo = "\u2b50 " if destacado else ""
        cv.create_text(bxm, by1 + 16, text=f"{prefijo}{p['fecha'].strftime('%H:%M')}",
                        font=self._f_hora, fill=badge_fg)
        cv.create_text(bxm, by1 + 34, text=p["fecha"].strftime("%d/%m"),
                        font=self._f_fecha, fill=badge_fg)

        x = 104

        # --- escudo local ---
        img_local = self._obtener_imagen_escudo(p.get("escudo_local"))
        ym = alto_fila / 2
        if img_local:
            cv.create_image(x + 17, ym, image=img_local)
            cv._referencias = getattr(cv, "_referencias", [])
            cv._referencias.append(img_local)
        else:
            cv.create_text(x + 17, ym, text="\u26bd", font=("Segoe UI Emoji", 14),
                            fill=t["texto_secundario"])
        x += 40

        # --- nombre local ---
        cv.create_text(x, ym, text=p["local"], font=self._f_equipo,
                        fill=t["texto_primario"], anchor="w", width=170)
        x += 178

        cv.create_text(x, ym, text="vs", font=self._f_vs, fill=t["texto_secundario"])
        x += 26

        # --- nombre visitante ---
        cv.create_text(x, ym, text=p["visitante"], font=self._f_equipo,
                        fill=t["texto_primario"], anchor="w", width=170)
        x += 178

        # --- escudo visitante ---
        img_visitante = self._obtener_imagen_escudo(p.get("escudo_visitante"))
        if img_visitante:
            cv.create_image(x + 17, ym, image=img_visitante)
            cv._referencias.append(img_visitante)
        else:
            cv.create_text(x + 17, ym, text="\u26bd", font=("Segoe UI Emoji", 14),
                            fill=t["texto_secundario"])
        x += 44

        # --- competicion ---
        cv.create_text(x, ym, text=p["competicion"], font=self._f_competicion,
                        fill=t["texto_secundario"], anchor="w",
                        width=max(60, ancho_fila - x - 10), justify="left")

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


def main():
    _fijar_icono_barra_tareas()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
