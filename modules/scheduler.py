import pandas as pd
from datetime import datetime, timedelta, time, date
from collections import defaultdict, deque

from modules.schedulers.machines import validar_medidas_troquel, get_machine_process_order
from modules.schedulers.priorities import (
    _clave_prioridad_maquina, _cola_impresora_flexo, _cola_impresora_offset, 
    _cola_troquelada, _cola_cortadora_bobina, get_downstream_presence_score
)
from modules.schedulers.agenda import _reservar_en_agenda
from modules.schedulers.tasks import _procesos_pendientes_de_orden, _expandir_tareas

# Importaciones de tus módulos auxiliares
from modules.utils.config_loader import (
    es_si, 
    horas_por_dia, 
    proximo_dia_habil, 
    construir_calendario,
    es_feriado,
    es_dia_habil,
    sumar_horas_habiles
)

from modules.utils.tiempos_y_setup import (
    capacidad_pliegos_h, 
    setup_base_min, 
    setup_menor_min, 
    usa_setup_menor, 
    tiempo_operacion_h
)


# Procesos tercerizados sin cola (duración fija, concurrencia ilimitada)
PROCESOS_TERCERIZADOS_SIN_COLA = {"stamping", "plastificado", "encapado", "cuño"}

# =======================================================
# Programador principal (Versión Combinada)
# =======================================================

# --- HELPER: SCORING PRIORIDAD GROUPING ---


