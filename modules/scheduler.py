import pandas as pd
from datetime import datetime, timedelta, time, date
from collections import defaultdict, deque
import random

from modules.schedulers.machines import elegir_maquina
from modules.schedulers.priorities import _clave_prioridad_maquina, _cola_impresora_flexo, _cola_impresora_offset, _cola_troquelada
from modules.schedulers.agenda import _reservar_en_agenda
from modules.schedulers.tasks import _procesos_pendientes_de_orden, _expandir_tareas

# Importaciones de tus módulos auxiliares
from modules.config_loader import (
    es_si, horas_por_dia, proximo_dia_habil, construir_calendario, es_dia_habil, sumar_horas_habiles
)
from modules.tiempos_y_setup import (
    capacidad_pliegos_h, setup_base_min, setup_menor_min, usa_setup_menor, tiempo_operacion_h
)

# Procesos tercerizados sin cola (duración fija, concurrencia ilimitada)
PROCESOS_TERCERIZADOS_SIN_COLA = {"stamping", "plastificado", "encapado", "cuño"}

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
    inicio_general = datetime.combine(agenda["General"]["fecha"], agenda["General"]["hora"])

    # 1. Expande OTs en tareas individuales
    tasks = _expandir_tareas(df_ordenes, cfg)

    if tasks.empty: return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # =======================================================
    # 2. ORDEN LÓGICO DE PLANIFICACIÓN
    # =======================================================

    flujo_estandar = [p.strip() for p in cfg.get("orden_std", [])] 

    def _orden_proceso(maquina):
        proc_name = cfg["maquinas"].loc[cfg["maquinas"]["Maquina"] == maquina, "Proceso"]
        if proc_name.empty: return (999, 0)
        proc = proc_name.iloc[0]
        
        base_order = 999
        for i, p in enumerate(flujo_estandar):
            if p.lower() in proc.lower(): 
                base_order = i
                break
        
        # Desempate: Manuales (0) van ANTES que Automáticas (1)
        if "troquel" in proc.lower():
            if "autom" in maquina.lower():
                return (base_order, 1)
            else:
                return (base_order, 0)
        
        return (base_order, 0)

    maquinas = sorted(cfg["maquinas"]["Maquina"].unique(), key=_orden_proceso)
    
    # =================================================================
    # 3. REASIGNACIÓN TROQUELADO (Solo asigna, NO reserva tiempo)
    # =================================================================
    
    troq_cfg = cfg["maquinas"][cfg["maquinas"]["Proceso"].str.lower().eq("troquelado")]
    manuales = [m for m in troq_cfg["Maquina"].tolist() if "manual" in str(m).lower()]
    auto_names = [m for m in troq_cfg["Maquina"].tolist() if "autom" in str(m).lower()]
    auto_name = auto_names[0] if auto_names else None

    def _validar_medidas_troquel(maquina, anc, lar):
        # Normalizar nombre
        m = str(maquina).lower().strip()
        
        # Dimensiones de la tarea (STRICT CHECK - Sin rotación)
        # El usuario especificó que PliAnc es Ancho y PliLar es Largo
        w = float(anc or 0)
        l = float(lar or 0)

        if "autom" in m:
            # Min 38x38 (Ambos lados deben ser >= 38)
            return w >= 42 and l >= 39
        
        # Manuales: Maximos definidos (Ancho x Largo)
        # Manual 1: Max 80 x 105
        if "manual 1" in m or "manual1" in m:
            return w <= 104 and l <= 104
        
        # Manual 2: Max 66 x 90
        if "manual 2" in m or "manual2" in m:
            return w <= 70 and l <= 70
            
        # Manual 3: Max 70 x 100
        if "manual 3" in m or "manual3" in m:
            return w <= 110 and l <= 110
            
        return True # Por defecto si no matchea nombre

    if not tasks.empty and manuales: 
        if "CodigoTroquel" not in tasks.columns: tasks["CodigoTroquel"] = ""
        tasks["CodigoTroquel"] = tasks["CodigoTroquel"].fillna("").astype(str).str.strip().str.lower()
        
        cap = {} 
        for m in manuales + ([auto_name] if auto_name else []):
            if m: cap[m] = float(capacidad_pliegos_h("Troquelado", m, cfg))
        load_h = {m: 0.0 for m in cap.keys()} 

        # Agenda simulada solo para lectura de fechas (no escritura)
        agenda_m = {m: {"fecha": agenda[m]["fecha"], "hora": agenda[m]["hora"]} for m in cap.keys()}

        mask_troq = tasks["Proceso"].eq("Troquelado")
        troq_df = tasks.loc[mask_troq].copy()

        if not troq_df.empty:
            troq_df["_troq_key"] = troq_df["CodigoTroquel"]
            troq_df["CantidadPliegos"] = pd.to_numeric(troq_df["CantidadPliegos"], errors='coerce').fillna(0)
            
            grupos = [] 
            for troq_key, g in troq_df.groupby("_troq_key", dropna=False):
                due_min = pd.to_datetime(g["DueDate"], errors="coerce").min() or pd.Timestamp.max
                total_pliegos = float(g["CantidadPliegos"].sum())
                
                # Datos para validación de medidas
                max_anc = g["PliAnc"].max()
                max_lar = g["PliLar"].max()
                min_anc = g["PliAnc"].min()
                min_lar = g["PliLar"].min()
                bocas = float(g["Bocas"].max()) # Tomamos el maximo de bocas del grupo

                grupos.append((due_min, troq_key, g.index.tolist(), total_pliegos, max_anc, max_lar, min_anc, min_lar, bocas))
            grupos.sort() 

            for _, troq_key, idxs, total_pliegos, max_anc, max_lar, min_anc, min_lar, bocas in grupos:
                candidatas = []
                
                # 1. Validar candidatos por TAMAÑO primero
                posibles = manuales + ([auto_name] if auto_name else [])
                candidatos_tamano = []
                for m in posibles:
                    if "autom" in str(m).lower():
                        # Para Automatica (Restricción de MINIMO), usamos las dimensiones MINIMAS del grupo
                        # Si la hoja más chica es < 38, NO entra en Auto.
                        if _validar_medidas_troquel(m, min_anc, min_lar):
                            candidatos_tamano.append(m)
                    else:
                        # Para Manuales (Restricción de MAXIMO), usamos las dimensiones MAXIMAS del grupo
                        # Si la hoja más grande es > 80, NO entra en Manual.
                        if _validar_medidas_troquel(m, max_anc, max_lar):
                            candidatos_tamano.append(m)
                
                if not candidatos_tamano: continue

                # 2. REGLA DE BOCAS (> 6) -> Automática Obligatoria (si entra)
                if bocas > 6:
                    if auto_name and (auto_name in candidatos_tamano):
                        candidatas = [auto_name]
                    else:
                        # Si no entra en Auto, va a manual compatible
                        candidatas = [m for m in candidatos_tamano if m != auto_name]
                
                # 3. REGLA DE CANTIDAD (> 3000) -> Automática Obligatoria (si entra)
                elif total_pliegos > 3000:
                    if auto_name and (auto_name in candidatos_tamano):
                        candidatas = [auto_name]
                    else:
                        candidatas = [m for m in candidatos_tamano if m != auto_name]
                
                # 4. DEFAULT (<= 3000 y <= 6 Bocas) -> Preferencia Manual
                else:
                    # Intentar filtrar solo manuales (excluir Auto)
                    manuales_compatibles = [m for m in candidatos_tamano if m != auto_name]
                    
                    if manuales_compatibles:
                        candidatas = manuales_compatibles
                    else:
                        # Si no entra en ninguna manual (por tamaño), permitimos Auto
                        candidatas = candidatos_tamano

                if not candidatas: continue

                def criterio_balanceo(m):
                    # Sin penalización artificial para Manual 3
                    fecha_orden = agenda_m[m]["fecha"]
                    return (fecha_orden, agenda_m[m]["hora"], load_h[m])

                m_sel = min(candidatas, key=criterio_balanceo)
                
                tasks.loc[idxs, "Maquina"] = m_sel
                # Solo actualizamos carga estimada, NO reservamos tiempo real
                load_h[m_sel] += total_pliegos / cap[m_sel]

    # =====================================================================
    # 3.1 REASIGNACIÓN DESCARTONADO (Solo asigna, NO reserva tiempo)
    # =====================================================================

    desc_cfg = cfg["maquinas"][cfg["maquinas"]["Proceso"].str.lower().str.contains("descartonado")]
    desc_maquinas = sorted(desc_cfg["Maquina"].tolist()) 

    if not tasks.empty and len(desc_maquinas) > 1:
        # ESTRATEGIA: COLA ÚNICA (POOL)
        # Todas las tareas van a un "buzón" común llamado "POOL_DESCARTONADO".
        # Las máquinas tomarán tareas de ahí a medida que se liberen.
        
        mask_desc = tasks["Proceso"].eq("Descartonado")
        tasks.loc[mask_desc, "Maquina"] = "POOL_DESCARTONADO"

    # =================================================================
    # 4. CONSTRUCCIÓN DE COLAS INTELIGENTES
    # =================================================================

    colas = {}
    buffer_espera = {m: [] for m in maquinas} # Buffer para Francotirador
    
    for m in maquinas:
        q = tasks[tasks["Maquina"] == m].copy()
        m_lower = m.lower()

        if q.empty: colas[m] = deque()
        elif ("manual" in m_lower) or ("autom" in m_lower) or ("troquel" in m_lower): colas[m] = _cola_troquelada(q)
        elif "offset" in m_lower: colas[m] = _cola_impresora_offset(q)
        elif ("flexo" in m_lower) or ("impres" in m_lower): colas[m] = _cola_impresora_flexo(q)
        else: 
            # Orden por defecto: Urgente -> DueDate -> Orden Proceso -> Cantidad
            q.sort_values(by=["Urgente", "DueDate", "_orden_proceso", "CantidadPliegos"], ascending=[False, True, True, False], inplace=True)
            colas[m] = deque(q.to_dict("records"))

    # Crear la cola del POOL si existe
    if "POOL_DESCARTONADO" in tasks["Maquina"].values:
        q_pool = tasks[tasks["Maquina"] == "POOL_DESCARTONADO"].copy()
        q_pool.sort_values(by=["Urgente", "DueDate", "_orden_proceso", "CantidadPliegos"], ascending=[False, True, True, False], inplace=True)
        colas["POOL_DESCARTONADO"] = deque(q_pool.to_dict("records"))
    else:
        colas["POOL_DESCARTONADO"] = deque()

    # =================================================================
    # 5. LÓGICA DE PLANIFICACIÓN (EL NÚCLEO)
    # =================================================================
    
    pendientes_por_ot = defaultdict(set); [pendientes_por_ot[t["OT_id"]].add(t["Proceso"]) for _, t in tasks.iterrows()]
    completado = defaultdict(set); fin_proceso = defaultdict(dict)
    ultimo_en_maquina = {m: None for m in maquinas} 
    carga_reg, filas = [], []; h_dia = horas_por_dia(cfg)

    def quedan_tareas(): return any(len(q) > 0 for q in colas.values())

    def verificar_disponibilidad(t, maquina_contexto=None): 
        """
        Verifica si una tarea puede ejecutarse (dependencias listas).
        Devuelve (bool_runnable, datetime_disponible).
        NO MODIFICA LA AGENDA.
        """
        def clean(s):
            if not s: return ""
            s = str(s).lower().strip()
            trans = str.maketrans("áéíóúüñ", "aeiouun")
            s = s.translate(trans)
            # Alias Agresivos
            if "flexo" in s: return "impresion flexo"
            if "offset" in s: return "impresion offset"
            if "troquel" in s: return "troquelado"
            return s

        proc_actual_clean = clean(t["Proceso"])
        ot = t["OT_id"]
        flujo_clean = [clean(p) for p in flujo_estandar]
        
        # Si no está en el flujo estándar, asumimos que no tiene dependencias previas en este flujo
        if proc_actual_clean not in flujo_clean: 
            return (True, None)
            
        idx = flujo_clean.index(proc_actual_clean)
        pendientes_clean = {clean(p) for p in pendientes_por_ot[ot]}
        prev_procs_names = []
        for p_raw in flujo_estandar[:idx]:
            if clean(p_raw) in pendientes_clean:
                prev_procs_names.append(p_raw)

        if not prev_procs_names: 
            return (True, None)

        completados_clean = {clean(c) for c in completado[ot]}
        for p in prev_procs_names:
            if clean(p) not in completados_clean:
                return (False, None) # Falta un proceso previo
        
        # Calcular cuándo estará lista la última dependencia
        last_end = max((fin_proceso[ot].get(p) for p in prev_procs_names if fin_proceso[ot].get(p)), default=None)
        
        return (True, last_end)

    def _prioridad_dinamica(m):
        if "autom" in m.lower():
            return (0, agenda[m]["fecha"], agenda[m]["hora"], m)
        return (1, agenda[m]["fecha"], agenda[m]["hora"], m)

    progreso = True
    while quedan_tareas() and progreso:
        progreso = False
        
        # Mezclar máquinas para evitar sesgo hacia la primera (Descartonadora 1)
        maquinas_shuffled = list(maquinas)
        # random.shuffle(maquinas_shuffled)

        for maquina in sorted(maquinas_shuffled, key=_prioridad_dinamica):
            if not colas.get(maquina):  
                # --- SISTEMA DE RESCATE (CRÍTICO) ---
                # Si la cola se vació pero quedó alguien encerrado en el buffer, ¡LIBÉRALO!
                if buffer_espera.get(maquina):
                    colas[maquina].extendleft(reversed(buffer_espera[maquina]))
                    buffer_espera[maquina] = []
                    progreso = True # Marcar progreso para no cortar la ejecución
                    # No hacemos continue, dejamos que fluya para que se procese abajo
                else:
                    # EXCEPCIÓN: Si es Descartonadora y hay tareas en el POOL, ¡NO CONTINUAR!
                    if "descartonad" in maquina.lower() and colas.get("POOL_DESCARTONADO"):
                        pass # Dejar pasar para que intente robar del POOL
                    else:
                        continue

            tareas_agendadas = True
            tasks_scheduled_count = 0 # LIMITADOR DE RACHA
            while tareas_agendadas: 
                if tasks_scheduled_count >= 1: break # Yield para permitir que otras máquinas (dependencias) avancen
                tareas_agendadas = False
                
                # --- CHEQUEO DE SEGURIDAD PREVIO ---
                if not colas.get(maquina):
                    if buffer_espera.get(maquina):
                         colas[maquina].extendleft(reversed(buffer_espera[maquina]))
                         buffer_espera[maquina] = []
                    else:
                        # EXCEPCIÓN: Si es Descartonadora y hay tareas en el POOL, ¡NO ROMPER!
                        if "descartonad" in maquina.lower() and colas.get("POOL_DESCARTONADO"):
                            pass # Dejar pasar
                        else:
                            break
                
                # ==========================================================
                # PASO 1: BÚSQUEDA DE CANDIDATA (GAP FILLING)
                # ==========================================================
                idx_cand = -1 
                mejor_candidato_futuro = None # (idx, fecha_disponible)
                
                current_agenda_dt = datetime.combine(agenda[maquina]["fecha"], agenda[maquina]["hora"])

                for i, t_cand in enumerate(colas[maquina]):
                    mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                    mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                    if not mp_ok: continue

                    runnable, available_at = verificar_disponibilidad(t_cand, maquina)
                    
                    if not runnable: continue

                    # Si está lista YA (o antes), la tomamos inmediatamente (Gap Filling)
                    if not available_at or available_at <= current_agenda_dt:
                        idx_cand = i
                        mejor_candidato_futuro = None # Ya encontramos una perfecta
                        break
                    
                    # Si no está lista ya, pero es runnable, la guardamos como opción futura
                    if mejor_candidato_futuro is None:
                        mejor_candidato_futuro = (i, available_at)
                    else:
                        # Si esta está lista ANTES que la que teníamos guardada, la preferimos
                        if available_at < mejor_candidato_futuro[1]:
                            mejor_candidato_futuro = (i, available_at)
                
                # Si no encontramos ninguna lista YA, pero hay futuras, tomamos la mejor futura
                if idx_cand == -1 and mejor_candidato_futuro:
                    idx_cand = mejor_candidato_futuro[0]
                    future_dt = mejor_candidato_futuro[1]
                    
                    # AVANZAR EL RELOJ DE LA MÁQUINA (Solo aquí, cuando decidimos esperar)
                    # Lógica de salto de tiempo (respetando días hábiles)
                    fecha_destino = future_dt.date()
                    hora_destino = future_dt.time()

                    if not es_dia_habil(fecha_destino, cfg):
                        fecha_destino = proximo_dia_habil(fecha_destino - timedelta(days=1), cfg)
                        hora_destino = time(7, 0)
                    
                    # Solo avanzamos si el destino es futuro (debería serlo por lógica anterior)
                    dest_dt = datetime.combine(fecha_destino, hora_destino)
                    if dest_dt > current_agenda_dt:
                        agenda[maquina]["fecha"] = fecha_destino
                        agenda[maquina]["hora"] = hora_destino
                        h_usadas = (hora_destino.hour - 7) + (hora_destino.minute / 60.0)
                        agenda[maquina]["resto_horas"] = max(0, h_dia - h_usadas)
                
                # ==========================================================
                # PASO 2: INTENTO DE ROBO (Casos A, B, C, D)
                # ==========================================================
                tarea_robada = False
                if idx_cand == -1:
                    if buffer_espera.get(maquina):
                         colas[maquina].extendleft(reversed(buffer_espera[maquina]))
                         buffer_espera[maquina] = []
                         idx_cand = 0 # Ahora sí tengo algo para hacer
                    
                    else:
                        # Si realmente estoy vacío y sin buffer, ahí sí salgo a robar
                        tarea_encontrada = None
                        fuente_maquina = None
                        idx_robado = -1

                        # ------------------------------------------------------
                        # NUEVO: Robo desde el POOL (Prioridad Máxima para Descartonadoras)
                        # ------------------------------------------------------
                        if "descartonad" in maquina.lower() and colas.get("POOL_DESCARTONADO"):
                            best_pool_idx = -1
                            best_pool_future = None # (idx, available_at)
                            best_has_successor = False # Flag for priority
                            best_is_urgent = False
                            current_agenda_dt = datetime.combine(agenda[maquina]["fecha"], agenda[maquina]["hora"])

                            for i, t_cand in enumerate(colas["POOL_DESCARTONADO"]):
                                # Validar MP
                                mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                                mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                                if not mp_ok: continue
                                
                                runnable, available_at = verificar_disponibilidad(t_cand, maquina)
                                
                                if not runnable: continue

                                # Check for successors (Pegado, Ventana, etc.)
                                # We check if there are any pending processes that are NOT Descartonado or previous ones.
                                # A simple heuristic: check if '_PEN_Pegado' or '_PEN_Ventana' or similar are 'Si'.
                                # Or check if there are any pending keys starting with '_PEN_' other than current.
                                has_successor = False
                                for k, v in t_cand.items():
                                    if k.startswith("_PEN_") and str(v).lower() == "si":
                                        proc_pend = k.replace("_PEN_", "").lower()
                                        if "descartonado" not in proc_pend and "impres" not in proc_pend and "troquel" not in proc_pend:
                                            has_successor = True
                                            break
                                
                                # Si está lista YA
                                if not available_at or available_at <= current_agenda_dt:
                                    # Logic Refined:
                                    # 1. Urgency is King. (Urgente="Si" > "No")
                                    # 2. If Urgency is same, prefer Successor.
                                    # 3. If both same, prefer original order (DueDate).
                                    
                                    is_urgent = str(t_cand.get("Urgente", "")).lower() == "si"
                                    
                                    if best_pool_idx == -1:
                                        best_pool_idx = i
                                        best_has_successor = has_successor
                                        best_is_urgent = is_urgent
                                    else:
                                        # Compare current candidate (i) with best so far
                                        
                                        # 1. Urgency Check
                                        if is_urgent and not best_is_urgent:
                                            # Found urgent, replace non-urgent best
                                            best_pool_idx = i
                                            best_has_successor = has_successor
                                            best_is_urgent = True
                                        elif not is_urgent and best_is_urgent:
                                            # Current is not urgent, best is. Keep best.
                                            pass
                                        else:
                                            # Same urgency status. Check Successor.
                                            if has_successor and not best_has_successor:
                                                best_pool_idx = i
                                                best_has_successor = True
                                                best_is_urgent = is_urgent
                                            # Else: Keep best (respects original sort order which is DueDate)
                                    
                                    # Note: We don't break immediately anymore because we want to scan for a better priority task
                                    continue
                                
                                # Si es futura
                                if best_pool_future is None:
                                    best_pool_future = (i, available_at)
                                else:
                                    if available_at < best_pool_future[1]:
                                        best_pool_future = (i, available_at)
                            
                            # Decisión final del POOL
                            idx_robado = -1
                            if best_pool_idx != -1:
                                idx_robado = best_pool_idx
                            elif best_pool_future:
                                idx_robado = best_pool_future[0]
                                # Nota: Al robar una futura, el avance de agenda ocurrirá naturalmente
                                # cuando se procese la tarea en el paso 4 (verificar_disponibilidad se llama de nuevo)
                            
                            if idx_robado != -1:
                                tarea_encontrada = colas["POOL_DESCARTONADO"][idx_robado]
                                fuente_maquina = "POOL_DESCARTONADO"
                                # No break aquí, dejamos que fluya al bloque de ejecución de robo
                        
                        if tarea_encontrada:
                            # Ejecutar robo del POOL inmediatamente
                            pass # Se procesa abajo en el bloque común de robo
                        
                        # A: Auto roba a Manual
                        elif maquina in auto_names:
                            for m_manual in manuales:
                                if not colas.get(m_manual): continue
                                for i, t_cand in enumerate(colas[m_manual]):
                                    if t_cand["Proceso"].strip() != "Troquelado": continue

                                    cant = float(t_cand.get("CantidadPliegos", 0) or 0)
                                    if cant < 3000: continue
                                    
                                    # Validar medidas para Auto (Min 38x38)
                                    anc = float(t_cand.get("PliAnc", 0) or 0); lar = float(t_cand.get("PliLar", 0) or 0)
                                    if not _validar_medidas_troquel(maquina, anc, lar): continue

                                    mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                                    mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                                    if not mp_ok: continue
                                    
                                    runnable, _ = verificar_disponibilidad(t_cand, maquina)
                                    if runnable:
                                        tarea_encontrada = t_cand; fuente_maquina = m_manual; idx_robado = i; break
                                if tarea_encontrada: break

                        # B y C: Manual roba a Auto o Manual
                        elif any(m in maquina for m in manuales):
                            # B: Robar a Auto
                            if auto_name and colas.get(auto_name):
                                for i, t_cand in enumerate(colas[auto_name]):
                                    if t_cand["Proceso"].strip() != "Troquelado": continue
                                    
                                    # REGLA: Manual solo roba si cantidad <= 3000
                                    cant = float(t_cand.get("CantidadPliegos", 0) or 0)
                                    # if cant > 3000: continue 

                                    # Validar medidas para ESTA manual
                                    anc = float(t_cand.get("PliAnc", 0) or 0); lar = float(t_cand.get("PliLar", 0) or 0)
                                    if not _validar_medidas_troquel(maquina, anc, lar): continue
                                    
                                    mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                                    mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                                    if not mp_ok: continue
                                    
                                    runnable, _ = verificar_disponibilidad(t_cand, maquina)
                                    if runnable:
                                        tarea_encontrada = t_cand; fuente_maquina = auto_name; idx_robado = i; break
                            
                            # C: Robar a Vecina Manual
                            if not tarea_encontrada:
                                vecinas = [m for m in manuales if m != maquina]
                                for vecina in vecinas:
                                    if not colas.get(vecina): continue
                                    for i, t_cand in enumerate(colas[vecina]):
                                        if t_cand["Proceso"].strip() != "Troquelado": continue
                                        
                                        # Validar medidas para ESTA manual
                                        anc = float(t_cand.get("PliAnc", 0) or 0); lar = float(t_cand.get("PliLar", 0) or 0)
                                        if not _validar_medidas_troquel(maquina, anc, lar): continue

                                        mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                                        mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                                        if not mp_ok: continue
                                        
                                        runnable, _ = verificar_disponibilidad(t_cand, maquina)
                                        if runnable:
                                            tarea_encontrada = t_cand; fuente_maquina = vecina; idx_robado = i; break
                                    if tarea_encontrada: break
                        
                        # D: Robo entre Descartonadoras
                        elif "descartonad" in maquina.lower():
                            vecinas_desc = [m for m in colas.keys() if "descartonad" in m.lower() and m != maquina]
                            for vecina in vecinas_desc:
                                if not colas.get(vecina): continue
                                for i, t_cand in enumerate(colas[vecina]):
                                    if "descartonad" not in t_cand["Proceso"].lower(): continue
                                    mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                                    mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                                    if not mp_ok: continue
                                    
                                    runnable, _ = verificar_disponibilidad(t_cand, maquina)
                                    if runnable:
                                        tarea_encontrada = t_cand; fuente_maquina = vecina; idx_robado = i; break
                                if tarea_encontrada: break

                        # Ejecutar Robo
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
                # PASO 3: FRANCOTIRADOR Y EJECUCIÓN
                # ==========================================================
                # ==========================================================
                # PASO 3: FRANCOTIRADOR Y EJECUCIÓN
                # ==========================================================
                if idx_cand != -1:
                    t_final = None
                    se_ejecuta_ya = True

                    # CASO 1: GAP FILLING (Cherry Picking) - Preservar orden de los saltados
                    if not tarea_robada and idx_cand > 0:
                        t_final = colas[maquina][idx_cand]
                        del colas[maquina][idx_cand]
                        se_ejecuta_ya = True
                    
                    # CASO 2: NORMAL (Tope de Cola o Robado)
                    else:
                        # Traemos la tarea al frente si es necesario (solo si no es gap filling, que ya manejamos arriba)
                        # Si tarea_robada=True, idx_cand es 0 (o irrelevante porque ya lo pusimos al frente en el paso de robo)
                        
                        t_candidata = colas[maquina][0]
                        es_barniz = "barniz" in t_candidata["Proceso"].lower()
                        
                        if es_barniz:
                            # 1. CONSOLIDACIÓN: Si hay gente en el buffer, ¡traerlos YA!
                            if buffer_espera[maquina]:
                                colas[maquina].extendleft(reversed(buffer_espera[maquina]))
                                buffer_espera[maquina] = []
                                se_ejecuta_ya = True 
                            
                            # 2. MIRAR AL FUTURO
                            else:
                                bloque_barniz = []
                                idx = 0
                                while idx < len(colas[maquina]):
                                    t = colas[maquina][idx]
                                    if "barniz" in t["Proceso"].lower():
                                        bloque_barniz.append(t)
                                        idx += 1
                                    else:
                                        break
                                
                                rango_vision = 3
                                encontre_pareja = False
                                limit = min(len(colas[maquina]), idx + rango_vision)
                                
                                for k in range(idx, limit):
                                    futura = colas[maquina][k]
                                    if "barniz" in futura["Proceso"].lower():
                                        mp = str(futura.get("MateriaPrimaPlanta")).strip().lower()
                                        mp_ok = mp in ("false", "0", "no", "falso", "") or not futura.get("MateriaPrimaPlanta")
                                        if mp_ok:
                                            encontre_pareja = True
                                            break
                                
                                if encontre_pareja:
                                    for _ in range(len(bloque_barniz)):
                                        t_removed = colas[maquina].popleft()
                                        buffer_espera[maquina].append(t_removed)
                                    
                                    se_ejecuta_ya = False
                                    progreso = True 
                                    continue

                        if se_ejecuta_ya:
                            t_final = colas[maquina].popleft()

                    #========================================
                    # PASO 4: EJECUCIÓN FINAL
                    #========================================

                    if se_ejecuta_ya and t_final:
                        t = t_final
                        orden = df_ordenes.loc[t["idx"]].copy()
                        proceso_nombre = str(t["Proceso"])
                        proceso_lower = proceso_nombre.strip().lower()

                        # Inyección de datos calculados
                        orden["CantidadPliegos"] = float(t["CantidadPliegos"])
                        orden["Poses"] = float(t.get("Poses", 1))
                        orden["Bocas"] = float(t.get("Bocas", 1))

                        # Calcular tiempos
                        # Calcular tiempos
                        _, proc_h = tiempo_operacion_h(orden, proceso_nombre, maquina, cfg)
                        setup_min = 0.0
                        motivo = "Setup base"

                        if proceso_lower in PROCESOS_TERCERIZADOS_SIN_COLA:
                            motivo = "Duración fija tercerizado"
                            total_h = proc_h
                        else:
                            setup_min = setup_base_min(proceso_nombre, maquina, cfg)
                            last_task = ultimo_en_maquina.get(maquina)
                            if last_task:
                                if (proceso_nombre == "Troquelado" and
                                    str(last_task.get("CodigoTroquel", "")).strip().lower() == str(t.get("CodigoTroquel", "")).strip().lower()):
                                    setup_min = setup_menor_min(proceso_nombre, maquina, cfg); motivo = "Mismo troquel (sin setup)"
                                elif usa_setup_menor(last_task, orden, proceso_nombre):
                                    setup_min = setup_menor_min(proceso_nombre, maquina, cfg); motivo = "Setup menor (cluster)"
                            
                            total_h = proc_h + setup_min / 60.0

                        if pd.isna(total_h) or total_h <= 0:
                            continue
                        
                        # --- LÓGICA DE AGENDA (Reserva de tiempo) ---
                        inicio_general = datetime.combine(agenda[maquina]["fecha"], agenda[maquina]["hora"])
                        
                        # Ajuste por dependencias (Solo si es necesario, aunque ya deberíamos estar en fecha)
                        # verificar_disponibilidad nos dio la fecha, pero por seguridad:
                        _, available_at = verificar_disponibilidad(t, maquina)
                        if available_at and available_at > inicio_general:
                            inicio_general = available_at
                            # Sincronizar agenda si nos adelantamos
                            agenda[maquina]["fecha"] = inicio_general.date()
                            agenda[maquina]["hora"] = inicio_general.time()
                            h_usadas = (inicio_general.hour - 7) + (inicio_general.minute / 60.0)
                            agenda[maquina]["resto_horas"] = max(0, h_dia - h_usadas)

                        # Calcular Fin (Usando lógica de horas hábiles para tercerizados o normal para internas)
                        if proceso_lower in PROCESOS_TERCERIZADOS_SIN_COLA:
                            # ... (Lógica existente para tercerizados)
                            inicio = inicio_general
                            prev_fins = [fin for fin in fin_proceso[t["OT_id"]].values() if fin]
                            if prev_fins:
                                inicio = max([inicio] + prev_fins)
                            fin = sumar_horas_habiles(inicio, total_h, cfg)

                            filas.append({k: t.get(k) for k in ["OT_id", "CodigoProducto", "Subcodigo", "CantidadPliegos", "CantidadPliegosNetos",
                                                                "Bocas", "Poses", "Cliente", "Cliente-articulo", "Proceso", "Maquina", "DueDate", "PliAnc", "PliLar"]} |
                                         {"Setup_min": round(setup_min, 2), "Proceso_h": round(proc_h, 3),
                                          "Inicio": inicio, "Fin": fin, "Duracion_h": round(total_h, 3), "Motivo": motivo})

                            fin_proceso[t["OT_id"]][proceso_nombre] = fin
                            completado[t["OT_id"]].add(proceso_nombre)
                            ultimo_en_maquina[maquina] = t
                            progreso = True; tareas_agendadas = True
                            tasks_scheduled_count += 1

                            agenda[maquina]["fecha"] = inicio_general.date()
                            agenda[maquina]["hora"] = inicio_general.time()
                            agenda[maquina]["resto_horas"] = h_dia

                            if tarea_robada:
                                break
                            continue

                        # ... (Lógica normal para máquinas internas)
                        inicio_real = inicio_general
                        
                        # Consumo de tiempo en agenda (USANDO LÓGICA ROBUSTA)
                        bloques_reserva = _reservar_en_agenda(agenda[maquina], total_h, cfg)
                        
                        if bloques_reserva:
                            inicio_real = bloques_reserva[0][0]
                            fin_real = bloques_reserva[-1][1]
                        else:
                            # Fallback (no debería ocurrir)
                            fin_real = inicio_real
                        
                        motivo = "Planificado"
                        if tarea_robada: motivo = "Robado (Optimización)"
                        
                        filas.append({k: t.get(k) for k in ["OT_id", "CodigoProducto", "Subcodigo", "CantidadPliegos", "CantidadPliegosNetos",
                                                            "Bocas", "Poses", "Cliente", "Cliente-articulo", "Proceso", "Maquina", "DueDate", "PliAnc", "PliLar"]} |
                                     {"Setup_min": round(setup_min, 2), "Proceso_h": round(proc_h, 3),
                                      "Inicio": inicio_real, "Fin": fin_real, "Duracion_h": round(total_h, 3), "Motivo": motivo})

                        fin_proceso[t["OT_id"]][proceso_nombre] = fin_real
                        completado[t["OT_id"]].add(proceso_nombre)
                        ultimo_en_maquina[maquina] = t
                        progreso = True
                        tareas_agendadas = True
                        tasks_scheduled_count += 1
                        
                        if tarea_robada:
                            break # Salir del while de tareas_agendadas para reevaluar la cola

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
            ).reset_index()
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
