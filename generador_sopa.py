# -*- coding: utf-8 -*-
"""Generador de sopa de letras (Etapa 4).

Este modulo NO dibuja nada -- solo arma los datos: una grilla de letras
y la lista de palabras que quedaron escondidas ahi adentro, con su
posicion exacta. La vista (Canvas con drag-select, Etapa 5) va a usar
esos datos para dibujar y para validar cuando el usuario selecciona una
palabra.

Uso tipico:
    from generador_sopa import generar_sopa
    sopa = generar_sopa()
    sopa["grilla"]    # lista de listas de letras (17 filas x 17 columnas)
    sopa["palabras"]  # lista de dicts: palabra, fila, columna, df, dc
"""
import random
import string

ANCHO_POR_DEFECTO = 17
ALTO_POR_DEFECTO = 17
CANTIDAD_PALABRAS_POR_DEFECTO = 12

# Direcciones "faciles" (por defecto): siempre para adelante, nunca al
# reves -- mas comodo de leer para mi viejo. (df, dc) = cuanto se mueve
# la fila y la columna por cada letra de la palabra.
DIRECCIONES_FACIL = [
    (0, 1),   # derecha
    (1, 0),   # abajo
    (1, 1),   # diagonal abajo-derecha
    (1, -1),  # diagonal abajo-izquierda
]

# Las 8 direcciones, incluye al reves -- para un modo "dificil" a
# futuro si hace falta.
DIRECCIONES_DIFICIL = DIRECCIONES_FACIL + [
    (0, -1),   # izquierda
    (-1, 0),   # arriba
    (-1, -1),  # diagonal arriba-izquierda
    (-1, 1),   # diagonal arriba-derecha
]

