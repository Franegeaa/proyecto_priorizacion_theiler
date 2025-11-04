import pandas as pd
from datetime import datetime, timedelta, time
from collections import defaultdict, deque

# Importaciones de tus módulos auxiliares
from modules.config_loader import (
    es_si, horas_por_dia, proximo_dia_habil, construir_calendario
)
from modules.tiempos_y_setup import (
    capacidad_pliegos_h, setup_base_min, setup_menor_min, usa_setup_menor, tiempo_operacion_h
)

# =======================================================
# Helpers de fecha / agenda
# =======================================================

def _reservar_en_agenda(agenda_m, horas_necesarias, cfg):
    """
    Reserva un bloque de 'horas_necesarias' en la agenda de una máquina.
    Maneja el salto a días hábiles siguientes si no hay horas.
    Retorna una lista de tuplas [(inicio, fin)] (puede partirse en varios días).
    """
    fecha = agenda_m["fecha"]
    hora_actual = datetime.combine(fecha, agenda_m["hora"])
    resto = agenda_m["resto_horas"]
    h_dia = horas_por_dia(cfg)

    bloques = []
    h = horas_necesarias
    while h > 1e-9: # Bucle mientras queden horas por planificar
        if resto <= 1e-9: # Si no queda tiempo en el día
            fecha = proximo_dia_habil(fecha + timedelta(days=1), cfg)
            hora_actual = datetime.combine(fecha, time(8, 0)) # Inicia a las 8 AM
            resto = h_dia
        
        usar = min(h, resto) # Asigna el mínimo entre lo necesario y lo disponible
        inicio = hora_actual
        fin = inicio + timedelta(hours=usar)
        bloques.append((inicio, fin))
        
        hora_actual = fin
        resto -= usar
        h -= usar

    agenda_m["fecha"] = hora_actual.date()
    agenda_m["hora"] = hora_actual.time()
    agenda_m["resto_horas"] = resto
    return bloques


# =======================================================
# Procesos pendientes (_PEN_*)
# =======================================================

def _procesos_pendientes_de_orden(orden: pd.Series, orden_std=None):
    """
    Devuelve la lista de procesos pendientes según los flags de la orden,
    usando nombres "hardcodeados" que deben coincidir con el flujo estándar.
    """
    flujo = orden_std or [
        "Guillotina", "Impresión Flexo", "Impresión Offset", "Barnizado",
        "OPP", "Stamping", "Cuño", "Encapado", "Troquelado",
        "Descartonado", "Ventana", "Pegado"
    ]
    
    flujo = [p.strip() for p in flujo] 
    orden_idx = {p: i for i, p in enumerate(flujo)}
    pendientes = []
    
    # Crea la lista de pendientes basado en los flags _PEN_
    # Asegúrate que los nombres aquí coincidan EXACTAMENTE con tu 'flujo_estandar' limpio
    if es_si(orden.get("_PEN_Guillotina")): pendientes.append("Guillotina")
    if es_si(orden.get("_PEN_ImpresionFlexo")): pendientes.append("Impresión Flexo")
    if es_si(orden.get("_PEN_ImpresionOffset")): pendientes.append("Impresión Offset") 
    if es_si(orden.get("_PEN_Barnizado")): pendientes.append("Barnizado")
    if es_si(orden.get("_PEN_OPP")): pendientes.append("OPP")
    # Añade aquí otros procesos si tienes flags para ellos (Stamping, Cuño, Encapado)
    if es_si(orden.get("_PEN_Troquelado")): pendientes.append("Troquelado")
    if es_si(orden.get("_PEN_Descartonado")): pendientes.append("Descartonado")
    if es_si(orden.get("_PEN_Ventana")): pendientes.append("Ventana")
    if es_si(orden.get("_PEN_Pegado")): pendientes.append("Pegado")
    
    pendientes_limpios = [p.strip() for p in pendientes]
    pendientes_limpios = list(set(pendientes_limpios)) # Quitar duplicados
    pendientes_limpios.sort(key=lambda p: orden_idx.get(p, 999)) # Ordena según el flujo

    return pendientes_limpios

# =======================================================
# Selección de máquina (Versión Simple Inicial)
# =======================================================