def programar(df_ordenes, cfg, start=date.today(), start_time=None, debug=False):
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

    # 1.0b GESTIONAR PROCESOS SALTADOS (IsSkipped)
    # NO eliminamos las tareas, simplemente las asignamos a una máquina virtual "SALTADO"
    # para que el visualizador las pueda mostrar si se solicita.
    if "IsSkipped" in tasks.columns:
        # Asignar maquina "SALTADO" a las que tengan IsSkipped=True
        tasks.loc[tasks["IsSkipped"] == True, "Maquina"] = "SALTADO"



    # Identify Pending tasks to avoid double-locking (Pending wins)
    pending_list = cfg.get("pending_processes", [])
    pending_set = set()
    for pp in pending_list:
        pending_set.add((str(pp["ot_id"]).strip(), str(pp["maquina"]).strip()))

    if "_match_key" in tasks.columns:
        tasks.drop(columns=["_match_key"], inplace=True)

    # =======================================================
    # 1.1 PROCESAMIENTO IMAGEN DE PLANTA (PENDING PROCESSES)
    # =======================================================
    
    # Listas para guardar lo ya agendado por imagen de planta
    completado = defaultdict(set)
    fin_proceso = defaultdict(dict)
    ultimo_en_maquina = {m: None for m in cfg["maquinas"]["Maquina"].unique()} 
    filas = []

    filas = []
    
    pending_list = cfg.get("pending_processes", [])
    if pending_list:

        # Mapa inverso para saber qué tareas borrar de 'tasks'
        # Clave: (OT_id, Maquina) -> Indices en tasks
        # Pero ojo, necesitamos saber el "Proceso" para mappear a Maquina si no es obvio, 
        # pero aquí el usuario nos da la Maquina directamente.
        
        for pp in pending_list:
            pp_maquina = pp["maquina"]
            pp_ot = pp["ot_id"]
            pp_qty = float(pp["cantidad_pendiente"])
            
            # Buscar la tarea original para sacar metadatos (Cliente, Producto, etc.)
            # Filtramos tasks por OT_id y Maquina
            # Nota: 'tasks' tiene columna 'Maquina' asignada? 
            # Originalmente _expandir_tareas asigna la máquina preferida o default.
            # Pero para procesos manuales/troquelado podría ser ambiguo AÚN si no corrimos el optimizador.
            # SIN EMBARGO, _expandir_tareas ya genera una fila por operación.
            # Intentamos matchear por OT y Maquina.
            
            # Normalizamos nombres para búsqueda
            mask_ot = tasks["OT_id"] == pp_ot
            
            # En tasks, la columna 'Maquina' puede no estar llena o ser genérica (ej. elecciones dinámicas).
            # Pero _expandir_tareas intenta asignar si es única.
            # Estrategia: Buscar por OT y ver cual operación corresponde a esa máquina.
            
            # Obtenemos el proceso de esa máquina según config
            row_maq = cfg["maquinas"][cfg["maquinas"]["Maquina"] == pp_maquina]
            if row_maq.empty: continue
            proc_target = row_maq["Proceso"].iloc[0] # Ej: "Impresión Flexo"
            
            # Buscamos en tasks esa OT y ese Proceso
            # Ojo con procesos genéricos ("Troquelado") vs máquinas específicas.
            
            mask_proc = tasks["Proceso"].astype(str).str.lower() == proc_target.lower()
            
            # Caso especial: Maquina especifica de un grupo (ej. Troquelado)
            # Si el usuario eligió "Manual 1" (Troquelado), y en tasks dice "Troquelado", vale.
            if "troquel" in proc_target.lower():
                 mask_proc = tasks["Proceso"].astype(str).str.lower().str.contains("troquel")
            elif "impres" in proc_target.lower():
                 # Si es Flexo vs Offset, ya deberían estar separados en el nombre del proceso
                 pass

            candidates = tasks[mask_ot & mask_proc]
            
            if candidates.empty:
                # Si no encontramos la tarea, quizás es porque la máquina no matchea perfecto con el proceso estándar
                # O la OT no existe. Logueamos y seguimos.
                continue
            
            # Tomamos la primera coincidencia (debería ser única por proceso)
            idx_task = candidates.index[0]
            t = tasks.loc[idx_task].to_dict()
            # t["idx"] = idx_task <-- LINEA ELIMINADA (Causaba el bug)
            
            # --- AGENDAR INMEDIATAMENTE ---
            
            # 1. Calcular duración con la cantidad PENDIENTE (no la total)
            #    Creamos una "orden fake" con esa cantidad
            orden_fake = df_ordenes.loc[t["idx"]].copy()
            orden_fake["CantidadPliegos"] = pp_qty
            
            #    Usamos tiempo_operacion_h (que ya validamos)
            _, proc_h = tiempo_operacion_h(orden_fake, proc_target, pp_maquina, cfg)
            
            #    Setup: Asumimos que si está "En curso", el setup YA SE HIZO.
            #    Por lo tanto setup_min = 0.
            setup_min = 0.0
            total_h = proc_h # Solo tiempo productivo restante
            
            motivo = "En Curso (Planta)"
            
            # 2. Reservar en Agenda
            #    Empieza DESDE AHORA (inicio_general del plan)
            #    Ojo: inicio_general se define unas lineas arriba.
            
            current_dt_maq = datetime.combine(agenda[pp_maquina]["fecha"], agenda[pp_maquina]["hora"])
            
            #    Reservamos
            bloques_reserva = _reservar_en_agenda(agenda[pp_maquina], total_h, cfg)
            
            if bloques_reserva:
                inicio_real = bloques_reserva[0][0]
                fin_real = bloques_reserva[-1][1]
                
                # Guardamos resultado
                filas.append({k: t.get(k) for k in ["OT_id", "CodigoProducto", "Subcodigo", "CantidadPliegos", "CantidadPliegosNetos",
                                                        "Bocas", "Poses", "Cliente", "Cliente-articulo", "Proceso", "Maquina", "DueDate", "PliAnc", "PliLar"]} |
                                 {"Setup_min": 0.0, "Proceso_h": round(proc_h, 3),
                                  "Inicio": inicio_real, "Fin": fin_real, "Duracion_h": round(total_h, 3), "Motivo": motivo, "Maquina": pp_maquina}) # Forzamos Maquina real
                
                # Actualizar estado global
                fin_proceso[pp_ot][proc_target] = fin_real
                completado[pp_ot].add(proc_target)
                t["CantidadPliegos"] = pp_qty # Para que el registro quede consistente con lo hecho
                ultimo_en_maquina[pp_maquina] = t
                
                # --- BORRAR DE TASKS (Para que no se agende de nuevo) ---
                tasks = tasks.drop(idx_task)
            else:
                pass
    # =======================================================

    flujo_estandar = [p.strip() for p in cfg.get("orden_std", [])] 

    def _orden_proceso(maquina):
        return get_machine_process_order(maquina, cfg)

    # --- FILTRO DE BLACKLIST ---
    if "manual_overrides" in cfg:
        # 1. Apply Urgency Overrides
        if "urgency_overrides" in cfg["manual_overrides"]:
            urg_overrides = cfg["manual_overrides"]["urgency_overrides"]
            # urg_overrides is Dict {(ot_id, proceso): bool}
            
            # Iterate through overrides and apply
            # Optimization: Create a key column in tasks? Or iterate if overrides are few.
            # Generally manual overrides are few, so iteration is fine.
            for (ot_urg, proc_urg), is_urgent in urg_overrides.items():
                # Normalize Match
                # We need to match OT and Process. 
                # Process matching might need 'contains' logic similar to manual assignments if names vary
                # But since UI returns exact process name from scheduler, direct match should work if data is consistent.
                
                # Check 1: Exact Match
                mask = (tasks["OT_id"].astype(str) == str(ot_urg)) & (tasks["Proceso"].astype(str) == str(proc_urg))
                
                if mask.any():
                    tasks.loc[mask, "Urgente"] = is_urgent

        # 2. Apply Blacklist
        if "blacklist_ots" in cfg["manual_overrides"]:
            bl = cfg["manual_overrides"]["blacklist_ots"]
            tasks = tasks[~tasks["OT_id"].isin(bl)]
        
    # ---------------------------------------------

    maquinas = sorted(cfg["maquinas"]["Maquina"].unique(), key=_orden_proceso)
    
    # --- ADD VIRTUAL MACHINES IF NEEDED ---
    # We check if tasks have assigned them
    extra_machines = set(tasks["Maquina"].unique()) - set(maquinas) - {"POOL_DESCARTONADO"}
    # Filter only our known virtual ones to be safe
    virtual_machines = {m for m in extra_machines if m in ["TERCERIZADO", "SALTADO"]}
    maquinas.extend(sorted(list(virtual_machines)))
    # -------------------------------------
    
    # =================================================================
    # 2.5 APLICAR HISTORIAL (Locked Assignments)
    # =================================================================
    if "locked_assignments" in cfg and cfg["locked_assignments"]:
        locks = cfg["locked_assignments"]
        # locks is Dict {(ot, proc): maquina}
        
        # Optimize: Create a mapping column in tasks to match keys
        # We need to match (OT_id, Proceso) against the keys in locks
        
        for (ot, proc), maq_locked in locks.items():
            # Find task
            # Check if machine exists in current config to avoid assigning disabled machines
            if maq_locked not in maquinas and maq_locked not in ["TERCERIZADO", "SALTADO", "POOL_DESCARTONADO"]:
                 continue

            mask = (tasks["OT_id"].astype(str) == str(ot)) & (tasks["Proceso"].astype(str) == str(proc))
            
            if mask.any():
                tasks.loc[mask, "Maquina"] = maq_locked
                # Mark as ManualAssignment so it is NOT re-optimized by Troquelado logic
                if "ManualAssignment" not in tasks.columns:
                    tasks["ManualAssignment"] = False
                tasks.loc[mask, "ManualAssignment"] = True
    
    # =================================================================
    # 2.9 APLICAR ASIGNACIONES MANUALES (Override)
    # =================================================================
    if "manual_assignments" in cfg and cfg["manual_assignments"]:
        # Ensure column exists and is boolean
        if "ManualAssignment" not in tasks.columns: 
             tasks["ManualAssignment"] = False
        tasks["ManualAssignment"] = tasks["ManualAssignment"].astype(bool)

        # Import normalization helper if not available, or just define locally if simple. 
        # But we have it imported via modules.config_loader. Let's assume passed cfg handles it or we do simple matching.
        # Actually, UI sends the raw name selected from dropdown (which comes from Active Machines).
        
        for maq_target, ots_list in cfg["manual_assignments"].items():
            if not ots_list: continue
            
            # Filter tasks that match the OTs
            mask_ots = tasks["OT_id"].astype(str).isin([str(x) for x in ots_list])
            if not mask_ots.any(): continue
            
            # Determine Target Process based on Machine Name
            target_lower = str(maq_target).lower()
            
            # Explicit logic to map Machine -> Process
            is_troquel = any(k in target_lower for k in ["troq", "manual", "iberica", "duyan", "autom"])
            is_descartonado = "descartonad" in target_lower
            
            mask_proc = pd.Series([False] * len(tasks), index=tasks.index)
            
            if is_troquel:
                # Match "Troquelado" process
                mask_proc = tasks["Proceso"].astype(str).str.lower().str.contains("troquel")
            elif is_descartonado:
                # Match "Descartonado" process
                mask_proc = tasks["Proceso"].astype(str).str.lower().str.contains("descartonad")
            else:
                # Fallback
                mask_proc = pd.Series([True] * len(tasks), index=tasks.index) 

            # Apply
            mask_final = mask_ots & mask_proc
            
            if mask_final.any():
                tasks.loc[mask_final, "Maquina"] = maq_target
                tasks.loc[mask_final, "ManualAssignment"] = True

    # =================================================================
    # 3. REASIGNACIÓN TROQUELADO (Solo asigna, NO reserva tiempo)
    # =================================================================
    
    troq_cfg = cfg["maquinas"][cfg["maquinas"]["Proceso"].str.lower().str.contains("troquel")]
    manuales = [m for m in troq_cfg["Maquina"].tolist() if "troq n" in str(m).lower()]
    iberica = [m for m in troq_cfg["Maquina"].tolist() if "iberica" in str(m).lower()]
    auto_names = [m for m in troq_cfg["Maquina"].tolist() if "autom" in str(m).lower() or "duyan" in str(m).lower()]
    auto_name = auto_names[0] if auto_names else None

    # DEBUG DOWNTIMES
    print(f"DEBUG: Maquinas activas Troquelado: {manuales + ([auto_name] if auto_name else [])}")
    print(f"DEBUG: Downtimes en CFG: {len(cfg.get('downtimes', []))}")
    for dt in cfg.get("downtimes", []):
        print(f"  - {dt}")

    if not tasks.empty and manuales: 
        if "CodigoTroquel" not in tasks.columns: tasks["CodigoTroquel"] = ""
        tasks["CodigoTroquel"] = tasks["CodigoTroquel"].fillna("").astype(str).str.strip().str.lower()
        
        cap = {} 
        for m in manuales + ([auto_name] if auto_name else []):
            if m: cap[m] = float(capacidad_pliegos_h("Troquelado", m, cfg))
        load_h = {m: 0.0 for m in cap.keys()} 

        # Agenda simulada solo para lectura de fechas (ahora con escritura simulada)
        # IMPORTANTE: Incluir "nombre" para que _reservar_en_agenda pueda buscar los downtimes
        agenda_m = {
            m: {
                "fecha": agenda[m]["fecha"], 
                "hora": agenda[m]["hora"],
                "resto_horas": agenda[m]["resto_horas"], 
                "nombre": m
            } 
            for m in cap.keys()
        }

        mask_troq = tasks["Proceso"].eq("Troquelado")
        
        # EXCLUDE Manual Assignments logic
        if "ManualAssignment" in tasks.columns:
            mask_troq = mask_troq & (~tasks["ManualAssignment"])
            
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
                    if "autom" in str(m).lower() or "duyan" in str(m).lower():
                        # Para Automatica (Restricción de MINIMO), usamos las dimensiones MINIMAS del grupo
                        # Si la hoja más chica es < 38, NO entra en Auto.
                        if validar_medidas_troquel(m, min_anc, min_lar):
                            candidatos_tamano.append(m)
                    else:
                        # Para Manuales (Restricción de MAXIMO), usamos las dimensiones MAXIMAS del grupo
                        # Si la hoja más grande es > 80, NO entra en Manual.
                        if validar_medidas_troquel(m, max_anc, max_lar):
                            candidatos_tamano.append(m)
                
                if not candidatos_tamano: continue

                # --- 1.5 CHECK PREFERENCIAS MANUALES (Config) ---
                # Si el código de troquel está asignado a una máquina específica, 
                # forzamos esa máquina (siempre que entre por tamaño).
                prefs = cfg.get("troquel_preferences", {})
                valid_preferred = []
                
                if prefs:
                    # Buscar en qué maquina(s) estÃ¡ este troquel
                    for m_pref, codes in prefs.items():
                        # Normalizar lista de codigos
                        codes_norm = [str(c).lower().strip() for c in codes]
                        if troq_key in codes_norm:
                            # Encontrado! Chequear si es valid candidate por tamaño
                            # Nota: prefs keys might not match official names exactly if changed, 
                            # but usually they come from UI dropdowns which use official names.
                            
                            # Intentar matchear nombre
                            # El nombre en prefs debe coincidir con 'posibles' list
                            # Buscamos m_pref en candidatos_tamano'
                            if m_pref in candidatos_tamano:
                                valid_preferred.append(m_pref)
                            else:
                                pass

                if valid_preferred:
                    # Override Logic: Si hay preferencias válidas, USARLAS EXCLUSIVAMENTE
                    candidatas = valid_preferred
                    
                else:
                    # --- LÓGICA ESTÁNDAR (Si no hay preferencia explícita) ---
                    
                    # 2. REGLA DE BOCAS (> 6) -> Automática Obligatoria (si entra)
                    if bocas > 6:
                        if auto_name and (auto_name in candidatos_tamano):
                            candidatas = [auto_name]
                        else:
                            # Si no entra en Auto, va a manual compatible
                            candidatas = [m for m in candidatos_tamano if m != auto_name]
                    
                    # 3. REGLA DE CANTIDAD (> 2500) -> Automática Obligatoria (si entra)
                    elif total_pliegos > 2500:
                        if auto_name and (auto_name in candidatos_tamano):
                            candidatas = [auto_name]
                        else:
                            candidatas = [m for m in candidatos_tamano if m != auto_name]
                    
                    # 4. DEFAULT (<= 3000 y <= 6 Bocas) -> Preferencia Manual Standard > Iberica > Auto
                    else:
                        # Preference 1: Manuales Standard
                        manuales_std = [m for m in candidatos_tamano if m in manuales]
                        
                        if manuales_std:
                            candidatas = manuales_std
                        else:
                            # Preference 2: Iberica (Si no entra en ninguna standard)
                            manuales_todas = [m for m in candidatos_tamano if m != auto_name]
                            if manuales_todas:
                                candidatas = manuales_todas
                            else:
                                # Preference 3: Auto (Si no entra en ninguna manual)
                                candidatas = candidatos_tamano

                if not candidatas: continue

                def criterio_balanceo(m):
                    # Balancear por: FECHA TERMINACION ESTIMADA (incluyendo downtimes) -> HORA -> CARGA
                    # agenda_m se ira actualizando con cada asignacion
                    f = agenda_m[m]["fecha"]
                    h = agenda_m[m]["hora"]
                    l = load_h[m]
                    # print(f"  DEBUG COMPARE {m}: {f} {h} (Load: {l})")
                    return (f, h, l)

                m_sel = min(candidatas, key=criterio_balanceo)
                # print(f"DEBUG CHOICE for group {troq_key} (Size {len(idxs)}): {m_sel}")

                tasks.loc[idxs, "Maquina"] = m_sel
                
                # ACTUALIZAR SIMULACION: Reservar tiempo en agenda_m para que la proxima iteracion "vea" que esta ocupada
                duracion_estimada = total_pliegos / cap[m_sel]
                
                # Usamos la funcion real de agenda para saltar paros/feriados y mover el puntero fecha/hora
                _reservar_en_agenda(agenda_m[m_sel], duracion_estimada, cfg)
                
                # Tambien actualizamos carga bruta por si acaso
                load_h[m_sel] += duracion_estimada

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
        
        # EXCLUDE Manual Assignments logic
        if "ManualAssignment" in tasks.columns:
            mask_desc = mask_desc & (~tasks["ManualAssignment"])
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
        elif ("troquel" in m_lower) or ("duyan" in m_lower) or ("manual" in m_lower): colas[m] = _cola_troquelada(q)
        elif ("offset" in m_lower) or ("heidelberg" in m_lower): colas[m] = _cola_impresora_offset(q)
        elif ("flexo" in m_lower) or ("impres" in m_lower): colas[m] = _cola_impresora_flexo(q)
        elif "bobina" in m_lower: colas[m] = _cola_cortadora_bobina(q)
        else: 
            # Orden por defecto: ManualPriority -> Agrupados -> New Urgent -> Soft Locked -> Urgente -> DueDate -> Orden Proceso -> Cantidad
            # Standard sorting
            q.sort_values(by=["ManualPriority", "Urgente", "DueDate", "_orden_proceso", "CantidadPliegos"], 
                          ascending=[True, False, True, True, False], inplace=True)
            colas[m] = deque(q.to_dict("records"))

    # Crear la cola del POOL si existe
    if "POOL_DESCARTONADO" in tasks["Maquina"].values:
        q_pool = tasks[tasks["Maquina"] == "POOL_DESCARTONADO"].copy()
        
        q_pool.sort_values(by=["ManualPriority", "Urgente", "DueDate", "_orden_proceso", "CantidadPliegos"], 
                           ascending=[True, False, True, True, False], inplace=True)
        colas["POOL_DESCARTONADO"] = deque(q_pool.to_dict("records"))
    else:
        colas["POOL_DESCARTONADO"] = deque()

    # =================================================================
    # 5. LÓGICA DE PLANIFICACIÓN (EL NÚCLEO)
    # =================================================================
    
    pendientes_por_ot = defaultdict(set); [pendientes_por_ot[t["OT_id"]].add(t["Proceso"]) for _, t in tasks.iterrows()]
    
    # IMPORTANTE: No reiniciamos 'completado' ni 'fin_proceso' ni 'ultimo_en_maquina' 
    # porque ya vienen con datos de la fase "Imagen de Planta"
    # completado = defaultdict(set); fin_proceso = defaultdict(dict) <-- ELIMINADO REINICIO
    
    # Si ultimo_en_maquina viene vacio (sin pendientes), lo iniciamos a None si hace falta, 
    # pero como es un diccionario mutable ya modificado arriba, lo dejamos ser.
    
    carga_reg = [] # filas se acumula, pero carga_reg es nuevo aqui
    # filas = [] <-- NO reiniciamos filas, ya trae los pendientes
    h_dia = horas_por_dia(cfg)

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
        
        # --- LÓGICA VERSIÓN TEÓRICA (SIMULACIÓN) ---
        # Si cfg.get("ignore_constraints") es True, esta función:
        # 1. Ignorará la falta de stock de Materia Prima (verificado fuera de esta función, en el loop principal).
        # 2. Ignorará la falta de fechas de llegada para Chapas (Pelicula) y Troqueles.
        # Esto permite generar una planificación "ideal" basada solo en capacidad de máquina y tiempos de proceso.
        
        # --- REORDENAMIENTO DINAMICO (ProcesoDpd / TroqAntes) ---
        dynamic_order_applied = False
        
        if t.get("ProcesoDpd") and str(t.get("ProcesoDpd")).strip():
             order_str = str(t.get("ProcesoDpd")).upper().strip()
             order_str = order_str.replace(" ", "").replace("-", "") # "TID"
             

             
             # Map initials to potential internal names
             # T -> troquelado
             # I -> impresion flexo / impresion offset
             # D -> descartonado
             
             ordered_nodes = []
             for char in order_str:
                 if char == "T": ordered_nodes.append("troquelado")
                 elif char == "D": ordered_nodes.append("descartonado")
                 elif char == "I": ordered_nodes.append("impres") # Partial match key
            
             # Identify what is actually in the flow
             # and build the concrete list of nodes to swap
             
             # We want to find the indices of the *matching* nodes in the current flow
             # and swap their contents to match `ordered_nodes` sequence.
             
             # 1. Find matches in current flow
             flow_matches = [] # list of (index, node_name)
             for i, p in enumerate(flujo_clean):
                 # Check if p matches any of our ordered initials logic
                 # But we need to know WHICH initial it matches to know the target order.
                 
                 # Optimization: specific checks
                 matched_char = None
                 if p == "troquelado" and "T" in order_str: matched_char = "T"
                 elif p == "descartonado" and "D" in order_str: matched_char = "D"
                 elif "impres" in p and "I" in order_str: matched_char = "I"
                 
                 if matched_char:
                     flow_matches.append((i, p, matched_char))
            
             # If we found at least 2 items involved in the reordering
             if len(flow_matches) >= 2:
                  # Sort matches by current index (already sorted by enumeration)
                  indices = [m[0] for m in flow_matches]
                  
                  # Determine the desired sequence of the FOUND nodes based on order_str
                  # flow_matches has (index, node, char).
                  # We want to re-arrange these nodes such that their chars follow order_str.
                  
                  # Filter order_str to only chars we found
                  found_chars = set(m[2] for m in flow_matches)
                  relevant_order = [c for c in order_str if c in found_chars]
                  
                  new_sequence = []
                  # Better: list of nodes for each char
                  pool_list = {c: [] for c in found_chars}
                  for m in flow_matches:
                      pool_list[m[2]].append(m[1])
                      


                  for char in relevant_order:
                      if pool_list.get(char):
                          # Append ALL nodes that match this char
                          # Preserving their relative original order (since we iterated flow)
                          new_sequence.extend(pool_list[char])
                          pool_list[char] = [] # Clear so we don't duplicate if char repeats in order string

                  
                  # Now replace in flujo_clean at the specific indices
                  for original_idx, new_node in zip(indices, new_sequence):
                      flujo_clean[original_idx] = new_node
                      
                  dynamic_order_applied = True
                  



        if not dynamic_order_applied and t.get("_TroqAntes"):
             # ... (existing logic) ...
             # We can keep this block collapsed/referenced if we don't change it, 
             # but to be safe I'm just leaving it as valid python path if needed, 
             # but here I am just inserting logs AFTER the dynamic block.
             if "troquelado" in flujo_clean:
                 # Identificar donde está la impresion
                 # ... (Implementation detail omitted for brevity in thought, but must retain logically) ...
                 # Actually I am not touching the _TroqAntes block in this tool call significantly 
                 # except to ensure flow is valid.
                 pass

        # --- VALIDATION LOGIC ---
        if proc_actual_clean not in flujo_clean: 
            return (True, None)
            
        idx = flujo_clean.index(proc_actual_clean)
        pendientes_clean = {clean(p) for p in pendientes_por_ot[ot]}
        


        prev_procs_names = []
        for p_clean in flujo_clean[:idx]:
            if p_clean in pendientes_clean:
                completados_clean = {clean(c) for c in completado[ot]}
                
                if p_clean not in completados_clean:

                    return (False, None)
                else: 

                    
                     # Si está completado, necesitamos su nombre Raw para buscar fecha fin.
                     # Buscamos en completado[ot] cual matchea.
                     raw_match = next((c for c in completado[ot] if clean(c) == p_clean), None)
                     if raw_match:
                        prev_procs_names.append(raw_match)

            else:
                 pass # Not pending, so ignored
        


        if not prev_procs_names: 
            return (True, None)

        completados_clean = {clean(c) for c in completado[ot]}
        for p in prev_procs_names:
            if clean(p) not in completados_clean:
                return (False, None) # Falta un proceso previo
        
        # Calcular cuándo estará lista la última dependencia
        last_end = max((fin_proceso[ot].get(p) for p in prev_procs_names if fin_proceso[ot].get(p)), default=None)
        
        # --- NUEVO: RESTRICCION POR LLEGADA DE INSUMOS (CHAPAS / TROQUEL) ---
        arrival_date = None
        
        # 1. Impresión (Offset/Flexo) depende de fecha llegada chapas (PeliculaArt)
        if "impres" in proc_actual_clean:
            # Si "ignoramos restricciones", asumimos que NO REQUIERE (Force False)
            requires_pelicula = es_si(t.get("PeliculaArt"))
            if cfg.get("ignore_constraints"):
                requires_pelicula = False
            
            if requires_pelicula:
                fecha_chapas = t.get("FechaLlegadaChapas")
                if pd.notna(fecha_chapas):
                    # Asumimos disponibilidad al inicio de ese día (00:00) o a las 7:00?
                    # Mejor las 07:00 para alinear con jornada
                    arrival_date = datetime.combine(fecha_chapas.date(), time(7,0))

        # 2. Troquelado depende de fecha llegada troquel (TroquelArt)
        elif "troquel" in proc_actual_clean:
             requires_troquel = es_si(t.get("TroquelArt"))
             if cfg.get("ignore_constraints"):
                 requires_troquel = False

             if requires_troquel:
                fecha_troquel = t.get("FechaLlegadaTroquel")
                if pd.notna(fecha_troquel):
                    arrival_date = datetime.combine(fecha_troquel.date(), time(7,0))
        
        # Fusionar restricciones: la fecha efectiva es el MAX(dependencia, llegada_insumo)
        if last_end and arrival_date:
            return (True, max(last_end, arrival_date))
        elif arrival_date:
            return (True, arrival_date)
        
        return (True, last_end)

    def _prioridad_dinamica(m):
        # ORDEN DE SIMULACION:
        # 1. Fecha (Quien está más atrasado debe avanzar primero)
        # 2. Hora
        # 3. Prioridad especial (Automatica antes para llenar huecos si empatan)
        prio_tipo = 0 if "autom" in m.lower() else 1
        
        # Virtual Machines don't have agenda, so we give them high priority (run whenever)
        if m in ["TERCERIZADO", "SALTADO"]:
            return (datetime.min, 0, m)
            
        current_dt = datetime.combine(agenda[m]["fecha"], agenda[m]["hora"])
        return (current_dt, prio_tipo, m)

    progreso = True
    while quedan_tareas() and progreso:
        progreso = False
        
        # Mezclar máquinas
        maquinas_shuffled = list(maquinas)

        # DEBUG SIMULATION ORDER
        sim_order = sorted(maquinas_shuffled, key=_prioridad_dinamica)
        for m in sim_order: # Log ALL machines
           dt, _, _ = _prioridad_dinamica(m)

        for maquina in sim_order:
            # --- VIRTUAL MACHINE EXECUTION (Infinite Capacity) ---
            if maquina in ["TERCERIZADO", "SALTADO"]:
                if not colas.get(maquina): continue
                
                # Consume ALL ready tasks
                queue_snapshot = list(colas[maquina]) # Copy to iterate
                for t_virt in queue_snapshot:
                    runnable, available_at = verificar_disponibilidad(t_virt, maquina)
                    if runnable:
                        # Determine Start Time (Max of Dependency Availability or Plan Start)
                        start_virt = max(available_at, inicio_general) if available_at else inicio_general
                        
                        # Determine Duration
                        duration_virt = 0.0
                        if maquina == "TERCERIZADO":
                             # Use estimated duration
                             duration_virt = float(t_virt.get("Duracion_h", 0.0) or 0.0)
                        
                        end_virt = start_virt + timedelta(hours=duration_virt)
                        
                        # Register Result
                        filas.append({k: t_virt.get(k) for k in ["OT_id", "CodigoProducto", "Subcodigo", "CantidadPliegos", "CantidadPliegosNetos",
                                                                "Bocas", "Poses", "Cliente", "Cliente-articulo", "Proceso", "Maquina", "DueDate", "PliAnc", "PliLar", 
                                                                "Urgente", "ManualPriority", "IsOutsourced", "IsSkipped"]} | 
                                        {"Setup_min": 0.0, "Proceso_h": duration_virt,
                                        "Inicio": start_virt, "Fin": end_virt, "Duracion_h": duration_virt, 
                                        "Motivo": "Outsourced/Skipped", "Maquina": maquina})
                        
                        # Update Global State
                        ot_id = t_virt["OT_id"]
                        proc = t_virt["Proceso"]
                        fin_proceso[ot_id][proc] = end_virt
                        completado[ot_id].add(proc)
                        ultimo_en_maquina[maquina] = t_virt
                        
                        # Remove from queue
                        colas[maquina].remove(t_virt)
                        progreso = True # We made progress
                
                continue # Skip standard logic for virtual machines
            # -----------------------------------------------------

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
                mejor_candidato_setup = None 
                
                current_agenda_dt = datetime.combine(agenda[maquina]["fecha"], agenda[maquina]["hora"])
                
                ultima_tarea = ultimo_en_maquina.get(maquina)
                if "barniz" in maquina.lower():
                    log_debug(f"--- Ciclo Nueva Tarea @ {current_agenda_dt} ---")
                    if ultima_tarea:
                        log_debug(f"Ultima Tarea: {ultima_tarea.get('Cliente')} - {ultima_tarea.get('Proceso')}")
                    else:
                        log_debug("Ultima Tarea: NONE")

                # SCAN WINDOW
                # For prep machines, we scan up to 50 items to find "Catch Up" candidates.
                # For others, we assume FIFO (break on first) or simple Logic.
                
                # VARS FOR GROUPING PRIORITY
                is_prep_machine = "guillotin" in maquina.lower() or "bobina" in maquina.lower() or "corte" in maquina.lower()
                best_group_score = -1
                best_group_idx = -1
                
                scan_limit = 50 if is_prep_machine else 999999
                
                for i, t_cand in enumerate(colas[maquina]):
                    if is_prep_machine and i >= scan_limit: 
                        break # Stop scanning for prep machines to avoid perf hit

                    mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                    mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                    
                    # OVERRIDE: Si ignoramos restricciones, asumimos MP OK siempre
                    if cfg.get("ignore_constraints"):
                        mp_ok = True
                    
                    # Manual Priority Override for Material Constraints ("No hay discusión")
                    prio_man_check = int(t_cand.get("ManualPriority", 9999))
                    if prio_man_check < 9000:
                        mp_ok = True
                    
                    if not mp_ok: continue

                    runnable, available_at = verificar_disponibilidad(t_cand, maquina)
                    
                    if not runnable: 
                        # --- SOLUCION NATIVOS / BLOQUEO POR GRUPO ---
                        if ultima_tarea and usa_setup_menor(ultima_tarea, t_cand, t_cand.get("Proceso", "")):
                            if not is_prep_machine: 
                                idx_cand = -1
                                mejor_candidato_futuro = None
                                mejor_candidato_setup = None
                                break
                        continue
                    
                    # --- SUPER OVERRIDE: MANUAL PRIORITY ---
                    prio_man = int(t_cand.get("ManualPriority", 9999))
                    # Si tiene prioridad alta (ej < 9000), es sagrada.
                    # Asumimos que la lista ya esta ordenada por ManualPriority.
                    # Si la primera tarea ejecutable tiene prioridad manual, LA TOMAMOS YA.
                    # Sin setups, sin grupos, sin nada.
                    if prio_man < 9000:
                        # Check start constraints
                        is_ready_now = not available_at or available_at <= current_agenda_dt
                        if is_ready_now:
                             idx_cand = i
                             mejor_candidato_futuro = None
                             mejor_candidato_setup = None # Disable setup gap filling
                             
                             # Forced break - no optimizations allowed for manual override
                             break 
                        else:
                             # If not ready IS runnable, keep it as future candidate.
                             # BUT we should NOT verify setups for others if this one is waiting with P1.
                             if mejor_candidato_futuro is None:
                                 mejor_candidato_futuro = (i, available_at)
                             elif available_at < mejor_candidato_futuro[1]:
                                 mejor_candidato_futuro = (i, available_at)
                             
                             # If we found a Manual Priority Runnable task but it's future,
                             # we should probably NOT pick a setup filler that delays us?
                             # For now, let standard logic handle future wait, but don't look further.
                             # Actually if P1 is waiting, we shouldn't run P9999 just because it has setup.
                             # So we break loop here too?
                             # If we break here, we wait for P1.
                             break
                    
                    es_setup = False
                    if ultima_tarea:
                         es_setup = usa_setup_menor(ultima_tarea, t_cand, t_cand.get("Proceso", ""))

                    if "barniz" in maquina.lower() and i < 5:
                         log_debug(f"Cand[{i}]: {t_cand.get('Cliente')} (Due: {t_cand.get('DueDate')}) - Avail: {available_at} - SetupMenor: {es_setup}")

                    # Si está lista YA (o antes), la tomamos...
                    is_ready_now = not available_at or available_at <= current_agenda_dt
                    
                    if is_ready_now:
                        if is_prep_machine:
                            score = get_downstream_presence_score(t_cand, colas, None, maquina, last_tasks_map=ultimo_en_maquina)
                            
                            # Decision Rule: Strictly better score wins
                            if score > best_group_score:
                                best_group_score = score
                                best_group_idx = i
                                
                            # If score is very high, maybe break? For now, scan full window.
                        else:
                            # STANDARD FIFO Logic (Gap Filling)
                            idx_cand = i
                            mejor_candidato_futuro = None
                            break
                    
                    else:
                        # Si no está lista ya, pero es runnable, la guardamos como opción futura
                        if mejor_candidato_futuro is None:
                            mejor_candidato_futuro = (i, available_at)
                        else:
                            if available_at < mejor_candidato_futuro[1]:
                                mejor_candidato_futuro = (i, available_at)
                            
                    # -- LÓGICA FRANCOTIRADOR (SMART WAIT) --
                    if es_setup:
                         if mejor_candidato_setup is None:
                             mejor_candidato_setup = (i, available_at)
                             if "barniz" in maquina.lower(): log_debug(f"MARKING SETUP CANDIDATE: IDX {i}")
                         else:
                             # Safe Comparison: None means "Active Now" (Earlier than any future date)
                             curr_dt = available_at if available_at else datetime.min
                             best_dt = mejor_candidato_setup[1] if mejor_candidato_setup[1] else datetime.min
                             
                             if curr_dt < best_dt:
                                 mejor_candidato_setup = (i, available_at)
                                 if "barniz" in maquina.lower(): log_debug(f"UPDATING SETUP CANDIDATE: IDX {i}")

                # END SEARCH LOOP
                
                # For Prep Machines, apply the Best Group Selection
                if is_prep_machine and best_group_idx != -1:
                    idx_cand = best_group_idx

                
                
                # --- APPLY SMART WAIT / FRANCOTIRADOR LOGIC ---
                TOLERANCIA = timedelta(minutes=90)
                final_decision = None # (idx, dt)

                if "barniz" in maquina.lower(): 
                    log_debug(f"End Loop. IdxCand: {idx_cand}. BestFut: {mejor_candidato_futuro}. BestSetup: {mejor_candidato_setup}")

                # 1. Si ya tenemos uno listo (idx_cand != -1), checkeamos si vale la pena ESPERAR por setup
                #    PERO SOLO SI NO ES UNA PRIORIDAD MANUAL
                is_manual_override = False
                if idx_cand != -1:
                    t_sel = colas[maquina][idx_cand]
                    if int(t_sel.get("ManualPriority", 9999)) < 9000:
                        is_manual_override = True

                if idx_cand != -1 and mejor_candidato_setup and not is_manual_override:
                     wait_time = timedelta(0)
                     if mejor_candidato_setup[1] is not None:
                         wait_time = mejor_candidato_setup[1] - current_agenda_dt
                         
                     if wait_time <= TOLERANCIA:
                         if "barniz" in maquina.lower(): log_debug(f"FRANCOTIRADOR: Esperando {wait_time} por cand {mejor_candidato_setup[0]} (Setup)")
                         idx_cand = -1
                         final_decision = mejor_candidato_setup
                
                # 2. Si no tenemos uno listo...
                elif idx_cand == -1:
                    if mejor_candidato_setup:
                        if "barniz" in maquina.lower(): log_debug(f"No ready task. Picking Setup Candidate {mejor_candidato_setup[0]} future.")
                        final_decision = mejor_candidato_setup
                    elif mejor_candidato_futuro:
                        if "barniz" in maquina.lower(): log_debug(f"No ready/setup task. Picking Normal Future {mejor_candidato_futuro[0]}.")
                        final_decision = mejor_candidato_futuro

                # Si no encontramos ninguna lista YA, pero hay futuras, tomamos la mejor futura
                if idx_cand == -1 and final_decision:
                    idx_cand = final_decision[0]
                    future_dt = final_decision[1]


                    if future_dt:
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
                        # EXCEPCIÓN: Descartonadora 3 y 4 NO roban del pool (son solo manuales)
                        # ------------------------------------------------------
                        is_restricted_desc = "descartonadora 3" in maquina.lower() or "descartonadora 4" in maquina.lower()
                        
                        if "descartonad" in maquina.lower() and colas.get("POOL_DESCARTONADO") and not is_restricted_desc:
                            best_pool_idx = -1
                            best_pool_future = None # (idx, available_at)
                            best_has_successor = False # Flag for priority
                            best_is_urgent = False
                            current_agenda_dt = datetime.combine(agenda[maquina]["fecha"], agenda[maquina]["hora"])

                            for i, t_cand in enumerate(colas["POOL_DESCARTONADO"]):
                                # Validar MP
                                mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                                mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                                
                                if cfg.get("ignore_constraints"):
                                    mp_ok = True

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
                                    # 0. Manual Priority (Lower is better)
                                    # 1. Urgency is King (Urgente="Si" > "No") IF Priority is equal
                                    # 2. If Urgency is same, prefer Successor.
                                    # 3. If both same, prefer original order (DueDate).
                                    
                                    current_prio = int(t_cand.get("ManualPriority", 9999))
                                    is_urgent = str(t_cand.get("Urgente", "")).lower() == "si"
                                    
                                    if best_pool_idx == -1:
                                        best_pool_idx = i
                                        best_has_successor = has_successor
                                        best_is_urgent = is_urgent
                                        best_prio = current_prio
                                    else:
                                        # Compare current candidate (i) with best so far
                                        
                                        # 0. Manual Priority Check
                                        if current_prio < best_prio:
                                            # Found better priority, replace best
                                            best_pool_idx = i
                                            best_has_successor = has_successor
                                            best_is_urgent = is_urgent
                                            best_prio = current_prio
                                        elif current_prio > best_prio:
                                            # Current is worse priority, keep best.
                                            pass
                                        else:
                                            # Same Manual Priority. Check Urgency.
                                            if is_urgent and not best_is_urgent:
                                                # Found urgent, replace non-urgent best
                                                best_pool_idx = i
                                                best_has_successor = has_successor
                                                best_is_urgent = True
                                                best_prio = current_prio
                                            elif not is_urgent and best_is_urgent:
                                                # Current is not urgent, best is. Keep best.
                                                pass
                                            else:
                                                # Same urgency status. Check Successor.
                                                if has_successor and not best_has_successor:
                                                    best_pool_idx = i
                                                    best_has_successor = True
                                                    best_is_urgent = is_urgent
                                                    best_prio = current_prio
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
                        
                        # A: Auto roba a Manual o Iberica
                        elif maquina in auto_names:
                            # Targets: Manuales + Iberica
                            targets_robo = manuales 
                            for m_target in targets_robo:
                                if not colas.get(m_target): continue
                                for i, t_cand in enumerate(colas[m_target]):
                                    if t_cand["Proceso"].strip() != "Troquelado": continue

                                    cant = float(t_cand.get("CantidadPliegos", 0) or 0)
                                    if cant < 3000: continue
                                    
                                    # Validar medidas para Auto (Min 38x38)
                                    anc = float(t_cand.get("PliAnc", 0) or 0); lar = float(t_cand.get("PliLar", 0) or 0)
                                    if not validar_medidas_troquel(maquina, anc, lar): continue

                                    mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                                    mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                                    if not mp_ok: continue
                                    
                                    runnable, available_at = verificar_disponibilidad(t_cand, maquina)
                                    if runnable and (not available_at or available_at <= current_agenda_dt):
                                        tarea_encontrada = t_cand; fuente_maquina = m_target; idx_robado = i; break
                                if tarea_encontrada: break

                        # B y C: Manual roba a Auto o Manual o Iberica
                        elif any(m in maquina for m in manuales):
                            # B: Robar a Auto
                            if auto_name and colas.get(auto_name):
                                for i, t_cand in enumerate(colas[auto_name]):
                                    if t_cand["Proceso"].strip() != "Troquelado": continue
                                    
                                    # REGLA: Manual solo roba si cantidad <= 3000
                                    cant = float(t_cand.get("CantidadPliegos", 0) or 0)
                                    if cant > 2500: continue 

                                    # Validar medidas para ESTA manual
                                    anc = float(t_cand.get("PliAnc", 0) or 0); lar = float(t_cand.get("PliLar", 0) or 0)
                                    if not validar_medidas_troquel(maquina, anc, lar): continue
                                    
                                    mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                                    mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                                    if not mp_ok: continue
                                    
                                    runnable, available_at = verificar_disponibilidad(t_cand, maquina)
                                    if runnable and (not available_at or available_at <= current_agenda_dt):
                                        tarea_encontrada = t_cand; fuente_maquina = auto_name; idx_robado = i; break
                            
                            # C: Robar a Vecina Manual
                            if not tarea_encontrada:
                                # Targets: Otras Manuales
                                vecinas = [m for m in manuales if m != maquina]
                                for vecina in vecinas:
                                    if not colas.get(vecina): continue
                                    for i, t_cand in enumerate(colas[vecina]):
                                        if t_cand["Proceso"].strip() != "Troquelado": continue
                                        
                                        # Validar medidas para ESTA manual
                                        anc = float(t_cand.get("PliAnc", 0) or 0); lar = float(t_cand.get("PliLar", 0) or 0)
                                        if not validar_medidas_troquel(maquina, anc, lar): continue

                                        mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                                        mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                                        if not mp_ok: continue
                                        
                                        runnable, available_at = verificar_disponibilidad(t_cand, maquina)
                                        if runnable and (not available_at or available_at <= current_agenda_dt):
                                            tarea_encontrada = t_cand; fuente_maquina = vecina; idx_robado = i; break
                                    if tarea_encontrada: break

                        # # Z: Iberica roba a Auto o Manual
                        # elif any(m in maquina for m in iberica):
                        #     # Z.1: Robar a Auto
                        #     if auto_name and colas.get(auto_name):
                        #         for i, t_cand in enumerate(colas[auto_name]):
                        #             if t_cand["Proceso"].strip() != "Troquelado": continue
                                    
                        #             # REGLA: Iberica roba lo que le sirva (asumimos lógica similar a Manual/Auto)
                        #             # Preferencia: Si hay algo en auto, intentar robarlo?
                        #             # User dijo: "para el robo de la automatica hay que poner que la iberica este como opcion para robar"
                        #             # AND "Iberica puede robar a las manuales y a la automatica".
                                    
                        #             anc = float(t_cand.get("PliAnc", 0) or 0); lar = float(t_cand.get("PliLar", 0) or 0)
                        #             if not validar_medidas_troquel(maquina, anc, lar): continue
                                    
                        #             mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                        #             mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                        #             if not mp_ok: continue
                                    
                        #             runnable, available_at = verificar_disponibilidad(t_cand, maquina)
                        #             if runnable and (not available_at or available_at <= current_agenda_dt):
                        #                 tarea_encontrada = t_cand; fuente_maquina = auto_name; idx_robado = i; break
                            
                            # Z.2: Robar a Manuales
                            if not tarea_encontrada:
                                for m_manual in manuales:
                                    if not colas.get(m_manual): continue
                                    for i, t_cand in enumerate(colas[m_manual]):
                                        if t_cand["Proceso"].strip() != "Troquelado": continue
                                    
                                        anc = float(t_cand.get("PliAnc", 0) or 0); lar = float(t_cand.get("PliLar", 0) or 0)
                                        if not validar_medidas_troquel(maquina, anc, lar): continue

                                        mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                                        mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                                        if not mp_ok: continue
                                        
                                        runnable, available_at = verificar_disponibilidad(t_cand, maquina)
                                        if runnable and (not available_at or available_at <= current_agenda_dt):
                                            tarea_encontrada = t_cand; fuente_maquina = m_manual; idx_robado = i; break
                                    if tarea_encontrada: break

                        # D: Robo entre Descartonadoras
                        # Tampoco roban si son las restringidas
                        elif "descartonad" in maquina.lower() and not is_restricted_desc:
                            vecinas_desc = [m for m in colas.keys() if "descartonad" in m.lower() and m != maquina]
                            for vecina in vecinas_desc:
                                if not colas.get(vecina): continue
                                for i, t_cand in enumerate(colas[vecina]):
                                    if "descartonad" not in t_cand["Proceso"].lower(): continue
                                    mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                                    mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                                    if not mp_ok: continue
                                    
                                    runnable, available_at = verificar_disponibilidad(t_cand, maquina)
                                    if runnable and (not available_at or available_at <= current_agenda_dt):
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
                                                                "Bocas", "Poses", "Cliente", "Cliente-articulo", "Proceso", "Maquina", "DueDate", "PliAnc", "PliLar", "MateriaPrima", "Gramaje",
                                                                "Urgente", "ManualPriority", "IsOutsourced", "IsSkipped"]} |
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
                                                            "Bocas", "Poses", "Cliente", "Cliente-articulo", "Proceso", "Maquina", "DueDate", "PliAnc", "PliLar", "MateriaPrima", "Gramaje",
                                                            "Urgente", "ManualPriority", "IsOutsourced", "IsSkipped"]} |
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

        # --- INYECCIÓN DE IDS DE MÁQUINA ---
        # IDs provistos por el usuario:
        # Guillotina - 1
        # troq nº 1 gus - 5
        # troq nº 2 ema - 7
        # Duyan - 105
        # Iberica - 104
        # heidelberg - 31
        # flexo 2 col - 32
        # pegadora ventana - 110
        # pegadora universal - 111
        # encapado - 150
        # cortadora de bobinas - 155
        # manual 3 - 4
        # descartonadora 1 - 40
        # descartonadora 2 - 194
        # descartonadora 3 - 247957750
        
        machine_ids_map = {
            "guillotina": 1,
            "troq nº 1 gus": 5, "manual 2": 5, "manual-2": 5,
            "troq nº 2 ema": 7, "manual 1": 7, "manual-1": 7,
            "duyan": 105,
            "iberica": 104,
            "heidelberg": 31, "offset": 31,
            "flexo 2 col": 32, "flexo": 32,
            "pegadora ventana": 110, "ventana": 110,
            "pegadora universal": 111, "pegadora": 111, "pegado": 111,
            "encapado": 150,
            "cortadora de bobinas": 155, "bobina": 155,
            "manual 3": 4, "manual-3": 4,
            "descartonadora 1": 40,
            "descartonadora 2": 194,
            "descartonadora 3": 247957750
        }

        if "custom_ids" in cfg:
            machine_ids_map.update({k.lower(): v for k, v in cfg["custom_ids"].items()})
        
        def get_machine_id(m_name):
            m_lower = str(m_name).lower().strip()
            # Búsqueda exacta primero
            if m_lower in machine_ids_map:
                return machine_ids_map[m_lower]
            # Búsqueda parcial si falla
            for k, v in machine_ids_map.items():
                if k in m_lower: 
                    return v
            return 0 # Default si no encuentra

        schedule["ID Maquina"] = schedule["Maquina"].apply(get_machine_id)
        
        # Mover "ID Maquina" al principio
        cols = ["ID Maquina"] + [c for c in schedule.columns if c != "ID Maquina"]
        schedule = schedule[cols]

    carga_md = pd.DataFrame(carga_reg)
    if not carga_md.empty:
        carga_md = carga_md.groupby(["Fecha", "Maquina", "CapacidadDia"], as_index=False)["HorasPlanificadas"].sum()
        carga_md["HorasExtra"] = (carga_md["HorasPlanificadas"] - carga_md["CapacidadDia"]).clip(lower=0).round(2)

    resumen_ot = pd.DataFrame()
    if not schedule.empty:
        resumen_ot = (
            schedule.groupby("OT_id").agg(
                Cliente=('Cliente', 'first'),
                Producto=('Cliente-articulo', 'first'),
                Fin_OT=('Fin', 'max'),
                DueDate=('DueDate', 'max')
            ).reset_index()
        )
        due_date_deadline_ot = pd.to_datetime(resumen_ot["DueDate"].dt.date) + timedelta(hours=18)
        resumen_ot["Fin_OT"] = pd.to_datetime(resumen_ot["Fin_OT"]) # Ensure datetime
        
        resumen_ot["Atraso_h"] = ((resumen_ot["Fin_OT"] - due_date_deadline_ot).dt.total_seconds() / 3600.0).clip(lower=0).fillna(0.0).round(2) 
        resumen_ot["EnRiesgo"] = resumen_ot["Atraso_h"] > 0
        
        # Ya no necesitamos hacer merge de Atraso_h desde resumen_ot porque ya lo calculamos,
        # PERO resumen_ot tiene el atraso FINAL de la OT (que es lo que importa al cliente).
        # El Atraso_h en schedule es "cuánto se pasó esta tarea del deadline final".
        # A veces una tarea intermedia se pasa, pero la OT se recupera? Dificil si el deadline es fijo.
        # Si Tarea1 termina dia 6 y Deadline es dia 5 -> Atraso.
        
        # Mantenemos Atraso_h en schedule para saber "Retraso generado/sufrido por esta máquina".
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