# Banco de palabras en espanol -- variado a proposito (no separado por
# categorias, como pidio Sebi), evitando palabras demasiado raras o
# tecnicas. Todas van a mayusculas y sin espacios/guiones para que
# entren limpitas en la grilla.
BANCO_DE_PALABRAS = [
    # Futbol / deportes (tematica del programa)
    "PELOTA", "ARQUERO", "GOLEADOR", "ESTADIO", "HINCHA", "CAMPEON",
    "PENAL", "CORNER", "REFEREE", "DELANTERO", "DEFENSA", "MEDIOCAMPO",
    "TARJETA", "MUNDIAL", "SELECCION", "EQUIPO", "PARTIDO", "TRIUNFO",
    "EMPATE", "DERROTA", "TECNICO", "CANCHA", "TRIBUNA", "CAMISETA",
    "BOTIN", "SILBATO", "ARCO", "TRAVESANO", "LATERAL", "CAPITAN",
    "TENIS", "BASQUET", "BOXEO", "CICLISMO", "NATACION", "ATLETISMO",
    "MEDALLA", "PODIO", "OLIMPIADA", "TORNEO", "TRIBUNA", "PLANTEL",
    # Animales
    "PERRO", "GATO", "CABALLO", "VACA", "OVEJA", "CERDO", "GALLINA",
    "PATO", "CONEJO", "TORTUGA", "LEON", "TIGRE", "ELEFANTE", "JIRAFA",
    "MONO", "OSO", "ZORRO", "LOBO", "AGUILA", "LORO", "DELFIN",
    "BALLENA", "TIBURON", "PULPO", "CANGREJO", "ABEJA", "MARIPOSA",
    "HORMIGA", "ARANA", "SERPIENTE", "RANA", "PINGUINO", "CEBRA",
    # Comida y cocina
    "PAN", "QUESO", "LECHE", "HUEVO", "ARROZ", "FIDEO", "CARNE",
    "POLLO", "PESCADO", "MANZANA", "NARANJA", "BANANA", "LIMON",
    "TOMATE", "LECHUGA", "CEBOLLA", "PAPA", "ZAPALLO", "ASADO",
    "EMPANADA", "MILANESA", "GUISO", "TORTA", "GALLETA", "HELADO",
    "CAFE", "MATE", "AZUCAR", "SAL", "ACEITE", "VINAGRE", "MIEL",
    "CHOCOLATE", "DULCE", "POSTRE", "ENSALADA", "SOPA", "PIZZA",
    # Casa y objetos cotidianos
    "MESA", "SILLA", "CAMA", "PUERTA", "VENTANA", "COCINA", "BANIO",
    "TECHO", "PARED", "JARDIN", "ESPEJO", "LAMPARA", "RELOJ", "LIBRO",
    "LAPIZ", "PAPEL", "TIJERA", "TELEFONO", "RADIO", "TELEVISOR",
    "HELADERA", "ESCOBA", "TOALLA", "ALMOHADA", "MANTA", "CORTINA",
    "MACETA", "PLATO", "VASO", "CUCHARA", "TENEDOR", "CUCHILLO", "OLLA",
    # Naturaleza y clima
    "SOL", "LUNA", "ESTRELLA", "CIELO", "NUBE", "LLUVIA", "VIENTO",
    "NIEVE", "RIO", "MAR", "MONTANIA", "BOSQUE", "ARBOL", "FLOR",
    "HOJA", "SEMILLA", "PIEDRA", "ARENA", "PLAYA", "ISLA", "VOLCAN",
    "TORMENTA", "ARCOIRIS", "AMANECER", "ATARDECER", "OTONIO",
    "INVIERNO", "VERANO", "PRIMAVERA",
    # Familia y personas
    "FAMILIA", "PADRE", "MADRE", "HIJO", "HIJA", "HERMANO", "ABUELO",
    "ABUELA", "NIETO", "PRIMO", "TIO", "SOBRINO", "AMIGO", "VECINO",
    "MAESTRO", "MEDICO", "ENFERMERO", "COCINERO", "BOMBERO", "PILOTO",
    "ARTISTA", "MUSICO", "ESCRITOR", "PINTOR", "ACTOR", "CANTANTE",
    # Ciudades y lugares de Argentina
    "BUENOSAIRES", "CORDOBA", "ROSARIO", "MENDOZA", "SALTA", "BARILOCHE",
    "IGUAZU", "PATAGONIA", "PAMPA", "TIGRE", "LAPLATA", "USHUAIA",
    # Musica y baile
    "TANGO", "MILONGA", "FOLKLORE", "GUITARRA", "PIANO", "BATERIA",
    "VIOLIN", "CANCION", "BAILE", "ORQUESTA", "CONCIERTO", "RITMO",
    # Varios
    "TRABAJO", "ESCUELA", "VACACIONES", "VIAJE", "AUTO", "BICICLETA",
    "TREN", "AVION", "BARCO", "CAMINO", "CIUDAD", "PUEBLO", "PLAZA",
    "MERCADO", "TIENDA", "DINERO", "REGALO", "FIESTA", "CUMPLEANIOS",
    "NAVIDAD", "AMISTAD", "ALEGRIA", "SONRISA", "ABRAZO", "CARINIO",
    # Colores
    "ROJO", "AZUL", "VERDE", "AMARILLO", "NARANJA", "VIOLETA", "ROSA",
    "MARRON", "GRIS", "NEGRO", "BLANCO", "CELESTE", "DORADO", "PLATEADO",
    "TURQUESA", "BEIGE", "BORDO", "FUCSIA",
    # Cuerpo humano
    "CABEZA", "PELO", "OJO", "OREJA", "NARIZ", "BOCA", "DIENTE", "CUELLO",
    "HOMBRO", "BRAZO", "CODO", "MANO", "DEDO", "PECHO", "ESPALDA",
    "PANZA", "CINTURA", "PIERNA", "RODILLA", "TOBILLO", "PIE", "CORAZON",
    "PULMON", "CEREBRO", "PIEL", "UNIA", "CEJA", "PESTANIA", "MEJILLA",
    "MENTON", "MUNIECA",
    # Ropa y vestimenta
    "CAMISA", "REMERA", "PANTALON", "SHORT", "PULOVER", "CAMPERA",
    "ABRIGO", "BUFANDA", "GORRO", "GORRA", "SOMBRERO", "GUANTE",
    "MEDIA", "ZAPATO", "ZAPATILLA", "SANDALIA", "CINTURON", "CORBATA",
    "VESTIDO", "POLLERA", "TRAJE", "PIJAMA", "BOLSILLO", "BOTON",
    "CIERRE", "MOCHILA", "CARTERA", "BILLETERA", "ANTEOJO", "PARAGUAS",
    # Herramientas y oficios
    "MARTILLO", "DESTORNILLADOR", "TENAZA", "SIERRA", "TALADRO",
    "CLAVO", "TORNILLO", "ESCALERA", "PINTOR", "ALBANIL", "PLOMERO",
    "ELECTRICISTA", "CARPINTERO", "MECANICO", "JARDINERO", "PANADERO",
    "ZAPATERO", "SASTRE", "PELUQUERO", "ABOGADO", "INGENIERO",
    "ARQUITECTO", "PERIODISTA", "CHOFER", "GUARDIA", "VENDEDOR",
    # Transporte
    "COLECTIVO", "SUBTE", "TAXI", "CAMION", "MOTO", "HELICOPTERO",
    "COHETE", "SUBMARINO", "CANOA", "VELERO", "CARRETA", "TRINEO",
    "MONOPATIN", "PATINETA",
    # Tecnologia
    "COMPUTADORA", "CELULAR", "TABLET", "TECLADO", "PANTALLA", "MOUSE",
    "IMPRESORA", "CAMARA", "AURICULAR", "PARLANTE", "CARGADOR", "CABLE",
    "INTERNET", "APLICACION", "VIDEOJUEGO", "ROBOT", "SATELITE",
    "ANTENA", "BATERIA", "PROGRAMA",
    # Geografia del mundo
    "AMERICA", "EUROPA", "AFRICA", "ASIA", "OCEANIA", "BRASIL", "CHILE",
    "URUGUAY", "PARAGUAY", "PERU", "COLOMBIA", "MEXICO", "ESPANIA",
    "FRANCIA", "ITALIA", "ALEMANIA", "JAPON", "CHINA", "EGIPTO",
    "CONTINENTE", "OCEANO", "DESIERTO", "GLACIAR", "CATARATA",
    "CORDILLERA", "VALLE", "ANDES",
    # Plantas y jardin
    "ROSA", "MARGARITA", "GIRASOL", "CACTUS", "HELECHO", "PASTO",
    "RAIZ", "TALLO", "RAMA", "FRUTA", "VERDURA", "COSECHA", "SIEMBRA",
    "INVERNADERO", "MACETERO", "REGADERA",
    # Sentimientos y estados
    "AMOR", "FELICIDAD", "TRISTEZA", "ENOJO", "MIEDO", "SORPRESA",
    "CALMA", "PACIENCIA", "CORAJE", "ESPERANZA", "GRATITUD", "ORGULLO",
    "TERNURA", "CONFIANZA", "NOSTALGIA", "ENTUSIASMO",
    # Escuela y aprendizaje
    "CUADERNO", "MOCHILA", "MAPA", "GLOBO", "PIZARRON", "TIZA",
    "REGLA", "GOMA", "CARTUCHERA", "BIBLIOTECA", "AULA", "RECREO",
    "EXAMEN", "TAREA", "LECTURA", "ESCRITURA", "NUMERO", "LETRA",
    "IDIOMA", "HISTORIA", "GEOGRAFIA", "CIENCIA", "MATEMATICA",
    # Otros deportes
    "BASQUET", "TENIS", "VOLEY", "NATACION", "BOXEO", "CICLISMO",
    "ATLETISMO", "GOLF", "HOCKEY", "PATIN", "ESGRIMA", "REMO",
    "SURF", "SKATE", "AJEDREZ", "MARATON", "PELOTA", "RAQUETA",
    "PILETA", "CANCHA", "ARBITRO", "ENTRENADOR", "MEDALLA", "TROFEO",
    "PODIO", "CARRERA", "SALTO", "CARDIO", "MUSCULO", "ELONGACION",
    # Comida argentina y cocina
    "ASADO", "CHORIZO", "MORCILLA", "EMPANADA", "MILANESA", "LOCRO",
    "MATE", "YERBA", "BOMBILLA", "FACTURA", "MEDIALUNA", "ALFAJOR",
    "DULCE", "PROVOLETA", "PARRILLA", "GUISO", "TARTA", "BUDIN",
    "TORTA", "FLAN", "HELADO", "SANDWICH", "PIZZA", "PASTA", "TALLARIN",
    "NIOQUI", "RAVIOLES", "PURE", "ENSALADA", "SOPA", "CALDO",
    "OLLA", "SARTEN", "CUCHARA", "TENEDOR", "CUCHILLO", "PLATO",
    "VASO", "TAZA", "MANTEL", "SERVILLETA", "HELADERA", "HORNO",
    "MICROONDAS", "LICUADORA", "TOSTADORA", "PAVA",
    # Muebles y electrodomesticos
    "MESA", "SILLA", "SOFA", "SILLON", "ESTANTE", "ARMARIO", "CAJON",
    "ESPEJO", "LAMPARA", "ALFOMBRA", "CORTINA", "VENTILADOR", "ESTUFA",
    "AIRE", "PLANCHA", "LAVARROPAS", "ASPIRADORA", "TELEVISOR",
    "CONTROL", "COLCHON", "ALMOHADA", "SABANA", "FRAZADA",
    # Insectos y animales marinos
    "HORMIGA", "MOSCA", "MOSQUITO", "ABEJA", "AVISPA", "LUCIERNAGA",
    "GRILLO", "SALTAMONTES", "LIBELULA", "CIEMPIES", "DELFIN",
    "BALLENA", "TIBURON", "PULPO", "MEDUSA", "ESTRELLA", "CANGREJO",
    "LANGOSTA", "CAMARON", "CALAMAR", "FOCA", "MORSA", "PINGUINO",
    # Salud y cuidado personal
    "MEDICO", "ENFERMERO", "HOSPITAL", "REMEDIO", "PASTILLA",
    "VENDAJE", "TERMOMETRO", "JERINGA", "DENTISTA", "CEPILLO",
    "JABON", "TOALLA", "PEINE", "PERFUME", "CREMA", "SHAMPOO",
    "DESCANSO", "EJERCICIO", "VITAMINA", "AGUA",
    # Oficina y papeleria
    "LAPIZ", "LAPICERA", "MARCADOR", "PAPEL", "SOBRE", "CARPETA",
    "AGENDA", "CALCULADORA", "GRAPADORA", "TIJERA", "CINTA", "SELLO",
    "FIRMA", "FORMULARIO", "ARCHIVO", "ESCRITORIO", "SILLAGIRATORIA",
    # Clima y fenomenos naturales
    "TORMENTA", "RAYO", "TRUENO", "GRANIZO", "NIEBLA", "ROCIO",
    "ARCOIRIS", "ECLIPSE", "TERREMOTO", "INUNDACION", "SEQUIA",
    "HURACAN", "TORNADO", "MAREA", "OLA", "CORRIENTE",
    # Musica e instrumentos
    "GUITARRA", "PIANO", "VIOLIN", "BATERIA", "BAJO", "FLAUTA",
    "TROMPETA", "ACORDEON", "BANDONEON", "TAMBOR", "MICROFONO",
    "ESCENARIO", "CONCIERTO", "ORQUESTA", "CANTANTE", "MELODIA",
    "RITMO", "TANGO", "FOLCLORE", "CUARTETO", "CUMBIA", "ROCK",
    # Cine, tv y entretenimiento
    "PELICULA", "SERIE", "ACTOR", "ACTRIZ", "DIRECTOR", "GUION",
    "PANTALLA", "BUTACA", "PALOMITA", "ENTRADA", "PERSONAJE",
    "ESCENA", "APLAUSO", "COMEDIA", "DRAMA", "AVENTURA",
    # Mas geografia y lugares
    "MONTEVIDEO", "SANTIAGO", "LIMA", "BOGOTA", "ASUNCION",
    "MADRID", "ROMA", "LONDRES", "PARIS", "BERLIN", "MOSCU",
    "ISLA", "PENINSULA", "BAHIA", "ARCHIPIELAGO", "MERIDIANO",
    "ECUADOR", "POLO", "LATITUD", "LONGITUD",
]

