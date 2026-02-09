import streamlit as st

color_map_procesos = {
    "Cortadora Bobina": "lightgray", #Gris claro
    "Guillotina": "dimgray",        # Gris oscuro
    "Impresión Offset": "mediumseagreen", # Verde mar
    "Impresión Flexo": "darkorange",
    "Plastificado": "violet",      
    "Barnizado": "gold",            # Dorado (o "Barniz" si se llama así)
    "Barniz": "gold",               # Añade variantes si es necesario
    "OPP": "slateblue",             # Azul pizarra
    "Stamping": "firebrick",        # Rojo ladrillo
    "Cuño": "darkcyan",             # Cian oscuro (Añade si es un proceso)
    "Encapado": "sandybrown",       # Marrón arena (Añade si es un proceso)
    "Troquelado": "lightcoral",     # Coral claro
    "Descartonado": "dodgerblue",   # Azul brillante
    "Ventana": "skyblue",           # Azul cielo
    "Pegado": "mediumpurple",         # Púrpura medio
}

def ordenar_maquinas_personalizado(lista_maquinas):
    """Ordena máquinas según prioridad operativa definida por el usuario."""
    prioridades = [
        (1, ["bobina", "cortadora de bobinas"]),
        (2, ["guillotina"]),
        (3, ["offset", "heidelberg"]),
        (4, ["flexo", "flexo 2 col"]),
        (5, ["stamping"]),
        (6, ["plastificadora"]),
        (7, ["encapado"]),
        (8, ["cuño"]),
        (9, ["automat", "automát", "duyan"]),
        (10, ["manual 1", "manual-1", "manual1", "troq nº 2 ema"]),
        (11, ["manual 2", "manual-2", "manual2", "troq nº 1 gus"]),
        (12, ["manual 3", "manual-3", "manual3"]),
        (13, ["iberica"]),
        (14, ["descartonadora 1"]),
        (15, ["descartonadora 2"]),
        (16, ["descartonadora 3"]),
        (17, ["descartonadora 4"]),
        (18, ["ventana", "pegadora ventana"]),
        (19, ["pegadora", "pegado", "pegadora universal"]),
    ]

    def clave(nombre):
        nombre_str = str(nombre).lower()
        for prioridad, patrones in prioridades:
            if any(pat in nombre_str for pat in patrones):
                return (prioridad, nombre_str)
        return (len(prioridades) + 1, nombre_str)

    return sorted(lista_maquinas, key=clave, reverse=True)
