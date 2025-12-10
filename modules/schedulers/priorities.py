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
    # Lógica Clustering REVISADA (Urgencia Estricta > Color)
    if q.empty: return deque()
    q = q.copy()
    # Convertir Urgente a booleano real
    q["Urgente"] = q["Urgente"].apply(lambda x: es_si(x))
    
    q["_cliente_key"] = q.get("Cliente", "").fillna("").astype(str).str.strip().str.lower()
    q["_color_key"] = (
        q.get("Colores", "").fillna("").astype(str).str.lower()
        .str.replace("-", "", regex=False).str.strip()
    )
    q["DueDate"] = pd.to_datetime(q["DueDate"], dayfirst=True, errors="coerce")

    # Separar en Urgent y Normal
    q_urgente = q[q["Urgente"]].copy()
    q_normal = q[~q["Urgente"]].copy()

    def _agrupar_subcola(sub_q):
        if sub_q.empty: return []
        grupos = []
        for color, g in sub_q.groupby("_color_key", dropna=False):
            due_min_del_color = g["DueDate"].min()
            # Orden interno del grupo
            g_sorted = g.sort_values(by=["DueDate", "_cliente_key", "CantidadPliegos"], ascending=[True, True, False])
            grupos.append((due_min_del_color, g_sorted.to_dict("records")))
        grupos.sort(key=lambda x: x[0]) # Ordenar por fecha del grupo
        return [item for _, recs in grupos for item in recs]

    sorted_urgente = _agrupar_subcola(q_urgente)
    sorted_normal = _agrupar_subcola(q_normal)

    return deque(sorted_urgente + sorted_normal)

def _cola_impresora_offset(q):
    if q.empty: return deque()
    q = q.copy()

    # 1. LIMPIEZA DE DATOS
    # ------------------------------------------------------------
    q["_cliente_key"] = q.get("Cliente", "").fillna("").astype(str).str.strip().str.lower()
    q["_troq_key"] = q.get("CodigoTroquel", "").fillna("").astype(str).str.strip().str.lower()
    q["_proceso_norm"] = q.get("Proceso", "").fillna("").astype(str).str.strip().str.lower()
    
    # Limpieza de Color
    q["_color_key"] = (
        q.get("Colores", "")
        .fillna("")
        .astype(str)
        .str.lower()
        .str.replace("-", "", regex=False)
        .str.strip()
    )

    # Asegurar fechas correctas
    q["DueDate"] = pd.to_datetime(q["DueDate"], dayfirst=True, errors="coerce")
    q["DueDate"] = q["DueDate"].fillna(pd.Timestamp.max)

    # 2. SEPARAR POR TIPO DE PROCESO
    # Prioridad: (0=Impresion CMYK/Pantone, 1=Barnizado)
    # Esto asegura que todas las impresiones (mismo DueDate) se hagan antes de pasar a Barnizado.
    
    mask_barniz = q["_proceso_norm"].str.contains("barniz", na=False)
    
    q_barniz = q[mask_barniz]
    q_impresion = q[~mask_barniz] # CMYK y Pantone aqui
    
    grupos_todos = []

    # 3. GRUPO IMPRESION (Prioridad 0)
    # ------------------------------------------------------------
    # Dentro de impresion, mantenemos la distincion CMYK vs Pantone si se quiere,
    # o simplificamos. Por ahora, distinguimos para respetar agrupamiento de Troquel vs Color.
    
    if not q_impresion.empty:
        colores_upper = q_impresion["_color_key"].str.upper()
        mask_pantone = colores_upper.str.contains(r'[^CMYK]', na=False)
        
        q_cmyk = q_impresion[~mask_pantone]
        q_pantone = q_impresion[mask_pantone]
        
        # 3.1 CMYK -> Agrupar por CLIENTE + TROQUEL
        for keys, g in q_cmyk.groupby(["_cliente_key", "_troq_key"], dropna=False):
            due_min = g["DueDate"].min()
            es_urgente = g["Urgente"].apply(es_si).any()
            g_sorted = g.sort_values(["Urgente", "DueDate", "CantidadPliegos"], ascending=[False, True, False])
            # Prio 0
            grupos_todos.append((not es_urgente, due_min, 0, keys[0], keys[1], g_sorted.to_dict("records")))

        # 3.2 PANTONE -> Agrupar por CLIENTE + COLOR
        for keys, g in q_pantone.groupby(["_cliente_key", "_color_key"], dropna=False):
            due_min = g["DueDate"].min()
            es_urgente = g["Urgente"].apply(es_si).any()
            g_sorted = g.sort_values(["Urgente", "DueDate", "CantidadPliegos"], ascending=[False, True, False])
            # Prio 0 (Mismo nivel que CMYK, se ordenan entre ellos por Fecha/Cliente)
            grupos_todos.append((not es_urgente, due_min, 0, keys[0], keys[1], g_sorted.to_dict("records")))

    # 4. GRUPO BARNIZADO (Prioridad 1)
    # ------------------------------------------------------------
    if not q_barniz.empty:
        # Agrupar solo por CLIENTE
        for cliente, g in q_barniz.groupby("_cliente_key", dropna=False):
            due_min = g["DueDate"].min()
            es_urgente = g["Urgente"].apply(es_si).any()
            g_sorted = g.sort_values(["Urgente", "DueDate", "CantidadPliegos"], ascending=[False, True, False])
            # Prio 1 -> Queda DESPUES de impresion si las fechas coinciden
            grupos_todos.append((not es_urgente, due_min, 1, cliente, "barniz", g_sorted.to_dict("records")))

    # 5. ORDENAMIENTO FINAL
    # ------------------------------------------------------------
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
        grupos.append((not es_urgente, due_min, troq, g_sorted.to_dict("records")))
    grupos.sort()
    return deque([item for _, _, _, recs in grupos for item in recs])