# Palabras duplicadas que quedaron de antes de esta ampliacion (TRIBUNA,
# TIGRE, ROSA -- esta ultima aparece en Colores y en Plantas, queda
# bien en las dos asi que se saca solo la copia de mas) se limpian
# ACA, en un solo lugar, en vez de tener que revisar a mano cada
# categoria de arriba cada vez que se agrega una palabra nueva.
BANCO_DE_PALABRAS = list(dict.fromkeys(BANCO_DE_PALABRAS))

# El generador de letras de relleno usa el abecedario en espanol
# (incluye Ñ) con una frecuencia aproximada a como se usan de verdad
# las letras en espanol -- si fuera parejo, aparecerian demasiadas
# letras raras (K, W, X) y quedaria raro. Las vocales y consonantes
# comunes se repiten mas veces en esta lista para que salgan mas
# seguido al rellenar.
LETRAS_RELLENO = list(
    "A" * 12 + "E" * 12 + "O" * 9 + "S" * 8 + "N" * 7 + "R" * 7 +
    "I" * 6 + "U" * 5 + "L" * 5 + "T" * 5 + "D" * 5 + "C" * 4 +
    "M" * 3 + "P" * 3 + "B" * 2 + "G" * 2 + "V" * 2 + "Y" * 1 +
    "Q" * 1 + "H" * 2 + "F" * 1 + "J" * 1 + "Z" * 1 + "Ñ" * 1
)