def elegir_maquina(proceso, orden, cfg, plan_actual=None):
    """
    Versión simple que elige la primera máquina candidata.
    La lógica de balanceo de Troquelado se aplica *después* en programar().
    """
    proc_lower = proceso.lower().strip()
    candidatos = cfg["maquinas"][cfg["maquinas"]["Proceso"].str.lower().str.contains(proc_lower.split()[0])]["Maquina"].tolist()
    if not candidatos:
        return None
    
    # Reglas específicas (pueden simplificarse si se manejan en config)
    if "impresión" in proc_lower:
        mat = str(orden.get("MateriaPrima", "")).lower()
        if "flexo" in proc_lower and ("micro" in mat or "carton" in mat):
            flexos = [m for m in candidatos if "flexo" in m.lower()]
            return flexos[0] if flexos else candidatos[0] # Fallback
        if "offset" in proc_lower and ("cartulin" in mat or "papel" in mat):
            offsets = [m for m in candidatos if "offset" in m.lower()]
            return offsets[0] if offsets else candidatos[0] # Fallback

    if "ventan" in proc_lower:
        vent = [m for m in candidatos if "ventan" in m.lower()]
        return vent[0] if vent else candidatos[0] # Fallback

    if "peg" in proc_lower:
        pegs = [m for m in candidatos if "peg" in m.lower() or "pegad" in m.lower()]
        return pegs[0] if pegs else candidatos[0] # Fallback

    if "descartonad in" in proc_lower:
        descs = [m for m in candidatos if "descartonad" in m.lower()]
        if descs:
            return descs[0]
    
    # Fallback general: Devuelve la primera máquina candidata
    return candidatos[0]


# =======================================================
# Claves de prioridad (Para Agrupación de Colas)
# =======================================================

def _clave_prioridad_maquina(proceso: str, orden: pd.Series):
    """Genera una clave para agrupar tareas y optimizar setups."""
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


# =======================================================
# Expandir tareas
# =======================================================

def _expandir_tareas(df: pd.DataFrame, cfg):
    """Expande OTs en tareas individuales (una fila por proceso pendiente)."""
    tareas = []
    orden_std_limpio = [p.strip() for p in cfg.get("orden_std", [])]

    for idx, row in df.iterrows():
        ot = f"{row['CodigoProducto']}-{row['Subcodigo']}"
        pendientes = _procesos_pendientes_de_orden(row, orden_std_limpio)

        for proceso in pendientes:
            maquina = elegir_maquina(proceso, row, cfg, None) # Asignación inicial simple
            if not maquina: continue

            # Cálculo de pliegos
            cant_prod = float(row.get("CantidadProductos", row.get("CantidadPliegos", 0)) or 0)
            poses = float(row.get("Poses", 1) or 1)
            bocas = float(row.get("BocasTroquel", row.get("Boca1_ddp", 1)) or 1)
            pliegos = cant_prod / poses if proceso.lower().startswith("impres") and poses > 0 else \
                      cant_prod / bocas if proceso.lower().startswith("troquel") and bocas > 0 else \
                      float(row.get("CantidadPliegos", cant_prod))

            tareas.append({
                "idx": idx, "OT_id": ot, "CodigoProducto": row["CodigoProducto"], "Subcodigo": row["Subcodigo"],
                "Cliente": row["Cliente"], "Proceso": proceso, "Maquina": maquina,
                "DueDate": row["FechaEntrega"], "GroupKey": _clave_prioridad_maquina(proceso, row),
                "MateriaPrimaPlanta": row.get("MateriaPrimaPlanta", row.get("MPPlanta")),
                "CodigoTroquel": row.get("CodigoTroquel") or row.get("CodTroTapa") or row.get("CodTroCuerpo") or "",
                "Colores": row.get("Colores", ""), "CantidadPliegos": pliegos, "Bocas": bocas, "Poses": poses,
            })  

    tasks = pd.DataFrame(tareas)
    tasks.drop_duplicates(subset=["OT_id", "Proceso"], inplace=True)
    
    if not tasks.empty:
        tasks["DueDate"] = pd.to_datetime(tasks["DueDate"], dayfirst=True, errors="coerce")
        # Asigna el índice de orden del proceso para usarlo después
        if "orden_std" in cfg:
            orden_map = {p: i for i, p in enumerate(orden_std_limpio, start=1)}
            tasks["_orden_proceso"] = tasks["Proceso"].map(orden_map).fillna(9999)
            tasks.sort_values(["OT_id", "_orden_proceso"], inplace=True)

    return tasks


