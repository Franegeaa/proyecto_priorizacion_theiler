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
    # Lógica Clustering con Ventana de 1 Día
    if q.empty: return deque()
    q = q.copy()
    # Convertir Urgente a booleano real
    q["Urgente"] = q["Urgente"].apply(lambda x: es_si(x))
    
    # Ensure Sort Cols
    if "_is_new_urgent" not in q.columns: q["_is_new_urgent"] = False
    if "_is_soft_locked" not in q.columns: q["_is_soft_locked"] = False
    
    q["_cliente_key"] = q.get("Cliente", "").fillna("").astype(str).str.strip().str.lower()
    q["_color_key"] = (
        q.get("Colores", "").fillna("").astype(str).str.lower()
        .str.replace("-", "", regex=False).str.strip()
    )
    q["DueDate"] = pd.to_datetime(q["DueDate"], dayfirst=True, errors="coerce")
    
    # Separar en Urgent y Normal
    q_urgente = q[q["Urgente"]].copy()
    q_normal = q[~q["Urgente"]].copy()

    def _agrupar_con_ventana(sub_q):
        if sub_q.empty: return []
        
        # 1. Orden inicial estricto por Fecha
        # Usamos un índice temporal para controlar procesados
        sub_q = sub_q.sort_values(by=["_is_new_urgent", "_is_soft_locked", "DueDate", "_cliente_key", "CantidadPliegos"], 
                                  ascending=[False, False, True, True, False])
        lista_items = sub_q.to_dict("records")
        n = len(lista_items)
        processed = [False] * n
        resultado = []
        
        from datetime import timedelta
        WINDOW = timedelta(days=1)

        for i in range(n):
            if processed[i]: continue
            
            # Tomamos el Anchor (el siguiente disponible más urgente/temprano)
            anchor = lista_items[i]
            resultado.append(anchor)
            processed[i] = True
            
            anchor_date = anchor["DueDate"]
            if pd.isna(anchor_date): continue # No podemos hacer comparaciones de ventana sin fecha
            
            anchor_color = anchor.get("_color_key", "")
            
            # Buscar siguientes compatibles dentro de la ventana
            for j in range(i + 1, n):
                if processed[j]: continue
                
                candidate = lista_items[j]
                cand_date = candidate["DueDate"]
                cand_color = candidate.get("_color_key", "")
                
                # Chequeo 1: Mismo Color
                if cand_color != anchor_color: continue
                
                # Chequeo 2: Dentro de Ventana (Anchor Date + 1 Dia >= Candidate Date)
                # Nota: Candidate Date siempre es >= Anchor Date porque ordenamos la lista al inicio.
                # Solo verificamos el límite superior.
                if pd.isna(cand_date):
                     # Si no tiene fecha, ¿lo agrupamos? Asumimos que sí si es el mismo color (tratar como fecha lejana o cercana?)
                     # Mejor no arriesgar: si no tiene fecha, sigue su curso natural (probablemente al final).
                     continue
                
                diff = cand_date - anchor_date
                if diff <= WINDOW:
                    # Agrupar!
                    resultado.append(candidate)
                    processed[j] = True
                    
        return resultado

    sorted_urgente = _agrupar_con_ventana(q_urgente)
    sorted_normal = _agrupar_con_ventana(q_normal)

    return deque(sorted_urgente + sorted_normal)