def _normalizar(palabra):
    """Mayusculas y sin espacios/guiones -- las tildes se mantienen
    porque van a mostrarse tal cual en la grilla."""
    return palabra.strip().upper().replace(" ", "").replace("-", "")


def elegir_palabras(cantidad, ancho, alto, banco=None):
    """Elige al azar `cantidad` palabras del banco que entren en una
    grilla de `ancho` x `alto` (el largo de la palabra no puede superar
    la dimension mas chica de la grilla). Si el banco tiene menos
    palabras utilizables que las pedidas, devuelve las que haya."""
    banco = banco if banco is not None else BANCO_DE_PALABRAS
    maximo = min(ancho, alto)
    candidatas = [_normalizar(p) for p in banco if len(_normalizar(p)) <= maximo]
    candidatas = list(dict.fromkeys(candidatas))  # sin duplicados, conserva orden
    random.shuffle(candidatas)
    return candidatas[:cantidad]


def _cabe(grilla, palabra, fila, columna, df, dc, alto, ancho):
    """True si `palabra` entra a partir de (fila, columna) en la
    direccion (df, dc) sin salirse de la grilla y sin chocar con una
    letra ya puesta que no coincida (los cruces SI se permiten cuando
    la letra es la misma, como en cualquier sopa de letras posta)."""
    f, c = fila, columna
    for letra in palabra:
        if not (0 <= f < alto and 0 <= c < ancho):
            return False
        ocupada = grilla[f][c]
        if ocupada is not None and ocupada != letra:
            return False
        f += df
        c += dc
    return True