# =======================================================
# Programador principal (Versión Combinada)
# =======================================================

def programar(df_ordenes: pd.DataFrame, cfg, start=None):
    """
    Planifica respetando dependencias, orden de máquinas,
    balanceo de carga (Troquelado) y optimización de setups.
    """
    if df_ordenes.empty: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    df_ordenes["OT_id"] = df_ordenes["CodigoProducto"].astype(str) + "-" + df_ordenes["Subcodigo"].astype(str)
    agenda = construir_calendario(cfg, start=start)

    # 1. Expande OTs en tareas individuales
    tasks = _expandir_tareas(df_ordenes, cfg)
    if tasks.empty: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # =======================================================
    # 2. ORDEN LÓGICO DE PLANIFICACIÓN (Define el orden del bucle principal)
    # =======================================================
    flujo_estandar = [p.strip() for p in cfg.get("orden_std", [])] # Carga y limpia

    def _orden_proceso(maquina):
        proc_name = cfg["maquinas"].loc[cfg["maquinas"]["Maquina"] == maquina, "Proceso"]
        if proc_name.empty: return 999
        proc = proc_name.iloc[0]
        for i, p in enumerate(flujo_estandar):
            if p.lower() in proc.lower(): return i
        return 999

    maquinas = sorted(cfg["maquinas"]["Maquina"].unique(), key=_orden_proceso)
   
    # =================================================================
    # 3. REASIGNACIÓN TROQUELADO (Balanceo de Carga - de "buena distribucion")
    # =================================================================
    
    troq_cfg = cfg["maquinas"][cfg["maquinas"]["Proceso"].str.lower().eq("troquelado")]
    manuales = [m for m in troq_cfg["Maquina"].tolist() if "manual" in str(m).lower()]
    auto_names = [m for m in troq_cfg["Maquina"].tolist() if "autom" in str(m).lower()]
    auto_name = auto_names[0] if auto_names else None

    if not tasks.empty and manuales: # Solo si hay manuales para balancear
        if "CodigoTroquel" not in tasks.columns: tasks["CodigoTroquel"] = ""
        tasks["CodigoTroquel"] = tasks["CodigoTroquel"].fillna("").astype(str).str.strip().str.lower()
        
        cap = {} # Capacidades
        for m in manuales + ([auto_name] if auto_name else []):
            if m: cap[m] = float(capacidad_pliegos_h("Troquelado", m, cfg) or 5000.0)
        load_h = {m: 0.0 for m in cap.keys()} # Carga en horas

        agenda_m = {}
        for m in cap.keys():
            agenda_m[m] = {
                "fecha": datetime.combine(datetime.today().date(), time(8, 0)),
                "hora": time(8, 0),
                "resto_horas": 8.5
            }

        mask_troq = tasks["Proceso"].eq("Troquelado")
        troq_df = tasks.loc[mask_troq].copy()

        if not troq_df.empty:
            troq_df["_troq_key"] = troq_df["CodigoTroquel"]
            grupos = [] # Agrupa tareas por troquel
            for troq_key, g in troq_df.groupby("_troq_key", dropna=False):
                due_min = pd.to_datetime(g["DueDate"], errors="coerce").min() or pd.Timestamp.max
                total_pliegos = float(g["CantidadPliegos"].fillna(0).sum())
                alguna_grande = bool((g["CantidadPliegos"].fillna(0) > 2000).any())
                grupos.append((due_min, troq_key, g.index.tolist(), total_pliegos, alguna_grande))
            grupos.sort() # Ordena grupos por DueDate

            # Asigna cada GRUPO a la máquina que termine antes
            for _, troq_key, idxs, total_pliegos, alguna_grande in grupos:
                candidatas = manuales + ([auto_name] if auto_name else [])

                if not candidatas: continue

                def criterio_balanceo(m):
                    fecha_disp = agenda_m[m]["fecha"]
                    carga_proj = load_h[m] + (total_pliegos / cap[m])
                    penalizacion_auto = (
                        1.0 + 0.15 * (load_h[m] / (max(load_h.values()) if any(load_h.values()) else 1.0))
                        if "autom" in m.lower() else 1.0
                    )
                    # Combinamos prioridad temporal + carga total ponderada
                    return (fecha_disp.toordinal(), carga_proj * penalizacion_auto)
                
                if alguna_grande and auto_name:
                    m_sel = auto_name
                else:
                    m_sel = min(candidatas, key=criterio_balanceo)
                
                # --- Asignación ---
                tasks.loc[idxs, "Maquina"] = m_sel
                load_h[m_sel] += total_pliegos / cap[m_sel]

                # --- Actualización de agenda --- 
                duracion_h = total_pliegos / cap[m_sel]
                fecha_actual = agenda_m[m_sel]["fecha"]
                nueva_fecha = fecha_actual + timedelta(hours=duracion_h)

                # Si supera la jornada laboral (8.5h -> hasta las 16:30), salta al día siguiente
                if nueva_fecha.hour >= 16:
                    exceso = (nueva_fecha.hour + nueva_fecha.minute / 60) - 16
                    nueva_fecha = datetime.combine(fecha_actual.date() + timedelta(days=1), time(8, 0)) + timedelta(hours=exceso)

                agenda_m[m_sel]["fecha"] = nueva_fecha
                agenda_m[m_sel]["resto_horas"] = max(0, 8.5 - (nueva_fecha.hour - 8))

                # --- DEBUG opcional (podés dejarlo para entender qué hace) ---
                # print(f"\n🟩 TROQUELADO DEBUG → Troquel: {troq_key or 'Sin troquel'}")
                # print(f"   OT(s): {tasks.loc[idxs, 'OT_id'].tolist()}")
                # print(f"   Total pliegos: {total_pliegos}")
                # print(f"   Grande: {alguna_grande}")
                # print(f"   Máquina seleccionada: {m_sel}")
                # print(f"   Carga actual (h): {[f'{k}: {v:.2f}' for k, v in load_h.items()]}")
                # print(f"   Agenda actualizada: {m_sel} disponible desde {agenda_m[m_sel]['fecha']}")
                # # Combinamos prioridad temporal + carga total ponderada
                # return (fecha_disp.toordinal(), carga_proj * penalizacion_auto)
                # m_sel = auto_name if (alguna_grande and auto_name) else min(
                #     candidatas, 
                #     key=lambda m: (load_h[m] + (total_pliegos / cap[m])) * (0.8 if "autom" in str(m).lower() else 1.0)
                # )
                # tasks.loc[idxs, "Maquina"] = m_sel # Sobreescribe la máquina asignada
                # load_h[m_sel] += total_pliegos / cap[m]

    # =====================================================================
    # 3.1 REASIGNACIÓN DESCARTONADO (Balanceo de Carga - NUEVO BLOQUE)
    # =====================================================================
    desc_cfg = cfg["maquinas"][cfg["maquinas"]["Proceso"].str.lower().str.contains("descartonado")]
    desc_maquinas = desc_cfg["Maquina"].tolist()

    if not tasks.empty and len(desc_maquinas) > 1: # Solo si hay más de una descartonadora
        
        # Calcula capacidades (asume un valor fallback si no está definido)
        cap_desc = {} 
        for m in desc_maquinas:
            c = capacidad_pliegos_h("Descartonado", m, cfg) 
            cap_desc[m] = float(c) if c and c > 0 else 5000.0 # Ajusta fallback si es necesario
        
        load_h_desc = {m: 0.0 for m in desc_maquinas} # Carga acumulada en horas

        # Filtra solo tareas de Descartonado
        mask_desc = tasks["Proceso"].eq("Descartonado")
        desc_df = tasks.loc[mask_desc].copy()

        if not desc_df.empty:
            # Ordena las tareas de descartonado por DueDate para priorizar
            desc_df.sort_values(by=["DueDate", "_orden_proceso"], inplace=True)
            
            # Itera por cada tarea y la asigna a la máquina que termine antes
            for idx, tarea in desc_df.iterrows():
                pliegos_tarea = float(tarea.get("CantidadPliegos", 0))
                if pliegos_tarea <= 0: continue

                # Elige la máquina con menor tiempo de finalización proyectado
                m_sel = min(
                    desc_maquinas,
                    key=lambda m: load_h_desc[m] + (pliegos_tarea / cap_desc[m])
                )
                
                # Sobreescribe la máquina en el DataFrame 'tasks' original
                tasks.loc[idx, "Maquina"] = m_sel
                # Acumula la carga en la máquina seleccionada
                load_h_desc[m_sel] += pliegos_tarea / cap_desc[m]

    # =================================================================
    # 4. CONSTRUCCIÓN DE COLAS INTELIGENTES (de "buena distribucion")
    # =================================================================
    def _cola_impresora(q): # Agrupa por DueDate -> Cliente -> Colores
        if q.empty: return deque()
        q = q.copy()
        q["_cliente_key"] = q.get("Cliente", "").fillna("").astype(str).str.strip().str.lower()
        q["_color_key"] = q.get("Colores", "").fillna("").astype(str).str.strip().str.lower()
        grupos = []
        for keys, g in q.groupby(["_cliente_key", "_color_key"], dropna=False):
            due_min = pd.to_datetime(g["DueDate"], errors="coerce").min() or pd.Timestamp.max
            g_sorted = g.sort_values(["DueDate", "CantidadPliegos"], ascending=[True, False])
            grupos.append((due_min, keys[0], keys[1], g_sorted.to_dict("records")))
        grupos.sort()
        return deque([item for _, _, _, recs in grupos for item in recs])

    def _cola_troquelada(q): # Agrupa por DueDate -> Troquel
        if q.empty: return deque()
        q = q.copy()
        q["_troq_key"] = q.get("CodigoTroquel", "").fillna("").astype(str).str.strip().str.lower()
        grupos = []
        for troq, g in q.groupby("_troq_key", dropna=False):
            due_min = pd.to_datetime(g["DueDate"], errors="coerce").min() or pd.Timestamp.max
            g_sorted = g.sort_values(["DueDate", "CantidadPliegos"], ascending=[True, False])
            grupos.append((due_min, troq, g_sorted.to_dict("records")))
        grupos.sort()
        return deque([item for _, _, recs in grupos for item in recs])

    colas = {}
    for m in maquinas:
        q = tasks[tasks["Maquina"] == m].copy()
        m_lower = m.lower()
        if q.empty: colas[m] = deque()
        elif ("manual" in m_lower) or ("autom" in m_lower) or ("troquel" in m_lower): colas[m] = _cola_troquelada(q)
        elif ("offset" in m_lower) or ("flexo" in m_lower) or ("impres" in m_lower): colas[m] = _cola_impresora(q)
        else: # Cola genérica ordenada por DueDate -> Orden Proceso
            q.sort_values(by=["DueDate", "_orden_proceso", "CantidadPliegos"], ascending=[True, True, False], inplace=True)
            colas[m] = deque(q.to_dict("records"))

    # =================================================================
    # 5. LÓGICA DE PLANIFICACIÓN (Bucle y Dependencias de "buen orden")
    # =================================================================
    pendientes_por_ot = defaultdict(set); [pendientes_por_ot[t["OT_id"]].add(t["Proceso"]) for _, t in tasks.iterrows()]
    completado = defaultdict(set); fin_proceso = defaultdict(dict)
    ultimo_en_maquina = {m: None for m in maquinas} # Para setups
    carga_reg, filas = [], []; h_dia = horas_por_dia(cfg)

    def quedan_tareas(): return any(len(q) > 0 for q in colas.values())

    def lista_para_ejecutar(t): # Lógica robusta de dependencias
        proc = t["Proceso"].strip(); ot = t["OT_id"]; orden_std = flujo_estandar
        if proc not in orden_std: return True
        idx = orden_std.index(proc); prev_procs = [p for p in orden_std[:idx] if p in pendientes_por_ot[ot]]
        if not prev_procs: return True
        if not all(p in completado[ot] for p in prev_procs): return False
        
        last_end = max((fin_proceso[ot].get(p) for p in prev_procs if fin_proceso[ot].get(p)), default=None)
        if last_end:
            maq = t["Maquina"]; current_agenda = datetime.combine(agenda[maq]["fecha"], agenda[maq]["hora"])
            if current_agenda < last_end:
                agenda[maq]["fecha"] = last_end.date(); agenda[maq]["hora"] = last_end.time()
                h_used = (last_end - datetime.combine(last_end.date(), time(8, 0))).total_seconds() / 3600.0
                agenda[maq]["resto_horas"] = max(0, h_dia - h_used)
        return True 
    
    #--- Bucle principal de planificación ---
    troq_cfg = cfg["maquinas"][cfg["maquinas"]["Proceso"].str.lower().eq("troquelado")]
    # manuales_troq = [m for m in troq_cfg["Maquina"].tolist() if "manual" in str(m).lower()]
    # auto_names_troq = [m for m in troq_cfg["Maquina"].tolist() if "autom" in str(m).lower()]

    # MAQUINA_CRITICA_TROQ = auto_names_troq[0] if auto_names_troq else None

    # MAQUINAS_CRITICAS = {MAQUINA_CRITICA_TROQ}

    progreso = True
    while quedan_tareas() and progreso:
        progreso = False
        for maquina in maquinas: # Itera en orden de flujo
            if not colas.get(maquina): continue

            tareas_agendadas = True
            while tareas_agendadas: # Vacía la cola de la máquina actual
                tareas_agendadas = False
                if not colas.get(maquina): break
                
                idx_cand = -1 # Simplificado: busca el PRIMERO que esté listo
                for i, t_cand in enumerate(colas[maquina]):
                    mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                    mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                    if mp_ok and lista_para_ejecutar(t_cand):
                        idx_cand = i
                        break
                
                tarea_robada = False

                # #---- Lógica de "robo" de tarea ----
                # if idx_cand == -1 and maquina in MAQUINAS_CRITICAS:
                #     # La automatica esta al pedo, roba la primera tarea troquelada lista de otra maquina
                #     tarea_encontrada = None
                #     fuente_maquina = None
                #     idx_robado = -1
        
                #     for m_manual in manuales_troq:

                #         if not colas.get(m_manual): continue

                #         for i in range(len(colas[m_manual])):
                #             t_cand = colas[m_manual][i]

                #             if t_cand["Proceso"].strip() != "Troquelado": continue
                #             mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                #             mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")

                #             if mp_ok and lista_para_ejecutar(t_cand):
                #                 tarea_encontrada = t_cand
                #                 fuente_maquina = m_manual
                #                 idx_robado = i
                #                 break
                #         if tarea_encontrada: break

                #     if tarea_encontrada:
                #         tarea_para_mover = colas[fuente_maquina][idx_robado]
                #         del colas[fuente_maquina][idx_robado]

                #         colas[maquina].appendleft(tarea_para_mover)
                #         idx_cand = 0
                #         tarea_robada = True
                #----------------------------------

                if idx_cand == -1: break # No hay nada listo en esta máquina

                # Mueve el candidato al frente (si no es el primero)
                if idx_cand > 0: colas[maquina].rotate(-idx_cand) 
                
                t = colas[maquina].popleft()
                orden = df_ordenes.loc[t["idx"]]

                # --- Lógica de Setup (de "buena distribucion") ---
                _, proc_h = tiempo_operacion_h(orden, t["Proceso"], maquina, cfg)
                setup_min = setup_base_min(t["Proceso"], maquina, cfg)
                motivo = "Setup base"

                if not tarea_robada:
                    last_task = ultimo_en_maquina.get(maquina) # Es un dict 't'
                    if last_task:
                        last_orden_data = df_ordenes.loc[last_task["idx"]] # Recupera datos completos
                        if (t["Proceso"] == "Troquelado" and 
                            str(last_task.get("CodigoTroquel", "")).strip().lower() == str(t.get("CodigoTroquel", "")).strip().lower()):
                            setup_min = 0; motivo = "Mismo troquel (sin setup)"
                        elif usa_setup_menor(last_orden_data, orden, t["Proceso"]): # Usa df_ordenes para comparar
                            setup_min = setup_menor_min(t["Proceso"], maquina, cfg); motivo = "Setup menor (cluster)"
                
                    
                total_h = proc_h + setup_min / 60.0
                if pd.isna(total_h) or total_h <= 0: continue    

                # --- Reserva y Registro ---
                bloques = _reservar_en_agenda(agenda[maquina], total_h, cfg)
                if not bloques: colas[maquina].appendleft(t); break 
                inicio, fin = bloques[0][0], bloques[-1][1]

                fin_proceso[t["OT_id"]][t["Proceso"]] = fin
                for b_ini, b_fin in bloques:
                    carga_reg.append({"Fecha": b_ini.date(), "Maquina": maquina, 
                                      "HorasPlanificadas": (b_fin - b_ini).total_seconds() / 3600.0, 
                                      "CapacidadDia": h_dia})

                filas.append({k: t.get(k) for k in ["OT_id", "CodigoProducto", "Subcodigo", "CantidadPliegos", 
                                                    "Bocas", "Poses", "Cliente", "Proceso", "Maquina", "DueDate"]} |
                             {"Setup_min": round(setup_min, 2), "Proceso_h": round(proc_h, 3), 
                              "Inicio": inicio, "Fin": fin, "Motivo": motivo})

                completado[t["OT_id"]].add(t["Proceso"])
                ultimo_en_maquina[maquina] = t # Guarda la tarea actual (dict)
                progreso = True; tareas_agendadas = True

                # if tarea_robada:
                #     if ultimo_en_maquina.get(fuente_maquina) == t:
                #         ultimo_en_maquina[fuente_maquina] = None
                #         pass
    
    # =================================================================
    # 6. SALIDAS (Combinadas y limpias)
    # =================================================================

    schedule = pd.DataFrame(filas)
    if not schedule.empty:
        schedule["DueDate"] = pd.to_datetime(schedule["DueDate"]) # Asegura tipo
        schedule.sort_values(["OT_id", "Inicio"], inplace=True, ignore_index=True)

    carga_md = pd.DataFrame(carga_reg)
    if not carga_md.empty:
        carga_md = carga_md.groupby(["Fecha", "Maquina", "CapacidadDia"], as_index=False)["HorasPlanificadas"].sum()
        carga_md["HorasExtra"] = (carga_md["HorasPlanificadas"] - carga_md["CapacidadDia"]).clip(lower=0).round(2)

    resumen_ot = pd.DataFrame()
    if not schedule.empty:
        resumen_ot = (
            schedule.groupby("OT_id").agg(
                Cliente=('Cliente', 'first'),
                Fin_OT=('Fin', 'max'),
                DueDate=('DueDate', 'max')
            )
            .reset_index()
        )
        due_date_deadline = pd.to_datetime(resumen_ot["DueDate"].dt.date) + timedelta(hours=18)
        resumen_ot["Atraso_h"] = ((resumen_ot["Fin_OT"] - due_date_deadline).dt.total_seconds() / 3600.0).clip(lower=0).fillna(0.0).round(2) # clip(lower=0) asegura que no haya atrasos negativos
        resumen_ot["EnRiesgo"] = resumen_ot["Atraso_h"] > 0
        schedule = schedule.merge(resumen_ot[["OT_id", "Atraso_h"]], on="OT_id", how="left")
    else:
        resumen_ot = pd.DataFrame(columns=["OT_id", "Fin_OT", "DueDate", "Atraso_h", "EnRiesgo"])

    detalle_maquina = pd.DataFrame()
    if not schedule.empty:
        detalle_maquina = (
            schedule.sort_values(["Maquina", "Inicio"])
            .groupby("Maquina")[["OT_id", "Proceso", "Inicio", "Fin", "CodigoProducto", "DueDate"]]
            .apply(lambda x: x.reset_index(drop=True))
            .reset_index(level=0)
        )

    return schedule, carga_md, resumen_ot, detalle_maquina