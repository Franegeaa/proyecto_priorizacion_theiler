import pandas as pd
from datetime import datetime, timedelta, time
from collections import defaultdict, deque

# Importaciones de tus módulos auxiliares
from modules.config_loader import (
    es_si, horas_por_dia, proximo_dia_habil, construir_calendario, es_dia_habil
)
from modules.tiempos_y_setup import (
    capacidad_pliegos_h, setup_base_min, setup_menor_min, usa_setup_menor, tiempo_operacion_h
)

# =======================================================
# (Las funciones _reservar_en_agenda, _procesos_pendientes_de_orden, 
# elegir_maquina, y _clave_prioridad_maquina permanecen igual)
# =======================================================

def _reservar_en_agenda(agenda_m, horas_necesarias, cfg):
    """
    Reserva 'horas_necesarias' en la agenda de una máquina,
    respetando paros programados (downtimes) y feriados.
    Si un bloque se superpone con un paro, lo corta antes del paro.
    """
    fecha = agenda_m["fecha"]
    hora_actual = datetime.combine(fecha, agenda_m["hora"])
    resto = agenda_m["resto_horas"]
    h_dia = horas_por_dia(cfg)

    bloques = []
    h = horas_necesarias

    nombre_maquina = (
        agenda_m.get("nombre")
        or agenda_m.get("Maquina")
        or agenda_m.get("maquina")
    )

    # Obtener todos los paros relevantes de la máquina
    paros_maquina = [
        (p["start"], p["end"])
        for p in cfg.get("downtimes", [])
        if str(p.get("maquina") or p.get("Maquina", ""))
            .strip()
            .lower()
            == str(nombre_maquina).strip().lower()
    ]
    paros_maquina.sort(key=lambda x: x[0])

    # PAUSA FIJA DE ALMUERZO (13:30 → 14:00)
    fecha_actual = fecha  # fecha del día que estamos procesando
    almuerzo_inicio = datetime.combine(fecha_actual, time(13, 30))
    almuerzo_fin = datetime.combine(fecha_actual, time(14, 0))

    paros_maquina.append((almuerzo_inicio, almuerzo_fin))
    paros_maquina.sort(key=lambda x: x[0])

    while h > 1e-9:

        # Si no queda resto de día → avanzar al siguiente día hábil
        if resto <= 1e-9:
            fecha = proximo_dia_habil(fecha + timedelta(days=1), cfg)
            hora_actual = datetime.combine(fecha, time(7, 0))
            resto = h_dia
            continue

        # Si estamos dentro de un paro → avanzar al final del paro
        dentro_paro = False
        for inicio, fin in paros_maquina:
            if inicio <= hora_actual < fin:
                hora_actual = fin
                dentro_paro = True
                break

        if dentro_paro:
            continue

        fin_turno = datetime.combine(fecha, time(16, 0))
        limite_fin_dia = min(
            fin_turno,
            hora_actual + timedelta(hours=h, minutes=1)
        )

        # Buscar el próximo paro que interfiera
        proximo_paro = None
        for inicio, fin in paros_maquina:
            if inicio >= hora_actual and inicio < limite_fin_dia:
                proximo_paro = inicio
                break

        # Determinar fin del bloque a reservar
        if proximo_paro:
            fin_bloque = min(
                proximo_paro,
                hora_actual + timedelta(hours=min(h, resto))
            )
        else:
            fin_bloque = min(
                limite_fin_dia,
                hora_actual + timedelta(hours=min(h, resto))
            )

        # Duración efectiva del bloque
        duracion_h = (fin_bloque - hora_actual).total_seconds() / 3600.0

        if duracion_h <= 0:
            # No hay tiempo útil → saltar al siguiente día
            fecha = proximo_dia_habil(fecha + timedelta(days=1), cfg)
            hora_actual = datetime.combine(fecha, time(7, 0))
            resto = h_dia
            continue

        # Registrar bloque válido
        bloques.append((hora_actual, fin_bloque))

        # Actualizar contadores
        hora_actual = fin_bloque
        resto -= duracion_h
        h -= duracion_h

        # Si terminamos justo en el inicio de un paro → saltarlo
        for inicio, fin in paros_maquina:
            if abs((hora_actual - inicio).total_seconds()) < 1e-6:
                hora_actual = fin
                break

        # Fin del turno → siguiente día hábil
        if hora_actual.time() >= time(16, 0):
            fecha = proximo_dia_habil(
                hora_actual.date() + timedelta(days=1), cfg
            )
            hora_actual = datetime.combine(fecha, time(7, 0))
            resto = h_dia

    # Guardar estado final de agenda
    agenda_m["fecha"] = hora_actual.date()
    agenda_m["hora"] = hora_actual.time()
    agenda_m["resto_horas"] = resto
    agenda_m["nombre"] = nombre_maquina

    return bloques

