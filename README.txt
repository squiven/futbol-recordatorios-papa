FUTBOL Y RECORDATORIOS
=======================

Que hace este programa
-----------------------
1) Avisa (con una notificacion de Windows) cuando esta por arrancar un
   partido de: Liga Profesional Argentina, Copa Argentina, Copa
   Libertadores, Copa Sudamericana, MLS (para los partidos de Messi con
   el Inter Miami) y la Champions League.

2) Tiene un boton grande "LLAMADO A COMER". Se toca cuando se lo llama a
   comer (almuerzo o cena) y arranca una cuenta regresiva de 2 horas.
   Cuando se cumple, aparece un aviso grande en pantalla + notificacion +
   sonido, para recordar que hay que medirse.

3) El programa se puede minimizar a la bandeja del sistema (al lado del
   reloj de Windows, abajo a la derecha) y sigue funcionando y avisando
   aunque la ventana este cerrada. Para volver a abrirla, doble click en
   el icono verde de la bandeja.


INSTALACION (una sola vez)
---------------------------
1) Instalar Python (si la computadora no lo tiene):
   - Ir a https://www.python.org/downloads/
   - Descargar la version para Windows
   - Al instalar, IMPORTANTE: tildar la casilla que dice
     "Add python.exe to PATH" antes de darle a Install.

2) Guardar esta carpeta completa "FutbolYRecordatorios" en la
   computadora (por ejemplo en el Escritorio).

3) Hacer doble click en "iniciar.bat".
   La primera vez va a tardar un poco mas porque instala las librerias
   necesarias (requests, plyer, pystray, Pillow) y ademas busca los IDs
   de cada competicion en la API. Eso solo pasa la primera vez.

4) Listo, deberia abrirse la ventana del programa.


INICIO AUTOMATICO CON WINDOWS (recomendado)
----------------------------------------------
Como tu papa apaga la computadora a la noche, conviene que el programa
arranque solo cuando la prenda de nuevo, sin que tenga que abrir nada.

1) Despues de haber usado "iniciar.bat" al menos una vez (para que ya
   esten instaladas las librerias), hacer doble click en
   "agregar_inicio_automatico.bat".
2) Va a aparecer un mensaje confirmando que quedo instalado. Con eso ya
   esta: la proxima vez que se prenda la PC, el programa arranca solo,
   SIN ninguna ventana ni consola negra (corre calladito en la bandeja
   del sistema, y desde ahi sigue mandando los avisos).

Para desactivar el inicio automatico en algun momento, doble click en
"quitar_inicio_automatico.bat".


USO DIARIO
-----------
- IMPORTANTE sobre "iniciar.bat": abre una consola negra porque el
  programa corre DENTRO de esa consola. Si se cierra esa ventana negra,
  el programa se apaga por completo (no sigue en la bandeja). Ese
  archivo es solo para la primera vez / para revisar errores.

- Para uso normal, sin riesgo de cerrar nada por error, usar
  "iniciar_segundo_plano.bat": arranca el programa sin ninguna consola
  ni ventana visible, directo a la bandeja del sistema.

- Si activaste el inicio automatico (ver mas abajo), no hace falta tocar
  ningun .bat nunca mas: arranca solo.

- Una vez que la ventana principal esta abierta, se la puede cerrar
  con la X sin problema: el programa sigue funcionando y avisando, y
  queda minimizado ABAJO EN LA BARRA DE TAREAS (como cualquier otro
  programa - Word, el navegador, etc). Para volver a abrirlo y tocar el
  boton de "LLAMADO A COMER", con un click en ese icono de la barra de
  tareas alcanza.

- Tambien queda un icono chiquito (pelota verde) en la bandeja del
  reloj, abajo a la derecha, como forma alternativa de abrirlo. Desde
  ahi, con click derecho, esta la opcion "Salir" para cerrar el
  programa del todo (no solo minimizarlo).

- Las notificaciones (partido por arrancar / hora de medirse) aparecen
  siempre arriba de cualquier cosa que este haciendo en la compu
  (diario, juegos, lo que sea), no hace falta tener el programa abierto
  para verlas. El aviso de "hora de medirse" ademas abre la ventana
  grande roja solo, automaticamente, encima de todo.


DE DONDE SALEN LOS PARTIDOS
------------------------------
Los datos de partidos vienen de TheSportsDB (gratis, sin necesidad de
registrarse), la misma API que ya se usa en el bot de Discord. No usa
API-Football para esto (esa API existe en el codigo por el temporizador
en un principio, pero quedo sin uso para partidos porque el plan
gratuito no tenia cargados los partidos de estas competiciones).


SI ALGO NO FUNCIONA
---------------------
- Se genera un archivo "registro.log" en esta misma carpeta con el
  detalle de que hizo el programa: que competiciones encontro, TODAS
  las opciones que le devolvio la API para cada busqueda (no solo la
  elegida), y si hubo errores de conexion.

- Para confirmar rapido que las 6 competiciones (Liga Argentina, Copa
  Argentina, Libertadores, Sudamericana, MLS y Champions) quedaron bien
  configuradas, doble click en "verificar_ligas.bat". Te muestra un
  resumen tipo lista con el nombre exacto y el ID que le asigno a cada
  una. Si alguna aparece con un nombre raro o equivocado, se puede
  editar a mano en "config.json" (dentro del bloque "ligas") o borrar
  esa entrada puntual y correr "iniciar.bat" de nuevo para que la
  vuelva a buscar.

- Si la API-Football devuelve error de limite de pedidos, es porque el
  plan gratis permite 100 pedidos por dia; el programa esta armado para
  usar muy pocos (consulta los partidos cada 4 horas), asi que no
  deberia pasar en uso normal.


DESINSTALAR
-------------
1) Click derecho en el icono de la bandeja del sistema y "Salir" (para
   cerrar el programa si esta corriendo).
2) Doble click en "desinstalar.bat" (saca el inicio automatico de
   Windows si estaba activado, y cierra el proceso si quedo alguno
   corriendo).
3) Borrar la carpeta "FutbolYRecordatorios" completa desde el
   Explorador de Windows.

Con eso no queda nada instalado. Python en si se puede dejar (no
molesta) o desinstalar desde "Agregar o quitar programas" si no se usa
para nada mas en esa computadora.


PARA EL FUTURO
----------------
El codigo esta separado en:
 - app.py            -> ventana, boton de comida/timer, bandeja del sistema
 - api_deportes.py    -> todo lo que habla con la API de futbol
 - config.json         -> configuracion (API key, ligas resueltas, etc)

Para agregar el boton de "aplicacion de insulina" mas adelante, se puede
sumar un segundo boton en app.py con su propio temporizador, siguiendo
el mismo patron que "LLAMADO A COMER".