def _colocar(grilla, palabra, fila, columna, df, dc):
    f, c = fila, columna
    for letra in palabra:
        grilla[f][c] = letra
        f += df
        c += dc


def generar_sopa(ancho=ANCHO_POR_DEFECTO, alto=ALTO_POR_DEFECTO,
                  cantidad_palabras=CANTIDAD_PALABRAS_POR_DEFECTO,
                  permitir_reversa=False, banco=None, intentos_por_palabra=200):
    """Arma una sopa de letras nueva. Devuelve un dict:
        {
          "ancho": int, "alto": int,
          "grilla": [[letra, ...], ...]  (alto filas x ancho columnas),
          "palabras": [
              {"palabra": "GATO", "fila": 2, "columna": 5,
               "df": 0, "dc": 1, "encontrada": False},
              ...
          ],
        }
    Las palabras que por mala suerte no entraron despues de agotar los
    intentos simplemente se descartan (no rompe nada, la sopa queda
    con un par de palabras menos en vez de fallar)."""
    direcciones = DIRECCIONES_DIFICIL if permitir_reversa else DIRECCIONES_FACIL

    candidatas = elegir_palabras(cantidad_palabras * 2, ancho, alto, banco=banco)
    # Mas largas primero: son las que menos lugares tienen para entrar,
    # asi que conviene ubicarlas cuando la grilla todavia esta vacia.
    candidatas.sort(key=len, reverse=True)

    grilla = [[None] * ancho for _ in range(alto)]
    colocadas = []

    for palabra in candidatas:
        if len(colocadas) >= cantidad_palabras:
            break
        ubicada = False
        for _ in range(intentos_por_palabra):
            df, dc = random.choice(direcciones)
            fila = random.randrange(alto)
            columna = random.randrange(ancho)
            if _cabe(grilla, palabra, fila, columna, df, dc, alto, ancho):
                _colocar(grilla, palabra, fila, columna, df, dc)
                colocadas.append({
                    "palabra": palabra, "fila": fila, "columna": columna,
                    "df": df, "dc": dc, "encontrada": False,
                })
                ubicada = True
                break
        # si no entro en ningun intento, se descarta y se sigue con la
        # proxima palabra candidata (por eso pedimos el doble de
        # candidatas de las que hacen falta al principio)

    # Relleno: cualquier celda que quedo vacia se llena con una letra
    # al azar (con la distribucion de LETRAS_RELLENO).
    for f in range(alto):
        for c in range(ancho):
            if grilla[f][c] is None:
                grilla[f][c] = random.choice(LETRAS_RELLENO)

    return {"ancho": ancho, "alto": alto, "grilla": grilla, "palabras": colocadas}


def imprimir_sopa(sopa):
    """Solo para debug por consola -- no lo usa la app."""
    for fila in sopa["grilla"]:
        print(" ".join(fila))
    print()
    print(f"{len(sopa['palabras'])} palabras colocadas:")
    print(", ".join(p["palabra"] for p in sopa["palabras"]))


if __name__ == "__main__":
    random.seed(1)
    s = generar_sopa()
    imprimir_sopa(s)
