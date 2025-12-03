import pandas as pd 
from collections import deque
from modules.config_loader import es_si

def _clave_prioridad_maquina(proceso: str, orden: pd.Series):
    marca = str(orden.get("Cliente") or "").strip().lower()
    colores = str(orden.get("Colores") or "").strip().lower()
    troquel = str(orden.get("CodigoTroquel") or "").strip().lower()
    material = str(orden.get("MateriaPrima") or "").strip().lower()
    pli_anc = orden.get("PliAnc")
    pli_lar = orden.get("PliLar")
    if proceso.lower().startswith("impres"): return (marca, colores, pli_anc, pli_lar)
    if proceso == "Troquelado": return (troquel,)
    if proceso == "Ventana": return (material, pli_anc, pli_lar)
    return tuple()

def _cola_impresora_flexo(q): 
    # Lógica Clustering (Agrupa Color -> Urgencia del Grupo)
    if q.empty: return deque()
    q = q.copy()
    # Convertir Urgente a booleano real para que .any() funcione bien
    q["Urgente"] = q["Urgente"].apply(lambda x: es_si(x))
    
    q["_cliente_key"] = q.get("Cliente", "").fillna("").astype(str).str.strip().str.lower()
    q["_color_key"] = (
        q.get("Colores", "").fillna("").astype(str).str.lower()
        .str.replace("-", "", regex=False).str.strip()
    )
    q["DueDate"] = pd.to_datetime(q["DueDate"], dayfirst=True, errors="coerce")
    
    grupos = []
    for color, g in q.groupby("_color_key", dropna=False):
        due_min_del_color = g["DueDate"].min()
        # Urgencia del grupo: Si alguna tarea es urgente, el grupo es urgente (True > False)
        es_urgente = g["Urgente"].any()
        
        g_sorted = g.sort_values(by=["Urgente", "DueDate", "_cliente_key", "CantidadPliegos"], ascending=[False, True, True, False])
        grupos.append((not es_urgente, due_min_del_color, color, g_sorted.to_dict("records")))
    
    grupos.sort() 
    return deque([item for _, _, _, recs in grupos for item in recs])

def _cola_impresora_offset(q):
    if q.empty: return deque()
    q = q.copy()

    # 1. LIMPIEZA DE DATOS (Igual que en Flexo)
    # ------------------------------------------------------------
    q["_cliente_key"] = q.get("Cliente", "").fillna("").astype(str).str.strip().str.lower()
    q["_troq_key"] = q.get("CodigoTroquel", "").fillna("").astype(str).str.strip().str.lower()
    
    # Limpieza de Color: Quitar guiones, espacios y mayúsculas
    q["_color_key"] = (
        q.get("Colores", "")
        .fillna("")
        .astype(str)
        .str.lower()
        .str.replace("-", "", regex=False) # <--- CLAVE: Ignorar guiones
        .str.strip()
    )

    # Asegurar fechas correctas
    q["DueDate"] = pd.to_datetime(q["DueDate"], dayfirst=True, errors="coerce")
    q["DueDate"] = q["DueDate"].fillna(pd.Timestamp.max)

    # 2. CLASIFICACIÓN (Pantone vs CMYK)
    # ------------------------------------------------------------
    colores_upper = q["_color_key"].str.upper()
    # Regex: Si tiene algo que NO sea C, M, Y, K o vacío, es Pantone
    mask_con_pantone = colores_upper.str.contains(r'[^CMYK]', na=False) # Quitamos el \- del regex porque ya borramos los guiones arriba
    
    q_sin_pantone = q[~mask_con_pantone]
    q_con_pantone = q[mask_con_pantone]

    grupos_todos = []

    # 3. GRUPO A: SIN PANTONE (CMYK) -> Agrupar por CLIENTE + TROQUEL
    # ------------------------------------------------------------
    if not q_sin_pantone.empty:
        for keys, g in q_sin_pantone.groupby(["_cliente_key", "_troq_key"], dropna=False):
            # Urgencia del grupo entero
            due_min = g["DueDate"].min()
            es_urgente = g["Urgente"].any()
            
            # Orden interno
            g_sorted = g.sort_values(["Urgente", "DueDate", "CantidadPliegos"], ascending=[False, True, False])
            
            # Tupla: (NoUrgente, Fecha, Prioridad 0, Cliente, Troquel, Tareas)
            # False < True, así que usamos 'not es_urgente' para que True (Urgente) quede primero (False) en sort ascendente
            grupos_todos.append((not es_urgente, due_min, 0, keys[0], keys[1], g_sorted.to_dict("records")))

    # 4. GRUPO B: CON PANTONE -> Agrupar por CLIENTE + COLOR
    # ------------------------------------------------------------
    if not q_con_pantone.empty:
        for keys, g in q_con_pantone.groupby(["_cliente_key", "_color_key"], dropna=False):
            # Urgencia del grupo entero
            due_min = g["DueDate"].min()
            es_urgente = g["Urgente"].any()
            
            # Orden interno
            g_sorted = g.sort_values(["Urgente", "DueDate", "CantidadPliegos"], ascending=[False, True, False])
            
            # Tupla: (NoUrgente, Fecha, Prioridad 1, Cliente, Color, Tareas)
            # Nota: Si prefieres que NO se separen CMYK de Pantone por defecto, 
            # cambia el '1' por '0' aquí también. Pero usualmente es mejor separarlos.
            grupos_todos.append((not es_urgente, due_min, 1, keys[0], keys[1], g_sorted.to_dict("records")))
    
    # 5. ORDENAMIENTO FINAL DE BLOQUES
    # ------------------------------------------------------------
    # Ordena por: NoUrgente -> Fecha -> Prioridad (0=CMYK, 1=Pantone) -> Cliente
    grupos_todos.sort() 

    return deque([item for _, _, _, _, _, recs in grupos_todos for item in recs])

def _cola_troquelada(q): 
    if q.empty: return deque()
    q = q.copy()
    q["_troq_key"] = q.get("CodigoTroquel", "").fillna("").astype(str).str.strip().str.lower()
    grupos = []
    for troq, g in q.groupby("_troq_key", dropna=False):
        due_min = pd.to_datetime(g["DueDate"], errors="coerce").min() or pd.Timestamp.max
        es_urgente = g["Urgente"].any()
        g_sorted = g.sort_values(["Urgente", "DueDate", "CantidadPliegos"], ascending=[False, True, False])
        grupos.append((es_urgente, due_min, troq, g_sorted.to_dict("records")))
    grupos.sort()
    return deque([item for _, _, _, recs in grupos for item in recs])
