# -*- coding: utf-8 -*-
"""
panel_timer.py
Componente reusable del temporizador de "llamado a comer" de Futbol y
Recordatorios.

Se separo de app.py en la Etapa 2 del rediseno de interfaz para que se
pueda dibujar en mas de un lugar (Futbol, y mas adelante Sopa y
Solitario) sin duplicar la logica de arrancar / cancelar / contar /
guardar en config.json. El ESTADO del temporizador es unico: sin
importar en cuantos lugares distintos se dibuje, hay una sola
instancia de PanelTimer y un solo timer_activo/timer_restante -- nunca
tres temporizadores corriendo por separado.

Extraccion PURAMENTE ESTRUCTURAL: la logica de aca abajo es exactamente
la misma que tenia app.py antes de este cambio (mismos calculos, mismo
guardado en config.json, misma recuperacion al reabrir el programa),
solo que reorganizada en su propia clase para que se pueda "montar" en
distintos contenedores.
"""

import os
from datetime import datetime

import tkinter as tk
from tkinter import font as tkfont

try:
    import winsound
except ImportError:
    winsound = None

from plyer import notification

import api_deportes as api

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "registro.log")


def log(mensaje):
    """Mismo logger que usa app.py (misma ruta de archivo,
    registro.log), duplicado aca para que este archivo no dependa de
    importar nada de vuelta de app.py (evita import circular)."""
    linea = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {mensaje}"
    print(linea)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except Exception:
        pass


def _redondear(canvas, x1, y1, x2, y2, r, **kw):
    """Dibuja un rectangulo con esquinas redondeadas en un Canvas y
    devuelve su id. Tkinter no tiene esto de fabrica: se arma con un
    poligono suavizado (smooth=True actua como spline en las esquinas).
    (Se movio aca desde app.py junto con el timer porque el panel la
    necesita: app.py la vuelve a importar de aca para las demas partes
    de la interfaz que tambien la usan, como las filas de partido.)"""
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