def _cola_impresora_offset(q):
    if q.empty: return deque()
    q = q.copy()

    # Ensure Sort Cols
    if "_is_new_urgent" not in q.columns: q["_is_new_urgent"] = False
    if "_is_soft_locked" not in q.columns: q["_is_soft_locked"] = False
    
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
            # Prioritize New Urgent inside group?
            # Or group sort order?
            # Groups are sorted later. This is INSIDE group sort? No, "g_sorted" is stored in recs.
            # And sorted later by "grupos_todos.sort()".
            # The tuple is `(not es_urgente, due_min, ...)`
            # We should add new urgency to tuple.
            es_new_urgent = g["_is_new_urgent"].any()
            es_soft_locked = g["_is_soft_locked"].any()
            
            g_sorted = g.sort_values(["_is_new_urgent", "_is_soft_locked", "Urgente", "DueDate", "CantidadPliegos"], 
                                     ascending=[False, False, False, True, False])
            # Prio 0
            # Order: New Urgent (True->0 in tuple logic? No, Python Sort. True > False)
            # We want True FIRST.
            # Tuple Sort: False < True.
            # So `not es_new_urgent` gives False if Urgent -> First.
            grupos_todos.append((not es_new_urgent, not es_soft_locked, not es_urgente, due_min, 0, keys[0], keys[1], g_sorted.to_dict("records")))

        # 3.2 PANTONE -> Agrupar por CLIENTE + COLOR
        for keys, g in q_pantone.groupby(["_cliente_key", "_color_key"], dropna=False):
            due_min = g["DueDate"].min()
            es_urgente = g["Urgente"].apply(es_si).any()
            es_new_urgent = g["_is_new_urgent"].any()
            es_soft_locked = g["_is_soft_locked"].any()
            
            g_sorted = g.sort_values(["_is_new_urgent", "_is_soft_locked", "Urgente", "DueDate", "CantidadPliegos"], 
                                     ascending=[False, False, False, True, False])
            # Prio 0 (Mismo nivel que CMYK, se ordenan entre ellos por Fecha/Cliente)
            grupos_todos.append((not es_new_urgent, not es_soft_locked, not es_urgente, due_min, 0, keys[0], keys[1], g_sorted.to_dict("records")))

    # 4. GRUPO BARNIZADO (Prioridad 1)
    # ------------------------------------------------------------
    if not q_barniz.empty:
        # Agrupar solo por CLIENTE
        for cliente, g in q_barniz.groupby("_cliente_key", dropna=False):
            due_min = g["DueDate"].min()
            es_urgente = g["Urgente"].apply(es_si).any()
            es_new_urgent = g["_is_new_urgent"].any()
            es_soft_locked = g["_is_soft_locked"].any()
            
            g_sorted = g.sort_values(["_is_new_urgent", "_is_soft_locked", "Urgente", "DueDate", "CantidadPliegos"], 
                                     ascending=[False, False, False, True, False])
            # Prio 1 -> Queda DESPUES de impresion si las fechas coinciden
            grupos_todos.append((not es_new_urgent, not es_soft_locked, not es_urgente, due_min, 1, cliente, "barniz", g_sorted.to_dict("records")))

    # 5. ORDENAMIENTO FINAL
    # ------------------------------------------------------------
    grupos_todos.sort()
    
    # # --- PRINT PARA DEPURACION ---
    # print("\n--- COLA DE IMPRESION OFFSET (Primeros 20 grupos) ---")
    # for i, item in enumerate(grupos_todos[:20]):
    #     prio, due, _, c1, c2, recs = item
    #     print(f"Grupo {i}: Prio={prio} Due={due} C1={c1} C2={c2} (Cnt: {len(recs)})")
    #     for r in recs:
    #         print(f"   -> OT: {r.get('OT_id')} | Cli: {r.get('Cliente')} | Troq: {r.get('CodigoTroquel')} | Due: {r.get('DueDate')}")
    # print("------------------------------------------------------\n")

    return deque([item for _, _, _, _, _, _, _, recs in grupos_todos for item in recs])

def _cola_troquelada(q): 
    if q.empty: return deque()
    q = q.copy()
    if "_is_new_urgent" not in q.columns: q["_is_new_urgent"] = False
    if "_is_soft_locked" not in q.columns: q["_is_soft_locked"] = False

    q["_troq_key"] = q.get("CodigoTroquel", "").fillna("").astype(str).str.strip().str.lower()
    grupos = []
    for troq, g in q.groupby("_troq_key", dropna=False):
        due_min = pd.to_datetime(g["DueDate"], errors="coerce").min() or pd.Timestamp.max
        es_urgente = g["Urgente"].any()
        es_new_urgent = g["_is_new_urgent"].any()
        es_soft_locked = g["_is_soft_locked"].any()

        g_sorted = g.sort_values(["_is_new_urgent", "_is_soft_locked", "Urgente", "DueDate", "CantidadPliegos"], 
                                 ascending=[False, False, False, True, False])
        grupos.append((not es_new_urgent, not es_soft_locked, not es_urgente, due_min, troq, g_sorted.to_dict("records")))
    grupos.sort()
    return deque([item for _, _, _, _, _, recs in grupos for item in recs])

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
    
    # Normalización de claves
    q["_mp_key"] = q.get("MateriaPrima", "").fillna("").astype(str).str.strip().str.lower()
    
    # Para medida, combinamos Ancho y Largo en un string o tupla para agrupar
    # Asumimos que PliAnc y PliLar vienen como float o int
    q["_medida_key"] = q.apply(lambda x: f"{float(x.get('PliAnc',0) or 0):.2f}x{float(x.get('PliLar',0) or 0):.2f}", axis=1)
    
    # Gramaje
    q["_gramaje_key"] = q.get("Gramaje", 0).fillna(0).astype(float)

    q["DueDate"] = pd.to_datetime(q["DueDate"], dayfirst=True, errors="coerce")
    
    # Ensure Sort Cols
    if "_is_new_urgent" not in q.columns: q["_is_new_urgent"] = False
    if "_is_soft_locked" not in q.columns: q["_is_soft_locked"] = False
    
    grupos = []
    
    # Agrupamos jerárquicamente
    # GroupBy respeta el orden de las columnas dadas en la lista, creando un MultiIndex
    for (mp, medida, gramaje), g in q.groupby(["_mp_key", "_medida_key", "_gramaje_key"], dropna=False):
        
        # Metadatos del grupo
        due_min = g["DueDate"].min() or pd.Timestamp.max
        es_urgente = g["Urgente"].any()
        es_new_urgent = g["_is_new_urgent"].any()
        es_soft_locked = g["_is_soft_locked"].any()
        
        # Orden interno del grupo (Para respetar FIFO/Urgencia dentro del mismo setup)
        g_sorted = g.sort_values(["_is_new_urgent", "_is_soft_locked", "Urgente", "DueDate", "CantidadPliegos"], 
                                 ascending=[False, False, False, True, False])
        
        # Guardamos el grupo. 
        grupos.append((not es_new_urgent, not es_soft_locked, not es_urgente, due_min, mp, medida, gramaje, g_sorted.to_dict("records")))
        
    grupos.sort()
    
    return deque([item for _, _, _, _, _, _, _, recs in grupos for item in recs])
