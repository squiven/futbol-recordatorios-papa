"""
app.py
Programa de recordatorios para papa:
 - Avisa proximos partidos de sus competiciones favoritas
   (Liga Argentina, Copa Argentina, Libertadores, Sudamericana, MLS/Messi, Champions).
 - Boton grande para arrancar el temporizador de 2 horas para medirse la
   insulina (se toca cuando lo llaman a comer, en el almuerzo y en la cena).

Para arrancar el programa: doble click en iniciar.bat
"""

import threading
import time
import os
from datetime import datetime

import tkinter as tk
from tkinter import font as tkfont

try:
    import winsound
except ImportError:
    winsound = None

from plyer import notification
import pystray
from PIL import Image, ImageDraw

import api_deportes as api
import actualizador

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "registro.log")


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
    ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icono.ico")
    try:
        return Image.open(ruta)
    except Exception:
        # Respaldo por si falta el archivo icono.ico
        img = Image.new("RGB", (64, 64), "white")
        d = ImageDraw.Draw(img)
        d.ellipse((4, 4, 60, 60), fill=(34, 139, 34))
        return img


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

        self._armar_ventana()
        self._armar_tray()
        self._revisar_timer_guardado()

        # Resolver ligas (solo hace falta la primera vez) y arrancar el
        # ciclo de fondo que actualiza partidos y chequea avisos.
        threading.Thread(target=self._ciclo_de_fondo, daemon=True).start()

    # ---------------- INTERFAZ ----------------
    def _armar_ventana(self):
        self.root.title("Futbol y Recordatorios")
        self.root.geometry("640x660")
        self.root.configure(bg="#f4f4f4")
        self.root.protocol("WM_DELETE_WINDOW", self._minimizar_a_bandeja)

        ruta_icono = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icono.ico")
        try:
            self.root.iconbitmap(ruta_icono)
        except Exception:
            pass

        titulo_font = tkfont.Font(family="Segoe UI", size=22, weight="bold")
        boton_font = tkfont.Font(family="Segoe UI", size=20, weight="bold")
        timer_font = tkfont.Font(family="Segoe UI", size=34, weight="bold")
        lista_font = tkfont.Font(family="Segoe UI", size=13)
        subtitulo_font = tkfont.Font(family="Segoe UI", size=16, weight="bold")

        tk.Label(self.root, text="\u26bd Futbol y Recordatorios", font=titulo_font,
                 bg="#f4f4f4").pack(pady=(20, 10))

        # Boton grande: se toca cuando lo llaman a comer.
        self.boton_comer = tk.Button(
            self.root, text="\U0001F37D  LLAMADO A COMER", font=boton_font,
            bg="#2e8b57", fg="white", activebackground="#256d46",
            height=2, command=self._iniciar_timer
        )
        self.boton_comer.pack(pady=10, padx=30, fill="x")

        self.label_timer = tk.Label(self.root, text="", font=timer_font,
                                     bg="#f4f4f4", fg="#c0392b")
        self.label_timer.pack(pady=(0, 5))

        cancelar_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        self.boton_cancelar = tk.Button(
            self.root, text="\u2716  Cancelar temporizador", font=cancelar_font,
            bg="#f4f4f4", fg="#c0392b", bd=0, activeforeground="#a93226",
            activebackground="#f4f4f4", cursor="hand2", command=self._cancelar_timer
        )
        # Arranca oculto: solo se muestra mientras hay un temporizador activo.

        tk.Label(self.root, text="Partidos de hoy", font=subtitulo_font,
                 bg="#f4f4f4").pack(pady=(10, 5))

        frame_lista = tk.Frame(self.root, bg="white", bd=1, relief="solid")
        frame_lista.pack(padx=20, pady=10, fill="both", expand=True)

        self.lista_partidos = tk.Listbox(frame_lista, font=lista_font,
                                          activestyle="none", bd=0,
                                          highlightthickness=0)
        self.lista_partidos.pack(fill="both", expand=True, padx=8, pady=8)
        self.lista_partidos.insert(tk.END, "Buscando partidos...")

        tk.Label(self.root, text="(si se cierra esta ventana con la X, queda"
                                  " minimizada abajo en la barra de tareas)",
                 font=("Segoe UI", 9), bg="#f4f4f4", fg="#777").pack(pady=(0, 10))

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
            # Las 2 horas se cumplieron mientras la compu estaba apagada
            # o el programa cerrado: avisar apenas arranca.
            log("Se retoma un temporizador que ya se habia cumplido "
                "mientras la compu estaba apagada.")
            self.timer_activo = True
            self._finalizar_timer()
        else:
            log(f"Se retoma un temporizador en marcha, quedan "
                f"{int(restante // 60)} minutos.")
            self.timer_activo = True
            self.timer_restante = int(restante)
            self.boton_comer.config(state="disabled", bg="#888888",
                                     text="\u23f3 Temporizador en marcha...")
            self.boton_cancelar.pack(pady=(0, 15))
            self._tick_timer()

    def _guardar_estado_timer(self, activo, inicio=None):
        self.config["temporizador"] = {"activo": activo, "inicio": inicio}
        api.guardar_config(self.config)

    def _iniciar_timer(self):
        if self.timer_activo:
            return
        self.timer_activo = True
        self.timer_restante = self.duracion_timer_seg
        self.boton_comer.config(state="disabled", bg="#888888",
                                 text="\u23f3 Temporizador en marcha...")
        self.boton_cancelar.pack(pady=(0, 15))
        ahora = datetime.now()
        self._guardar_estado_timer(activo=True, inicio=ahora.isoformat())
        log("Temporizador de 2 horas iniciado (llamado a comer).")
        self._tick_timer()

    def _cancelar_timer(self):
        if not self.timer_activo:
            return
        self.timer_activo = False
        self.timer_restante = None
        self.label_timer.config(text="")
        self.boton_cancelar.pack_forget()
        self.boton_comer.config(state="normal", bg="#2e8b57",
                                 text="\U0001F37D  LLAMADO A COMER")
        self._guardar_estado_timer(activo=False)
        log("Temporizador cancelado manualmente.")

    def _tick_timer(self):
        if self.timer_restante is None:
            return
        if self.timer_restante <= 0:
            self._finalizar_timer()
            return
        horas, resto = divmod(self.timer_restante, 3600)
        minutos, segundos = divmod(resto, 60)
        self.label_timer.config(
            text=f"\u23f1 {horas:d}:{minutos:02d}:{segundos:02d} restantes"
        )
        self.timer_restante -= 1
        self.root.after(1000, self._tick_timer)

    def _finalizar_timer(self):
        self.timer_activo = False
        self.label_timer.config(text="")
        self.boton_cancelar.pack_forget()
        self.boton_comer.config(state="normal", bg="#2e8b57",
                                 text="\U0001F37D  LLAMADO A COMER")
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
        ventana = tk.Toplevel(self.root)
        ventana.title("Recordatorio")
        ventana.geometry("460x280")
        ventana.configure(bg="#c0392b")
        ventana.attributes("-topmost", True)
        ruta_icono = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icono.ico")
        try:
            ventana.iconbitmap(ruta_icono)
        except Exception:
            pass
        tk.Label(ventana, text="\u23f0 \u00a1ES HORA DE\nMEDIRSE!",
                 font=("Segoe UI", 24, "bold"), bg="#c0392b", fg="white",
                 justify="center").pack(expand=True, pady=(25, 15))
        tk.Button(ventana, text="\u2705  Ya me med\u00ed, cerrar",
                  font=("Segoe UI", 18, "bold"), command=ventana.destroy,
                  bg="white", fg="#c0392b", height=2).pack(pady=(0, 20), padx=30, fill="x")
        ventana.lift()
        ventana.focus_force()

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

    def _refrescar_lista_ui(self):
        self.lista_partidos.delete(0, tk.END)
        if not self.partidos:
            self.lista_partidos.insert(tk.END, "No hay partidos programados para hoy.")
            return
        for p in self.partidos[:15]:
            fecha_txt = p["fecha"].strftime("%d/%m %H:%M")
            texto = f"{fecha_txt}   {p['local']} vs {p['visitante']}   ({p['competicion']})"
            self.lista_partidos.insert(tk.END, texto)

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
                self._avisar_partido(p)
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