def _procesos_pendientes_de_orden(orden: pd.Series, orden_std=None):
    flujo = orden_std or [
        "Guillotina", "Impresión Flexo", "Impresión Offset", "Barnizado",
        "OPP", "Stamping", "Cuño", "Encapado", "Troquelado",
        "Descartonado", "Ventana", "Pegado"
    ]
    flujo = [p.strip() for p in flujo] 
    orden_idx = {p: i for i, p in enumerate(flujo)}
    pendientes = []
    
    if es_si(orden.get("_PEN_Guillotina")): pendientes.append("Guillotina")
    if es_si(orden.get("_PEN_ImpresionFlexo")): pendientes.append("Impresión Flexo")
    if es_si(orden.get("_PEN_ImpresionOffset")) and not es_si(orden.get("PeliculaArt")): pendientes.append("Impresión Offset") 
    if es_si(orden.get("_PEN_Barnizado"))and not es_si(orden.get("PeliculaArt")): pendientes.append("Barnizado")
    if es_si(orden.get("_PEN_OPP")): pendientes.append("OPP")
    if es_si(orden.get("_PEN_Troquelado")) and not es_si(orden.get("TroquelArt")) and not es_si(orden.get("PeliculaArt")): pendientes.append("Troquelado")
    if es_si(orden.get("_PEN_Descartonado"))and not es_si(orden.get("PeliculaArt")) and not es_si(orden.get("TroquelArt")): pendientes.append("Descartonado")
    if es_si(orden.get("_PEN_Ventana"))and not es_si(orden.get("PeliculaArt")) and not es_si(orden.get("TroquelArt")): pendientes.append("Ventana")
    if es_si(orden.get("_PEN_Pegado"))and not es_si(orden.get("PeliculaArt")) and not es_si(orden.get("TroquelArt")): pendientes.append("Pegado")
    
    pendientes_limpios = [p.strip() for p in pendientes]
    pendientes_limpios = list(dict.fromkeys(pendientes))
    pendientes_limpios.sort(key=lambda p: orden_idx.get(p, 999))
    return pendientes_limpios

def elegir_maquina(proceso, orden, cfg, plan_actual=None):
    proc_lower = proceso.lower().strip()
    candidatos = cfg["maquinas"][cfg["maquinas"]["Proceso"].str.lower().str.contains(proc_lower.split()[0])]["Maquina"].tolist()
    if not candidatos:
        return None
    if "impresión" in proc_lower:
        mat = str(orden.get("MateriaPrima", "")).lower()
        if "flexo" in proc_lower and ("micro" in mat or "carton" in mat):
            flexos = [m for m in candidatos if "flexo" in m.lower()]
            return flexos[0] if flexos else candidatos[0]
        if "offset" in proc_lower and ("cartulin" in mat or "papel" in mat):
            offsets = [m for m in candidatos if "offset" in m.lower()]
            return offsets[0] if offsets else candidatos[0]
    if "ventan" in proc_lower:
        vent = [m for m in candidatos if "ventan" in m.lower()]
        return vent[0] if vent else candidatos[0]
    if "peg" in proc_lower:
        pegs = [m for m in candidatos if "peg" in m.lower() or "pegad" in m.lower()]
        return pegs[0] if pegs else candidatos[0]
    if "descartonad in" in proc_lower:
        descs = [m for m in candidatos if "descartonad" in m.lower()]
        if descs:
            return descs[0]
    return candidatos[0]

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

# =======================================================
# Expandir tareas (CON LA CORRECCIÓN DE "CantidadPliegos")
# =======================================================

