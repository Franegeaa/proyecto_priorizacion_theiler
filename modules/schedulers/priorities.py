import pandas as pd 
from collections import deque
from modules.utils.config_loader import es_si

def _clave_prioridad_maquina(proceso: str, orden: pd.Series):
    marca = str(orden.get("Cliente") or "").strip().lower()
    colores = str(orden.get("Colores") or "").strip().lower()
    troquel = str(orden.get("CodigoTroquel") or "").strip().lower()
    material = str(orden.get("MateriaPrima") or "").strip().lower()
    pli_anc = orden.get("PliAnc")
    pli_lar = orden.get("PliLar")
    if proceso.lower().startswith("impres"): return (marca, colores, pli_anc, pli_lar)
    if proceso == "Troquelado": return (troquel,)
    if proceso == "Ventana": return (troquel,)
    return tuple()

def _cola_impresora_flexo(q):
    # Ahora usamos la misma lógica que Offset para respetar prioridades de Excel
    return _cola_impresora_universal(q)

def _cola_impresora_offset(q):
    return _cola_impresora_universal(q)

def _cola_impresora_universal(q):
    if q.empty: return deque()
    q = q.copy()

    # Ensure ManualPriority exists
    if "ManualPriority" not in q.columns: q["ManualPriority"] = 9999
    q["ManualPriority"] = q["ManualPriority"].fillna(9999).astype(int)

    # --- PRIORIDAD EXCEL COMPUESTA (FechaImDdp + PrioriImp) ---
    # El sistema externo asigna prioridades POR DÍA (1,2,3... resetea cada día).
    # "Prioridad 1 del 10/03" es más urgente que "Prioridad 1 del 11/03".
    # Combinamos fecha + número en una única clave de ordenamiento.
    if "FechaImDdp" in q.columns:
        q["_fecha_imp"] = pd.to_datetime(q["FechaImDdp"], errors="coerce")
    else:
        q["_fecha_imp"] = pd.NaT
    
    if "PrioriImp" in q.columns:
        q["_priori_imp_num"] = pd.to_numeric(q["PrioriImp"], errors="coerce").fillna(9999)
    else:
        q["_priori_imp_num"] = 9999
    
    # Fecha nula → al final
    q["_fecha_imp"] = q["_fecha_imp"].fillna(pd.Timestamp.max)

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
            min_prio = g["ManualPriority"].min()
            due_min = g["DueDate"].min()
            es_urgente = g["Urgente"].apply(es_si).any()
            fecha_imp_min = g["_fecha_imp"].min()
            priori_imp_min = g["_priori_imp_num"].min()
            
            g_sorted = g.sort_values(["ManualPriority", "_fecha_imp", "_priori_imp_num", "Urgente", "DueDate", "CantidadPliegos"], 
                                     ascending=[True, True, True, False, True, False])
            # Tupla: (ManualPrio, FechaExcel, PrioExcel, no_urgente, DueDate, tipo_proc, key1, key2, records)
            grupos_todos.append((min_prio, fecha_imp_min, priori_imp_min, not es_urgente, due_min, 0, keys[0], keys[1], g_sorted.to_dict("records")))

        # 3.2 PANTONE -> Agrupar por CLIENTE + COLOR
        for keys, g in q_pantone.groupby(["_cliente_key", "_color_key"], dropna=False):
            min_prio = g["ManualPriority"].min()
            due_min = g["DueDate"].min()
            es_urgente = g["Urgente"].apply(es_si).any()
            fecha_imp_min = g["_fecha_imp"].min()
            priori_imp_min = g["_priori_imp_num"].min()

            g_sorted = g.sort_values(["ManualPriority", "_fecha_imp", "_priori_imp_num", "Urgente", "DueDate", "CantidadPliegos"], 
                                     ascending=[True, True, True, False, True, False])
            # Tupla: (ManualPrio, FechaExcel, PrioExcel, no_urgente, DueDate, tipo_proc, key1, key2, records)
            grupos_todos.append((min_prio, fecha_imp_min, priori_imp_min, not es_urgente, due_min, 0, keys[0], keys[1], g_sorted.to_dict("records")))

    # 4. GRUPO BARNIZADO (Prioridad 1)
    # ------------------------------------------------------------
    if not q_barniz.empty:
        # Agrupar solo por CLIENTE
        for cliente, g in q_barniz.groupby("_cliente_key", dropna=False):
            min_prio = g["ManualPriority"].min()
            due_min = g["DueDate"].min()
            es_urgente = g["Urgente"].apply(es_si).any()
            fecha_imp_min = g["_fecha_imp"].min()
            priori_imp_min = g["_priori_imp_num"].min()

            g_sorted = g.sort_values(["ManualPriority", "_fecha_imp", "_priori_imp_num", "Urgente", "DueDate", "CantidadPliegos"], 
                                     ascending=[True, True, True, False, True, False])
            # Tupla: (ManualPrio, FechaExcel, PrioExcel, no_urgente, DueDate, tipo_proc, key1, key2, records)
            grupos_todos.append((min_prio, fecha_imp_min, priori_imp_min, not es_urgente, due_min, 1, cliente, "barniz", g_sorted.to_dict("records")))

    # 5. ORDENAMIENTO FINAL
    # ------------------------------------------------------------
    grupos_todos.sort()

    return deque([item for *_, recs in grupos_todos for item in recs])