class PanelTimer:
    """
    app: la instancia de App (app.py). Se usa para:
      - leer/escribir config.json (self.app.config)
      - tomar el tema y las fuentes ACTUALES (self.app.tema,
        self.app._f_boton, etc) -- estas pueden cambiar en cualquier
        momento si se alterna claro/oscuro, asi que siempre se leen
        frescas en el momento de dibujar, nunca se copian una vez.
      - programar el "tick" de cada segundo con self.app.root.after
      - mostrar la ventana principal y el popup de "hora de medirse"
        cuando el timer se cumple (eso se quedo en App, ver _finalizar)
    """

    def __init__(self, app):
        self.app = app
        self.config = app.config

        self.duracion_timer_seg = self.config.get("duracion_timer_minutos", 120) * 60
        self.timer_activo = False
        self.timer_restante = None

        self.modo = "grande"
        self.canvas = None

        # IDs de los items del Canvas en modo "grande" (Futbol) --
        # identico al panel original de app.py.
        self._id_boton_comer_rect = None
        self._id_boton_comer_texto = None
        self._id_boton_comer_sub = None
        self._id_boton_parar_rect = None
        self._id_boton_parar_icono = None
        self._id_boton_parar_texto = None
        self._id_boton_parar_sub = None
        self._id_timer_valor = None
        self._id_timer_caption = None
        self._id_progress_fill = None
        self._barra_coords = None

        # IDs del modo "compacto" (para Sopa/Solitario en las
        # proximas etapas -- todavia no lo usa ninguna vista real,
        # queda preparado). Es un solo boton que alterna
        # arrancar/parar en vez de dos separados: no hay lugar para
        # dos botones de 210px en un panel angosto arriba a la
        # izquierda.
        self._id_compacto_rect = None
        self._id_compacto_boton_rect = None
        self._id_compacto_boton_texto = None
        self._id_compacto_valor = None

    # ---------------- DIBUJO ----------------
    def armar(self, parent, ancho, alto=190, modo="grande"):
        """Crea el Canvas del temporizador dentro de parent. Se llama
        de nuevo cada vez que cambia la vista activa o el tema (el
        Canvas anterior ya fue destruido junto con el resto de esa
        vista) -- el ESTADO (timer_activo/timer_restante) no se toca
        para nada aca, solo se vuelve a dibujar con los valores
        actuales."""
        self.modo = modo
        cv = tk.Canvas(parent, width=ancho, height=alto,
                       bg=self.app.tema["ventana_bg"], highlightthickness=0)
        self.canvas = cv

        if modo == "compacto":
            cv.pack(anchor="nw")
            self._armar_compacto(cv, ancho, alto)
        else:
            cv.pack(padx=20, pady=(24, 16))
            self._armar_grande(cv, ancho, alto)

        if self.timer_activo:
            self._pintar_activo()
        else:
            self._pintar_inactivo()

        return cv

    def _armar_grande(self, cv, W, H):
        t = self.app.tema
        f = self.app  # de aca salen las fuentes (_f_boton, etc)
        _redondear(cv, 0, 0, W, H, 22, fill=t["panel_bg"], outline=t["panel_borde"])

        # --- columna izquierda: LLAMADO A COMER ---
        cx1, cy1, cx2, cy2 = 18, 20, 228, H - 20
        self._id_boton_comer_rect = _redondear(cv, cx1, cy1, cx2, cy2, 16,
                                                fill=t["verde"], outline="")
        cxm = (cx1 + cx2) / 2
        cv.create_text(cxm, cy1 + 34, text="\U0001F37D", font=("Segoe UI Emoji", 20),
                        fill="white")
        self._id_boton_comer_texto = cv.create_text(
            cxm, cy1 + 68, text="LLAMADO A\nCOMER", font=f._f_boton,
            fill="white", justify="center")
        self._id_boton_comer_sub = cv.create_text(
            cxm, cy2 - 18, text="Iniciar contador de 2 horas",
            font=f._f_boton_sub, fill="white", justify="center")

        tag_comer = "boton_comer"
        for iid in (self._id_boton_comer_rect, self._id_boton_comer_texto, self._id_boton_comer_sub):
            cv.addtag_withtag(tag_comer, iid)
        cv.tag_bind(tag_comer, "<Button-1>", lambda e: self.iniciar())
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
            pxm, py1 + 68, text="PARAR TIEMPO", font=f._f_boton, fill="white",
            justify="center")
        self._id_boton_parar_sub = cv.create_text(
            pxm, py2 - 18, text="Detener el contador", font=f._f_boton_sub,
            fill="white", justify="center")

        tag_parar = "boton_parar"
        for iid in (self._id_boton_parar_rect, self._id_boton_parar_icono,
                    self._id_boton_parar_texto, self._id_boton_parar_sub):
            cv.addtag_withtag(tag_parar, iid)
        cv.tag_bind(tag_parar, "<Button-1>", lambda e: self._confirmar_y_cancelar())

        # --- columna central: reloj ---
        centro_x = W / 2
        cv.create_text(centro_x, 40, text="TIEMPO RESTANTE", font=f._f_timer_label,
                        fill=t["verde"])
        self._id_timer_valor = cv.create_text(
            centro_x, 78, text="00:00:00", font=f._f_timer_valor,
            fill=t["texto_secundario"])
        self._id_timer_caption = cv.create_text(
            centro_x, 108, text="HORAS  |  MINUTOS  |  SEGUNDOS",
            font=f._f_timer_caption, fill=t["texto_secundario"])

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

    def _armar_compacto(self, cv, W, H):
        """Version chica para cuando el timer tenga que convivir con
        Sopa/Solitario, arriba a la izquierda. Todo centrado
        horizontalmente dentro del box (antes el texto de arriba
        quedaba pegado al borde izquierdo mientras el boton de abajo
        si estaba centrado, y se veia desparejo)."""
        t = self.app.tema
        _redondear(cv, 0, 0, W, H, 16, fill=t["panel_bg"], outline=t["panel_borde"])

        cv.create_text(W / 2, 20, text="TIEMPO RESTANTE", font=self.app._f_timer_label,
                        fill=t["verde"])
        self._id_compacto_valor = cv.create_text(
            W / 2, 48, text="00:00:00", font=tkfont.Font(family="Segoe UI", size=20, weight="bold"),
            fill=t["texto_secundario"])

        bx1, by1, bx2, by2 = 16, H - 40, W - 16, H - 12
        self._id_compacto_boton_rect = _redondear(cv, bx1, by1, bx2, by2, 12,
                                                    fill=t["verde"], outline="")
        self._id_compacto_boton_texto = cv.create_text(
            (bx1 + bx2) / 2, (by1 + by2) / 2, text="LLAMADO A COMER",
            font=self.app._f_boton_sub, fill="white")

        tag = "boton_compacto"
        cv.addtag_withtag(tag, self._id_compacto_boton_rect)
        cv.addtag_withtag(tag, self._id_compacto_boton_texto)
        cv.tag_bind(tag, "<Button-1>", lambda e: self._alternar())
        cv.tag_bind(tag, "<Enter>", lambda e: cv.config(cursor="hand2"))
        cv.tag_bind(tag, "<Leave>", lambda e: cv.config(cursor=""))

    def _alternar(self):
        """Solo la usa el modo compacto (un unico boton para arrancar
        y parar, en vez de los dos botones separados del modo
        grande)."""
        if self.timer_activo:
            self._confirmar_y_cancelar()
        else:
            self.iniciar()

    # ---------------- ESTADO / PERSISTENCIA ----------------
    def revisar_guardado(self):
        """Se llama una sola vez al arrancar el programa. Si habia un
        temporizador en marcha antes de apagar la computadora, lo
        retoma calculando cuanto tiempo REAL paso (no cuanto estuvo
        prendido el programa) -- logica identica a la que tenia
        app.py antes de esta extraccion."""
        temp = self.config.get("temporizador", {})
        if not temp.get("activo") or not temp.get("inicio"):
            return

        try:
            inicio = datetime.fromisoformat(temp["inicio"])
        except Exception:
            self._guardar_estado(activo=False)
            return

        transcurrido = (datetime.now() - inicio).total_seconds()
        restante = self.duracion_timer_seg - transcurrido

        if restante <= 0:
            log("Se retoma un temporizador que ya se habia cumplido "
                "mientras la compu estaba apagada.")
            self.timer_activo = True
            self._finalizar()
        else:
            log(f"Se retoma un temporizador en marcha, quedan "
                f"{int(restante // 60)} minutos.")
            self.timer_activo = True
            self.timer_restante = int(restante)
            self._pintar_activo()
            self._tick()

    def _guardar_estado(self, activo, inicio=None):
        self.config["temporizador"] = {"activo": activo, "inicio": inicio}
        api.guardar_config(self.config)

    # ---------------- PINTADO ----------------
    def _pintar_activo(self):
        if not self.canvas or not self.canvas.winfo_exists():
            return
        t = self.app.tema
        cv = self.canvas
        if self.modo == "compacto":
            cv.itemconfig(self._id_compacto_boton_rect, fill=t["rojo"])
            cv.itemconfig(self._id_compacto_boton_texto, text="PARAR TIEMPO")
        else:
            cv.itemconfig(self._id_boton_comer_rect, fill=t["gris_deshabilitado"])
            cv.itemconfig(self._id_boton_comer_texto, text="TEMPORIZADOR\nEN MARCHA")
            cv.itemconfig(self._id_boton_parar_rect, fill=t["rojo"])

    def _pintar_inactivo(self):
        if not self.canvas or not self.canvas.winfo_exists():
            return
        t = self.app.tema
        cv = self.canvas
        if self.modo == "compacto":
            cv.itemconfig(self._id_compacto_boton_rect, fill=t["verde"])
            cv.itemconfig(self._id_compacto_boton_texto, text="LLAMADO A COMER")
            cv.itemconfig(self._id_compacto_valor, text="00:00:00", fill=t["texto_secundario"])
        else:
            cv.itemconfig(self._id_boton_comer_rect, fill=t["verde"])
            cv.itemconfig(self._id_boton_comer_texto, text="LLAMADO A\nCOMER")
            cv.itemconfig(self._id_boton_parar_rect, fill=t["gris_deshabilitado"])
            cv.itemconfig(self._id_timer_valor, text="00:00:00", fill=t["texto_secundario"])
            x1, y1, x2, y2 = self._barra_coords
            cv.coords(self._id_progress_fill, *_puntos_redondeado(x1, y1, x1 + 1, y2, 3))

    # ---------------- ACCIONES ----------------
    def iniciar(self):
        if self.timer_activo:
            return
        self.timer_activo = True
        self.timer_restante = self.duracion_timer_seg
        self._pintar_activo()
        ahora = datetime.now()
        self._guardar_estado(activo=True, inicio=ahora.isoformat())
        log("Temporizador de 2 horas iniciado (llamado a comer).")
        self._tick()

    def _confirmar_y_cancelar(self):
        """Antes de cancelar de una, pide confirmacion -- un misclick
        en cualquiera de los dos botones (el grande PARAR TIEMPO o el
        compacto haciendo de alternar) tiraba abajo sin avisar las 2
        horas ya contadas. El popup en si vive en App (self.app), no
        aca, para reusar el mismo estilo que los demas avisos
        (_popup_aviso, _mostrar_alerta_partido) -- ver
        App._confirmar_cancelar_timer.

        Se dispara con root.after(0, ...) en vez de llamarlo directo:
        este metodo corre DENTRO del propio evento de click del
        Canvas (el tag_bind de "boton_parar"), y crear+dibujar un
        Toplevel con Canvas nuevo (con texto) en esa misma pasada del
        evento a veces no terminaba de pintarse en Windows -- quedaban
        los botones del popup sin texto hasta que algo forzaba un
        redibujado. Mismo motivo por el que _avisar_partido (app.py)
        ya usaba root.after(0, ...) para mostrar SU alerta en vez de
        llamarla directo desde el hilo de fondo."""
        if not self.timer_activo:
            return
        self.app.root.after(0, self.app._confirmar_cancelar_timer, self.cancelar)

    def cancelar(self):
        if not self.timer_activo:
            return
        self.timer_activo = False
        self.timer_restante = None
        self._pintar_inactivo()
        self._guardar_estado(activo=False)
        log("Temporizador cancelado manualmente.")

    def _tick(self):
        if self.timer_restante is None:
            return
        if self.timer_restante <= 0:
            self._finalizar()
            return

        t = self.app.tema
        horas, resto = divmod(self.timer_restante, 3600)
        minutos, segundos = divmod(resto, 60)
        texto = f"{horas:d}:{minutos:02d}:{segundos:02d}"

        if self.canvas and self.canvas.winfo_exists():
            cv = self.canvas
            if self.modo == "compacto":
                cv.itemconfig(self._id_compacto_valor, text=texto, fill=t["verde"])
            else:
                cv.itemconfig(self._id_timer_valor, text=texto, fill=t["verde"])
                avance = 1 - (self.timer_restante / self.duracion_timer_seg)
                x1, y1, x2, y2 = self._barra_coords
                x_fill = x1 + max(2, (x2 - x1) * avance)
                cv.coords(self._id_progress_fill, *_puntos_redondeado(x1, y1, x_fill, y2, 3))

        self.timer_restante -= 1
        self.app.root.after(1000, self._tick)

    def _finalizar(self):
        self.timer_activo = False
        self._pintar_inactivo()
        self._guardar_estado(activo=False)
        log("Temporizador cumplido: hay que medirse.")

        try:
            notification.notify(title="Es hora de medirse",
                                 message="Pasaron las 2 horas de la comida.",
                                 timeout=30)
        except Exception as e:
            log(f"No se pudo mandar notificacion: {e}")
        self.app._notificar_ntfy("Es hora de medirse",
                                  "Pasaron las 2 horas de la comida.")

        if winsound:
            try:
                winsound.MessageBeep()
            except Exception:
                pass

        # El popup grande de "ES HORA DE MEDIRSE" y el traer la
        # ventana al frente se quedaron en App (app.py) -- no son
        # parte del panel en si, son una accion puntual que dispara el
        # timer al cumplirse, igual que la alerta de partido de Boca.
        self.app._mostrar_ventana()
        self.app._popup_aviso()