def _expandir_tareas(df: pd.DataFrame, cfg):
    """Expande OTs en tareas individuales (una fila por proceso pendiente)."""
    tareas = []
    orden_std_limpio = [p.strip() for p in cfg.get("orden_std", [])]



    for idx, row in df.iterrows():
        ot = f"{row['CodigoProducto']}-{row['Subcodigo']}"
        pendientes = _procesos_pendientes_de_orden(row, orden_std_limpio)

        if not pendientes:
            continue

        for proceso in pendientes:
            maquina = elegir_maquina(proceso, row, cfg, None) # Asignación inicial simple

            # Cálculo de pliegos
            cant_prod = float(row.get("CantidadProductos", row.get("CantidadPliegos", 0)) or 0)
            poses = float(row.get("Poses", 1) or 1)
            bocas = float(row.get("BocasTroquel", row.get("Boca1_ddp", 1)) or 1)
            if proceso.lower().startswith("impres")or proceso.lower().startswith("barniz"):
                # Impresión: usa poses
                pliegos = cant_prod / poses if poses > 0 else cant_prod

            elif "troquel" in proceso.lower():
                # TROQUELADO: SIEMPRE dividir cantidad por bocas
                pliegos = cant_prod / bocas if bocas > 0 else cant_prod
            else:
                # Procesos restantes
                pliegos = float(row.get("CantidadPliegos", cant_prod))

            tareas.append({
                "idx": idx, "OT_id": ot, "CodigoProducto": row["CodigoProducto"], "Subcodigo": row["Subcodigo"],
                "Cliente": row["Cliente"], "Cliente-articulo": row.get("Cliente-articulo", ""),
                "Proceso": proceso, "Maquina": maquina,
                "DueDate": row["FechaEntrega"], "GroupKey": _clave_prioridad_maquina(proceso, row),
                "MateriaPrimaPlanta": row.get("MateriaPrimaPlanta", row.get("MPPlanta")),
                "CodigoTroquel": row.get("CodigoTroquel") or row.get("CodTroTapa") or row.get("CodTroCuerpo") or "",
                "Colores": row.get("Colores", ""), 
                "CantidadPliegos": pliegos,
                "CantidadPliegosNetos": row.get("CantidadPliegos"), 
                "Bocas": bocas, "Poses": poses,
                "TroquelArt": row.get("TroquelArt", ""),
                "PeliculaArt": row.get("PeliculaArt", ""),
                "PliAnc": row.get("PliAnc", 0),
                "PliLar": row.get("PliLar", 0),
            })  

    tasks = pd.DataFrame(tareas)
    tasks.drop_duplicates(subset=["OT_id", "Proceso"], inplace=True)
    
    if not tasks.empty:
        tasks["DueDate"] = pd.to_datetime(tasks["DueDate"], dayfirst=True, errors="coerce")
        if "orden_std" in cfg:
            orden_map = {p: i for i, p in enumerate(orden_std_limpio, start=1)}
            tasks["_orden_proceso"] = tasks["Proceso"].map(orden_map).fillna(9999)
            tasks.sort_values(["OT_id", "_orden_proceso"], inplace=True)

    return tasks


# =======================================================
# Programador principal (Versión Combinada)
# =======================================================