def _cola_troquelada(q): 
    if q.empty: return deque()
    q = q.copy()

    if "ManualPriority" not in q.columns: q["ManualPriority"] = 9999
    q["ManualPriority"] = q["ManualPriority"].fillna(9999).astype(int)

    q["_troq_key"] = q.get("CodigoTroquel", "").fillna("").astype(str).str.strip().str.lower()
    grupos = []
    for troq, g in q.groupby("_troq_key", dropna=False):
        min_prio = g["ManualPriority"].min()
        due_min = pd.to_datetime(g["DueDate"], errors="coerce").min() or pd.Timestamp.max
        es_urgente = g["Urgente"].any()
        g_sorted = g.sort_values(["ManualPriority", "Urgente", "DueDate", "CantidadPliegos"], 
                                 ascending=[True, False, True, False])
        grupos.append((min_prio, not es_urgente, due_min, troq, g_sorted.to_dict("records")))
    grupos.sort()
    return deque([item for _, _, _, _, recs in grupos for item in recs])

def _cola_cortadora_bobina(q):
    """
    Agrupa por:
    1. Materia Prima
    2. Medida (Ancho y Largo)
    3. Gramaje (Grs./Nº)
    Dentro del grupo ordena por Urgente y DueDate.
    """
    if q.empty: return deque()
    q = q.copy()
    
    # Ensure ManualPriority exists
    if "ManualPriority" not in q.columns: q["ManualPriority"] = 9999
    q["ManualPriority"] = q["ManualPriority"].fillna(9999).astype(int)

    # Normalización de claves
    q["_mp_key"] = q.get("MateriaPrima", "").fillna("").astype(str).str.strip().str.lower()
    
    # Para medida, combinamos Ancho y Largo en un string o tupla para agrupar
    # Asumimos que PliAnc y PliLar vienen como float o int
    q["_medida_key"] = q.apply(lambda x: f"{float(x.get('PliAnc',0) or 0):.2f}x{float(x.get('PliLar',0) or 0):.2f}", axis=1)
    
    # Gramaje
    q["_gramaje_key"] = q.get("Gramaje", 0).fillna(0).astype(float)

    q["DueDate"] = pd.to_datetime(q["DueDate"], dayfirst=True, errors="coerce")
    
    # Ensure Sort Cols
    

    
    grupos = []
    
    # Agrupamos jerárquicamente
    # GroupBy respeta el orden de las columnas dadas en la lista, creando un MultiIndex
    for (mp, medida, gramaje), g in q.groupby(["_mp_key", "_medida_key", "_gramaje_key"], dropna=False):
        
        # Metadatos del grupo
        min_prio = g["ManualPriority"].min()
        due_min = g["DueDate"].min() or pd.Timestamp.max
        es_urgente = g["Urgente"].any()

        
        # Orden interno del grupo (Para respetar FIFO/Urgencia dentro del mismo setup)
        g_sorted = g.sort_values(["ManualPriority", "Urgente", "DueDate", "CantidadPliegos"], 
                                 ascending=[True, False, True, False])
        
        # Guardamos el grupo. 
        grupos.append((min_prio, not es_urgente, due_min, mp, medida, gramaje, g_sorted.to_dict("records")))
        
    grupos.sort()
    
    return deque([item for _, _, _, _, _, _, recs in grupos for item in recs])

def get_downstream_presence_score(task, colas, maquinas_info, maquina_actual, last_tasks_map=None):
    """
    Calcula un puntaje de prioridad basado en si el CLIENTE de la tarea
    ya tiene otras tareas esperando o procesandose en la siguiente maquina (Impresión).
    Sirve para agrupar tareas del mismo cliente en procesos previos (Guillotina/Corte).
    """
    cliente = str(task.get("Cliente", "")).strip().lower()
    if not cliente: return 0
    
    # Determinar siguiente máquina probable (Impresión)
    # Heurística simple: Si estoy en Guillotina/Corte, lo siguiente es Impresión.
    # Necesitamos saber qué impresión usa esta tarea.
    # Miramos _PEN_ImpresionFlexo o _PEN_ImpresionOffset.
    
    target_queues = []
    
    # Check flags in task
    is_flexo = str(task.get("_PEN_ImpresionFlexo")).strip().lower() in ["sí", "si", "true"]
    is_offset = str(task.get("_PEN_ImpresionOffset")).strip().lower() in ["sí", "si", "true"]
    
    
    # Find printer names in colas keys
    # Asumimos que las colas tienen nombres como "Impresora Flexo 1", "Heidelberg", etc.
    # O usamos la configuración de máquinas.
    
    # Simple search in queues
    for q_name in colas.keys():
        qn = q_name.lower()
        if is_flexo and ("flexo" in qn or "bhs" in qn):
            target_queues.append(q_name)
        if is_offset and ("offset" in qn or "heidelberg" in qn or "kba" in qn):
             target_queues.append(q_name)
             
    score = 0
    for tq in target_queues:
        # Check Waiting Queue
        queue_items = colas.get(tq, [])
        for item in queue_items:
            c_item = str(item.get("Cliente", "")).strip().lower()
            if c_item == cliente:
                score += 1

        
        # Check Currently Running / Last Scheduled Task
        if last_tasks_map:
            t_running = last_tasks_map.get(tq)
            if t_running:
                c_run = str(t_running.get("Cliente", "")).strip().lower()
                if c_run == cliente:
                    score += 2 # Running task is a strong signal!
    
    return score