def programar(df_ordenes: pd.DataFrame, cfg, start=None, start_time=None):
    """
    Planifica respetando dependencias, orden de máquinas,
    balanceo de carga (Troquelado) y optimización de setups.
    """
    if df_ordenes.empty: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    df_ordenes["OT_id"] = df_ordenes["CodigoProducto"].astype(str) + "-" + df_ordenes["Subcodigo"].astype(str)
    agenda = construir_calendario(cfg, start=start, start_time=start_time)

    # 1. Expande OTs en tareas individuales
    tasks = _expandir_tareas(df_ordenes, cfg)
    if tasks.empty: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # =======================================================
    # 2. ORDEN LÓGICO DE PLANIFICACIÓN
    # =======================================================

    flujo_estandar = [p.strip() for p in cfg.get("orden_std", [])] 

    ### ---------------------------------------------------------------- ###
    ### MODIFICADO: _orden_proceso ahora prioriza Manuales
    ### ---------------------------------------------------------------- ###

    def _orden_proceso(maquina):
        proc_name = cfg["maquinas"].loc[cfg["maquinas"]["Maquina"] == maquina, "Proceso"]
        if proc_name.empty: return (999, 0) # Devuelve tupla
        proc = proc_name.iloc[0]
        
        base_order = 999
        for i, p in enumerate(flujo_estandar):
            if p.lower() in proc.lower(): 
                base_order = i
                break
        
        # Desempate: Manuales (0) van ANTES que Automáticas (1)
        if "troquel" in proc.lower():
            if "autom" in maquina.lower():
                return (base_order, 1) # Automática corre DESPUÉS
            else:
                return (base_order, 0) # Manuales corren ANTES
        
        return (base_order, 0) # Resto de las máquinas
    ### ---------------------------------------------------------------- ###

    maquinas = sorted(cfg["maquinas"]["Maquina"].unique(), key=_orden_proceso)
    
    # =================================================================
    # 3. REASIGNACIÓN TROQUELADO
    # =================================================================
    
    troq_cfg = cfg["maquinas"][cfg["maquinas"]["Proceso"].str.lower().eq("troquelado")]
    manuales = [m for m in troq_cfg["Maquina"].tolist() if "manual" in str(m).lower()]
    auto_names = [m for m in troq_cfg["Maquina"].tolist() if "autom" in str(m).lower()]
    auto_name = auto_names[0] if auto_names else None

    if not tasks.empty and manuales: 
        if "CodigoTroquel" not in tasks.columns: tasks["CodigoTroquel"] = ""
        tasks["CodigoTroquel"] = tasks["CodigoTroquel"].fillna("").astype(str).str.strip().str.lower()
        
        cap = {} 
        for m in manuales + ([auto_name] if auto_name else []):
            if m: cap[m] = float(capacidad_pliegos_h("Troquelado", m, cfg) or 2500.0)
        load_h = {m: 0.0 for m in cap.keys()} 

        agenda_m = {}
        # --- MODIFICADO: La agenda simulada debe empezar en la fecha/hora real ---
        # Usamos la agenda "General" que creó construir_calendario
        fecha_inicio_real = agenda["General"]["fecha"]
        hora_inicio_real = agenda["General"]["hora"]
        resto_inicio_real = agenda["General"]["resto_horas"]
        
        for m in cap.keys():
            agenda_m[m] = {
                "fecha": agenda[m]["fecha"],
                "hora": agenda[m]["hora"],
                "resto_horas": agenda[m]["resto_horas"]
            }

        # --- FIN MODIFICADO ---

        mask_troq = tasks["Proceso"].eq("Troquelado")
        troq_df = tasks.loc[mask_troq].copy()

        if not troq_df.empty:
            troq_df["_troq_key"] = troq_df["CodigoTroquel"]
            troq_df["CantidadPliegos"] = pd.to_numeric(troq_df["CantidadPliegos"], errors='coerce').fillna(0)
            grupos = [] 
            for troq_key, g in troq_df.groupby("_troq_key", dropna=False):
                due_min = pd.to_datetime(g["DueDate"], errors="coerce").min() or pd.Timestamp.max
                total_pliegos = float(g["CantidadPliegos"].fillna(0).sum())

                alguna_grande = bool((g["CantidadPliegos"] > 2500).any())
                tamano_grande = bool((g["PliAnc"].fillna(0) > 100).any()) or bool((g["PliLar"].fillna(0) > 140).any())

                grupos.append((due_min, troq_key, g.index.tolist(), total_pliegos, alguna_grande or tamano_grande))

            grupos.sort() 

            # (Ajusta 100 y 140 a tus límites reales de las máquinas manuales)
            
            for _, troq_key, idxs, total_pliegos, requiere_auto in grupos: # El último valor ya no lo usamos igual
                candidatas = manuales + ([auto_name] if auto_name else [])

                if requiere_auto and auto_name:
                # Si es grande, la ÚNICA candidata es la automática.
                # Las manuales ni siquiera entran al concurso.
                    candidatas = [auto_name]
                else:
                    # Si es chica, compiten todas (Manuales + Auto)
                    candidatas = manuales + ([auto_name] if auto_name else [])

                if not candidatas: continue

                def criterio_balanceo(m):
                    ag = agenda_m[m]
                    return (ag["fecha"], ag["hora"], load_h[m])
                # ... (definición de criterio_balanceo se mantiene igual) ...

                # 2. CAMBIO: Lógica de selección
                m_sel = min(candidatas, key=criterio_balanceo)

            # for _, troq_key, idxs, total_pliegos, alguna_grande in grupos:
            #     candidatas = manuales + ([auto_name] if auto_name else [])

            #     if not candidatas: continue

            #     # def criterio_balanceo(m):
            #     #     fecha_disp = agenda_m[m]["fecha"] 
            #     #     carga_proj = load_h[m] + (total_pliegos / cap[m])
            #     #     penalizacion_auto = (
            #     #         1.0 + 0.15 * (load_h[m] / (max(load_h.values()) if any(load_h.values()) else 1.0))
            #     #         if "autom" in m.lower() else 1.0
            #     #     )
            #     #     return (fecha_disp.toordinal(), carga_proj * penalizacion_auto)

                
     
            #     if alguna_grande and auto_name:
            #         m_sel = auto_name
            #     else:
            #         m_sel = min(candidatas, key=criterio_balanceo)
                
            #     print(">> Máquina elegida:", m_sel)

                # print("\n----- REASIGNACIÓN TROQUELADO -----")
                # print("Troquel:", troq_key)
                # print("Pliegos totales:", total_pliegos)
                # print("Candidatas:", candidatas)
                # print("Cargas actuales:", load_h)
                # print("Capacidades:", cap)
                # print("Alguna grande:", alguna_grande)
                # print("Máquina elegida:", m_sel)
                # print("Agenda simulada antes:", agenda_m[m_sel])
                
                tasks.loc[idxs, "Maquina"] = m_sel
                load_h[m_sel] += total_pliegos / cap[m_sel]

                duracion_h = total_pliegos / cap[m_sel]
                
                # --- MODIFICADO: Usamos _reservar_en_agenda para simular el tiempo ---
                # Esta función SÍ respeta los feriados de config_loader
                _reservar_en_agenda(agenda_m[m_sel], duracion_h, cfg)
                # agenda_m[m_sel] se actualiza por referencia
                # --- FIN MODIFICADO ---

    # =====================================================================
    # 3.1 REASIGNACIÓN DESCARTONADO
    # =====================================================================

    desc_cfg = cfg["maquinas"][cfg["maquinas"]["Proceso"].str.lower().str.contains("descartonado")]
    desc_maquinas = desc_cfg["Maquina"].tolist()

    if not tasks.empty and len(desc_maquinas) > 1:
        cap_desc = {} 
        for m in desc_maquinas:
            c = capacidad_pliegos_h("Descartonado", m, cfg) 
            cap_desc[m] = float(c) if c and c > 0 else 5000.0
        
        # --- NUEVO: Creamos una agenda simulada para Descartonado ---
        agenda_m_desc = {}
        fecha_inicio_real = agenda["General"]["fecha"]
        hora_inicio_real = agenda["General"]["hora"]
        resto_inicio_real = agenda["General"]["resto_horas"]
        
        for m in desc_maquinas:
            agenda_m_desc[m] = {
                "fecha": fecha_inicio_real,
                "hora": hora_inicio_real,
                "resto_horas": resto_inicio_real
            }
        # --- FIN NUEVO ---

        mask_desc = tasks["Proceso"].eq("Descartonado")
        desc_df = tasks.loc[mask_desc].copy()

        if not desc_df.empty:
            desc_df.sort_values(by=["DueDate", "_orden_proceso"], inplace=True)
            
            for idx, tarea in desc_df.iterrows():
                pliegos_tarea = float(tarea.get("CantidadPliegos", 0)) 
                if pliegos_tarea <= 0: continue

                # --- MODIFICADO: Elige por fecha de fin, no por carga simple ---
                m_sel = min(
                    desc_maquinas,
                    key=lambda m: agenda_m_desc[m]["fecha"]
                )
                
                tasks.loc[idx, "Maquina"] = m_sel
                
                # --- MODIFICADO: Usamos _reservar_en_agenda para simular el tiempo ---
                duracion_h = pliegos_tarea / cap_desc[m_sel]
                _reservar_en_agenda(agenda_m_desc[m_sel], duracion_h, cfg)
                # --- FIN MODIFICADO ---

    # =================================================================
    # 4. CONSTRUCCIÓN DE COLAS INTELIGENTES
    # =================================================================

    def _cola_impresora_flexo(q): 
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
    
    def _cola_impresora_offset(q): # NUEVA LÓGICA (para Offset)
        if q.empty: return deque()
        q = q.copy()

        # 1. Añadir claves de agrupación
        q["_cliente_key"] = q.get("Cliente", "").fillna("").astype(str).str.strip().str.lower()
        q["_color_key"] = q.get("Colores", "").fillna("").astype(str).str.strip().str.lower()
        q["_troq_key"] = q.get("CodigoTroquel", "").fillna("").astype(str).str.strip().str.lower()

        # 2. Dividir: Tareas sin pantone vs. con pantone
        # Asumimos que "pantone" o "pms" identifica un pantone.
        colores_upper = q["_color_key"].str.upper()
        mask_con_pantone = colores_upper.str.contains(r'[^CMYK\-]', na=False)
        
        q_sin_pantone = q[~mask_con_pantone]
        q_con_pantone = q[mask_con_pantone]

        grupos_todos = []

        # 3. Procesar SIN PANTONE (Prioridad: Marca -> Troquel)
        if not q_sin_pantone.empty:
            for keys, g in q_sin_pantone.groupby(["_cliente_key", "_troq_key"], dropna=False):
                due_min = pd.to_datetime(g["DueDate"], errors="coerce").min() or pd.Timestamp.max
                g_sorted = g.sort_values(["DueDate", "CantidadPliegos"], ascending=[True, False])
                # Añadimos clave de desempate (0)
                grupos_todos.append((due_min, 0, keys[0], keys[1], g_sorted.to_dict("records")))

        # 4. Procesar CON PANTONE (Prioridad: Marca -> Colores)
        if not q_con_pantone.empty:
            for keys, g in q_con_pantone.groupby(["_cliente_key", "_color_key"], dropna=False):
                due_min = pd.to_datetime(g["DueDate"], errors="coerce").min() or pd.Timestamp.max
                g_sorted = g.sort_values(["DueDate", "CantidadPliegos"], ascending=[True, False])
                # Añadimos clave de desempate (1)
                grupos_todos.append((due_min, 1, keys[0], keys[1], g_sorted.to_dict("records")))
        
        # 5. Ordenar todos los grupos juntos por DueDate
        grupos_todos.sort() 

        # 6. Crear la cola final
        return deque([item for _, _, _, _, recs in grupos_todos for item in recs])

    def _cola_troquelada(q): 
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
    buffer_espera = {m: None for m in maquinas}
    for m in maquinas:
        q = tasks[tasks["Maquina"] == m].copy()
        m_lower = m.lower()

        if q.empty: colas[m] = deque()
        elif ("manual" in m_lower) or ("autom" in m_lower) or ("troquel" in m_lower): colas[m] = _cola_troquelada(q)
        elif "offset" in m_lower:
            colas[m] = _cola_impresora_offset(q) # Nueva función para Offset
        elif ("flexo" in m_lower) or ("impres" in m_lower): # 'impres' genérico usa la de flexo
            colas[m] = _cola_impresora_flexo(q) # Antigua función para Flexo
        else: 
            q.sort_values(by=["DueDate", "_orden_proceso", "CantidadPliegos"], ascending=[True, True, False], inplace=True)
            colas[m] = deque(q.to_dict("records"))

    # =================================================================
    # 5. LÓGICA DE PLANIFICACIÓN
    # =================================================================
    
    pendientes_por_ot = defaultdict(set); [pendientes_por_ot[t["OT_id"]].add(t["Proceso"]) for _, t in tasks.iterrows()]
    completado = defaultdict(set); fin_proceso = defaultdict(dict)
    ultimo_en_maquina = {m: None for m in maquinas} 
    carga_reg, filas = [], []; h_dia = horas_por_dia(cfg)

    def quedan_tareas(): return any(len(q) > 0 for q in colas.values())

    def lista_para_ejecutar(t): 
        proc = t["Proceso"].strip(); ot = t["OT_id"]; orden_std = flujo_estandar
        if proc not in orden_std: return True
        idx = orden_std.index(proc); prev_procs = [p for p in orden_std[:idx] if p in pendientes_por_ot[ot]]
        if not prev_procs: return True
        if not all(p in completado[ot] for p in prev_procs): return False
        # if proc == "Troquelado":
 
        last_end = max((fin_proceso[ot].get(p) for p in prev_procs if fin_proceso[ot].get(p)), default=None)
        if last_end:
            maq = t["Maquina"]; current_agenda = datetime.combine(agenda[maq]["fecha"], agenda[maq]["hora"])
            if current_agenda < last_end:
                
                # --- MODIFICADO: Salto de tiempo debe respetar feriados ---
                fecha_destino = last_end.date()
                hora_destino = last_end.time()

                # Si el proceso anterior terminó en un día no hábil...
                if not es_dia_habil(fecha_destino, cfg):
                    # ...saltamos al próximo día hábil...
                    fecha_destino = proximo_dia_habil(fecha_destino - timedelta(days=1), cfg) # -1 para que la lógica de 'proximo' incluya 'hoy'
                    # ...y empezamos a las 8 AM.
                    hora_destino = time(8, 0) 
                
                agenda[maq]["fecha"] = fecha_destino
                agenda[maq]["hora"] = hora_destino
                
                h_usadas = (hora_destino.hour - 8) + (hora_destino.minute / 60.0)
                agenda[maq]["resto_horas"] = max(0, h_dia - h_usadas)
                # --- FIN MODIFICADO ---

        return True
    
    #--- Bucle principal de planificación ---
    
    def _prioridad_dinamica(m):
    # Si es automática → darle prioridad cuando está libre
        if "autom" in m.lower():
            fecha = agenda[m]["fecha"]
            hora = agenda[m]["hora"]
            return (0, fecha, hora)   # prioridad alta

        # Manuales después
        fecha = agenda[m]["fecha"]
        hora = agenda[m]["hora"]
        return (1, fecha, hora)

    progreso = True
    while quedan_tareas() and progreso:
        progreso = False
        # (Ahora 'maquinas' está ordenada con Manuales primero)
        for maquina in sorted(maquinas, key=_prioridad_dinamica):
            if not colas.get(maquina): continue
            
            hora_actual_maquina_dt = datetime.combine(agenda[maquina]["fecha"], agenda[maquina]["hora"])

            tareas_agendadas = True
            while tareas_agendadas: 
                tareas_agendadas = False
                if not colas.get(maquina): break
                
                idx_cand = -1 
                for i, t_cand in enumerate(colas[maquina]):
                    mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                    mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                    
                    # if t_cand["Proceso"].strip() == "Troquelado":
                    #     if str(t_cand["TroquelArt"]).strip().lower() in ("verdadero", "1", "si", "true", ""):
                    #         break
                        
                    # elif t_cand["Proceso"].strip() == "Impresion Offset":
                    #     if str(t_cand["PeliculaArt"]).strip().lower() in ("verdadero", "1", "si", "true", ""):
                    #         break

                    if mp_ok and lista_para_ejecutar(t_cand):
                        idx_cand = i
                        break
                
                tarea_robada = False
                
                # ==========================================================
                # --- BLOQUE DE ROBO "ROBIN HOOD" (TOTALMENTE CONECTADO) ---
                # ==========================================================

                if idx_cand == -1:
                    tarea_encontrada = None
                    fuente_maquina = None
                    idx_robado = -1

                    # -------------------------------------------------------
                    # CASO A: La Automática tiene hambre (Roba a Manuales)
                    # -------------------------------------------------------
                    if maquina in auto_names:
                        for m_manual in manuales:
                            if not colas.get(m_manual): continue
                            
                            for i, t_cand in enumerate(colas[m_manual]):
                                if t_cand["Proceso"].strip() != "Troquelado": continue
                                
                                # Validaciones estándar (MP, Dependencias)
                                mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                                mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                                if not mp_ok: continue
                                
                                if lista_para_ejecutar(t_cand):
                                    tarea_encontrada = t_cand
                                    fuente_maquina = m_manual
                                    idx_robado = i
                                    break
                            if tarea_encontrada: break

                    # -------------------------------------------------------
                    # SI SOY UNA MÁQUINA MANUAL (Manual 1, 2 o 3)
                    # -------------------------------------------------------
                    elif any(m in maquina for m in manuales):
                        
                        # --- CASO B: Intento robarle a la JEFA (Automática) ---
                        # Prioridad 1: Descongestionar la automática de tareas chicas
                        if auto_name and colas.get(auto_name):
                            for i, t_cand in enumerate(colas[auto_name]):
                                if t_cand["Proceso"].strip() != "Troquelado": continue

                                # REGLA DE ORO: > 2500 SE QUEDA EN AUTOMÁTICA
                                cant = float(t_cand.get("CantidadPliegos", 0) or 0)
                                if cant > 2500: continue 

                                # Validaciones Físicas y MP
                                anc = float(t_cand.get("PliAnc", 0) or 0)
                                lar = float(t_cand.get("PliLar", 0) or 0)
                                if anc > 100 or lar > 140: continue # Ajustar a tus medidas
                                
                                mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                                mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                                if not mp_ok: continue

                                if lista_para_ejecutar(t_cand):
                                    tarea_encontrada = t_cand
                                    fuente_maquina = auto_name
                                    idx_robado = i
                                    break
                        
                        # --- CASO C: (NUEVO) Intento robarle a mis VECINAS (Otras Manuales) ---
                        # Prioridad 2: Balancear carga entre manuales
                        
                        if not tarea_encontrada:
                            otras_manuales = [m for m in manuales if m != maquina] # Lista de vecinas
                            
                            for vecina in otras_manuales:
                                if not colas.get(vecina): continue
                                
                                for i, t_cand in enumerate(colas[vecina]):
                                    if t_cand["Proceso"].strip() != "Troquelado": continue
                                    
                                    # Validaciones Físicas (Por si las manuales tienen tamaños distintos)
                                    anc = float(t_cand.get("PliAnc", 0) or 0)
                                    lar = float(t_cand.get("PliLar", 0) or 0)
                                    if anc > 100 or lar > 140: continue 
                                    
                                    # Validaciones estándar
                                    mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                                    mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                                    if not mp_ok: continue

                                    # Aquí NO importa la cantidad de pliegos, entre manuales se vale todo
                                    if lista_para_ejecutar(t_cand):
                                        tarea_encontrada = t_cand
                                        fuente_maquina = vecina
                                        idx_robado = i
                                        break
                                
                                if tarea_encontrada: break

                    # -------------------------------------------------------
                    # EJECUCIÓN DEL ROBO
                    # -------------------------------------------------------
                    if tarea_encontrada:
                        tarea_para_mover = colas[fuente_maquina][idx_robado]
                        del colas[fuente_maquina][idx_robado]
                        
                        tarea_para_mover["Maquina"] = maquina 
                        colas[maquina].appendleft(tarea_para_mover)
                        
                        idx_cand = 0
                        tarea_robada = True
                    else:
                        break

                # ==========================================================

                if idx_cand > 0: colas[maquina].rotate(-idx_cand) 
                
                # ==========================================================
                # --- ESTRATEGIA "FRANCOTIRADOR" (LOOK-AHEAD) ---
                # ==========================================================
                
                # Miramos quién es el primero en la fila (sin sacarlo todavía)
                t_candidata = colas[maquina][0]
                es_barniz = "barniz" in t_candidata["Proceso"].lower()
                
                # CASO 1: VIENE UNA TAREA DE BARNIZADO
                if es_barniz:

                    print(f"🔍 FRANCOTIRADOR: Evaluando Barniz {t_candidata['OT_id']} en {maquina}...")
                    
                    # A) ¿YA TENGO UNA TAREA ESPERANDO EN EL BUFFER?
                    if buffer_espera[maquina]:
                        # ¡Llegó el momento! Encontré la segunda tarea (la actual t_candidata).
                        # Tu regla: "Ejecutar la que acaba de llegar (t_candidata) 
                        # y DESPUÉS la que estaba esperando".
                        
                        # 1. Saco la tarea actual de la cola y la tomo para procesar YA
                        t = colas[maquina].popleft() 
                        
                        # 2. Recupero la vieja tarea del buffer
                        tarea_vieja = buffer_espera[maquina]
                        buffer_espera[maquina] = None # Vacío la sala de espera
                        
                        # 3. Pongo la vieja tarea AL FRENTE de la cola (Priority Lane)
                        # para que sea la SIGUIENTE INMEDIATA en la próxima vuelta del bucle.
                        colas[maquina].appendleft(tarea_vieja)
                        
                        print(f"🎯 FRANCOTIRADOR: Ejecutando par Barnizado. 1° {t['OT_id']} -> Siguiente: {tarea_vieja['OT_id']}")

                    # B) NO HAY NADIE ESPERANDO. ¿VALE LA PENA ESPERAR?
                    else:
                        # Miro hasta 3 tareas adelante en la cola (índices 1, 2, 3)
                        encontre_pareja = False
                        limite_vision = min(len(colas[maquina]), 4) # 0 es la actual, miramos 1, 2, 3
                        for k in range(1, limite_vision):
                            
                            futura = colas[maquina][k]
                            print(f"   👀 Viendo futura tarea {futura['OT_id']} ({futura['Proceso']})...")
                            # Chequeo si es barniz y si sus dependencias permitirían ejecutarla
                            if "barniz" in futura["Proceso"].lower():
                                encontre_pareja = True
                                break
                        
                        if encontre_pareja:
                            # Si hay otra viniendo cerca, GUARDAMOS la actual y no la ejecutamos.
                            buffer_espera[maquina] = colas[maquina].popleft() # La saco de la cola y la guardo
                            print(f"⏳ HOLD: Guardando Barniz {buffer_espera[maquina]['OT_id']} esperando pareja cercana...")
                            
                            # Hacemos 'continue' para saltar esta vuelta. 
                            # En la próxima vuelta, el algoritmo procesará la tarea que estaba SEGUNDA (ej. Troquel).
                            continue 
                        else:
                            # No hay nada cerca, ejecutar normalmente (no me voy a quedar esperando eternamente)
                            t = colas[maquina].popleft()

                # CASO 2: NO ES BARNIZ (O es cualquier otra cosa)
                else:
                    t = colas[maquina].popleft()

                orden = df_ordenes.loc[t["idx"]].copy()

                # =================================================================
                # --- CORRECCIÓN CRÍTICA: USAR DATOS CALCULADOS (POSES/BOCAS) ---
                # =================================================================
                # Sobrescribimos los valores crudos de la OT con los valores
                # matemáticos que calculamos en _expandir_tareas (que ya tienen poses/bocas)
                orden["CantidadPliegos"] = float(t["CantidadPliegos"]) 
                orden["Poses"] = float(t.get("Poses", 1))
                orden["Bocas"] = float(t.get("Bocas", 1))
                
                _, proc_h = tiempo_operacion_h(orden, t["Proceso"], maquina, cfg)
                setup_min = setup_base_min(t["Proceso"], maquina, cfg)
                motivo = "Setup base"
                
                last_task = ultimo_en_maquina.get(maquina) 
                if last_task:
                    if (t["Proceso"] == "Troquelado" and 
                        str(last_task.get("CodigoTroquel", "")).strip().lower() == str(t.get("CodigoTroquel", "")).strip().lower()):
                        setup_min = setup_menor_min(t["Proceso"], maquina, cfg); motivo = "Mismo troquel (sin setup)"
                    elif usa_setup_menor(last_task, orden, t["Proceso"]): 
                        setup_min = setup_menor_min(t["Proceso"], maquina, cfg); motivo = "Setup menor (cluster)"
                
                total_h = proc_h + setup_min / 60.0
                if pd.isna(total_h) or total_h <= 0: continue    

                bloques = _reservar_en_agenda(agenda[maquina], total_h, cfg)
                if not bloques: colas[maquina].appendleft(t); break 
                inicio, fin = bloques[0][0], bloques[-1][1]
                # duracion_h = round((fin - inicio).total_seconds() / 3600.0, 3)
                segundos_netos = sum((b_fin - b_ini).total_seconds() for b_ini, b_fin in bloques)
                duracion_h = round(segundos_netos / 3600.0, 3)

                fin_proceso[t["OT_id"]][t["Proceso"]] = fin
                for b_ini, b_fin in bloques:
                    carga_reg.append({"Fecha": b_ini.date(), "Maquina": maquina, 
                                        "HorasPlanificadas": (b_fin - b_ini).total_seconds() / 3600.0, 
                                        "CapacidadDia": h_dia})

                filas.append({k: t.get(k) for k in ["OT_id", "CodigoProducto", "Subcodigo", "CantidadPliegos", "CantidadPliegosNetos",
                                                    "Bocas", "Poses", "Cliente", "Cliente-articulo", "Proceso", "Maquina", "DueDate"]} |
                             {"Setup_min": round(setup_min, 2), "Proceso_h": round(proc_h, 3), 
                              "Inicio": inicio, "Fin": fin, "Duracion_h": duracion_h, "Motivo": motivo})

                completado[t["OT_id"]].add(t["Proceso"])
                ultimo_en_maquina[maquina] = t 
                progreso = True; tareas_agendadas = True
                
                # (Mantenemos este break para que la Automática 
                # no sea demasiado agresiva en un solo turno)
                if tarea_robada:
                    break 

    # =================================================================
    # 6. SALIDAS 
    # =================================================================

    schedule = pd.DataFrame(filas)
    if not schedule.empty:
        schedule["DueDate"] = pd.to_datetime(schedule["DueDate"]) 
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
        resumen_ot["Atraso_h"] = ((resumen_ot["Fin_OT"] - due_date_deadline).dt.total_seconds() / 3600.0).clip(lower=0).fillna(0.0).round(2) 
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