import pandas as pd
from datetime import datetime, timedelta, time, date
from collections import defaultdict, deque
import random

from modules.schedulers.machines import elegir_maquina
from modules.schedulers.priorities import _clave_prioridad_maquina, _cola_impresora_flexo, _cola_impresora_offset, _cola_troquelada, _cola_cortadora_bobina
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
    # 1.1 PROCESAMIENTO IMAGEN DE PLANTA (PENDING PROCESSES)
    # =======================================================
    
    # Listas para guardar lo ya agendado por imagen de planta
    completado = defaultdict(set)
    fin_proceso = defaultdict(dict)
    ultimo_en_maquina = {m: None for m in cfg["maquinas"]["Maquina"].unique()} 
    filas = []
    
    pending_list = cfg.get("pending_processes", [])
    if pending_list:
        print(f"--- Procesando {len(pending_list)} procesos en curso ---")
        
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
                print(f"Skip Pending: No se encontró tarea para {pp_ot} en {pp_maquina} ({proc_target})")
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
                print(f"OK Pending: {pp_ot} en {pp_maquina} agendado y removido de cola.")
            else:
                 print(f"Error Pending: No se pudo reservar tiempo para {pp_ot} en {pp_maquina}")

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
            if "autom" in maquina.lower() or "duyan" in maquina.lower():
                return (base_order, 1)
            else:
                return (base_order, 0)
        
        return (base_order, 0)

    maquinas = sorted(cfg["maquinas"]["Maquina"].unique(), key=_orden_proceso)
    
    # =================================================================
    # 3. REASIGNACIÓN TROQUELADO (Solo asigna, NO reserva tiempo)
    # =================================================================
    
    troq_cfg = cfg["maquinas"][cfg["maquinas"]["Proceso"].str.lower().str.contains("troquel")]
    manuales = [m for m in troq_cfg["Maquina"].tolist() if "manual" in str(m).lower() or "troq n" in str(m).lower()]
    iberica = [m for m in troq_cfg["Maquina"].tolist() if "iberica" in str(m).lower()]
    auto_names = [m for m in troq_cfg["Maquina"].tolist() if "autom" in str(m).lower() or "duyan" in str(m).lower()]
    auto_name = auto_names[0] if auto_names else None


    def _validar_medidas_troquel(maquina, anc, lar):
        # Normalizar nombre
        m = str(maquina).lower().strip()
        # Dimensiones de la tarea (CON ROTACIÓN)
        # Se compara el lado mayor del pliego con el lado mayor de la máquina
        # y el lado menor del pliego con el lado menor de la máquina.
        w_orig = float(anc or 0)
        l_orig = float(lar or 0)
        
        pliego_min = min(w_orig, l_orig)
        pliego_max = max(w_orig, l_orig)

        if "autom" in m or "duyan" in m:
            # Min 38x38 (Ambos lados deben ser >= 38)
            # Como es minimo, ambos lados deben superar 38, asi que da igual la rotación si min(pliego) >= 38
            return pliego_min >= 38
        
        # Manuales: Maximos definidos (Ancho y Largo)
        
        # Manual 1 (Troq Nº 2 Ema): Max 80 x 105
        if "manual 1" in m or "manual1" in m or "ema" in m:
             # Maquina: 80x105 -> Min: 80, Max: 105
             mq_min, mq_max = 80, 105
             return pliego_min <= mq_min and pliego_max <= mq_max
        
        # Manual 2 (Troq Nº 1 Gus): Max 66 x 90
        # Maquina: 66x90 -> Min: 66, Max: 90
        if "manual 2" in m or "manual2" in m or "gus" in m:
             mq_min, mq_max = 66, 90
             return pliego_min <= mq_min and pliego_max <= mq_max
            
        # Manual 3: Max 70 x 100
        # Maquina: 70x100 -> Min: 70, Max: 100
        if "manual 3" in m or "manual3" in m:
             mq_min, mq_max = 70, 100
             return pliego_min <= mq_min and pliego_max <= mq_max
        
        # Iberica: Max 70 x 100
        #          Min 35 x 50
        # Maquina: 70x100 -> Min: 86, Max: 110
        if "iberica" in m:
            mq_min, mq_max, mq_min2, mq_max2 = 86, 110, 35, 50
            return (pliego_min <= mq_min and pliego_max <= mq_max) and (pliego_min >= mq_min2 and pliego_max >= mq_max2)
        
        return True # Por defecto si no matchea nombre

    if not tasks.empty and manuales: 
        if "CodigoTroquel" not in tasks.columns: tasks["CodigoTroquel"] = ""
        tasks["CodigoTroquel"] = tasks["CodigoTroquel"].fillna("").astype(str).str.strip().str.lower()
        
        cap = {} 
        for m in manuales + ([auto_name] if auto_name else []) + iberica:
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
                posibles = manuales + ([auto_name] if auto_name else []) + iberica
                candidatos_tamano = []
                for m in posibles:
                    if "autom" in str(m).lower():
                        # Para Automatica (Restricción de MINIMO), usamos las dimensiones MINIMAS del grupo
                        # Si la hoja más chica es < 38, NO entra en Auto.
                        if _validar_medidas_troquel(m, min_anc, min_lar):
                            candidatos_tamano.append(m)
                    elif "iberica" in str(m).lower():
                        # Para Iberica (Restricción de MINIMO), usamos las dimensiones MINIMAS del grupo
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
                
                # 3. REGLA DE CANTIDAD (> 2500) -> Automática Obligatoria (si entra)
                elif total_pliegos > 2500:
                    if auto_name and (auto_name in candidatos_tamano):
                        candidatas = [auto_name]
                        # Fix: Iterar sobre la lista iberica para ver si alguna es candidata
                        for ib in iberica:
                            if ib in candidatos_tamano:
                                candidatas.append(ib)
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
        elif ("manual" in m_lower) or ("autom" in m_lower) or ("troquel" in m_lower) or ("duyan" in m_lower) or ("iberica" in m_lower): colas[m] = _cola_troquelada(q)
        elif ("offset" in m_lower) or ("heidelberg" in m_lower): colas[m] = _cola_impresora_offset(q)
        elif ("flexo" in m_lower) or ("impres" in m_lower): colas[m] = _cola_impresora_flexo(q)
        elif "bobina" in m_lower: colas[m] = _cola_cortadora_bobina(q)
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
        
        # --- NUEVO: RESTRICCION POR LLEGADA DE INSUMOS (CHAPAS / TROQUEL) ---
        arrival_date = None
        
        # 1. Impresión (Offset/Flexo) depende de fecha llegada chapas (PeliculaArt)
        if "impres" in proc_actual_clean:
            if es_si(t.get("PeliculaArt")):
                fecha_chapas = t.get("FechaLlegadaChapas")
                if pd.notna(fecha_chapas):
                    # Asumimos disponibilidad al inicio de ese día (00:00) o a las 7:00?
                    # Mejor las 07:00 para alinear con jornada
                    arrival_date = datetime.combine(fecha_chapas.date(), time(7,0))

        # 2. Troquelado depende de fecha llegada troquel (TroquelArt)
        elif "troquel" in proc_actual_clean:
             if es_si(t.get("TroquelArt")):
                fecha_troquel = t.get("FechaLlegadaTroquel")
                with open("debug_scheduler.log", "a") as f:
                    f.write(f"DEBUG: Checking TroquelArt for {ot}. Val: {t.get('TroquelArt')}. Date: {fecha_troquel}. NotNa: {pd.notna(fecha_troquel)}\n")
                if pd.notna(fecha_troquel):
                    arrival_date = datetime.combine(fecha_troquel.date(), time(7,0))
                    with open("debug_scheduler.log", "a") as f:
                        f.write(f"DEBUG: Set arrival_date to {arrival_date}\n")
        
        # Fusionar restricciones: la fecha efectiva es el MAX(dependencia, llegada_insumo)
        if last_end and arrival_date:
            return (True, max(last_end, arrival_date))
        elif arrival_date:
            return (True, arrival_date)
        
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
                def log_debug(msg):
                    with open("tests/debug_francotirador.txt", "a", encoding="utf-8") as f:
                        f.write(f"[{maquina}] {msg}\n")

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

                for i, t_cand in enumerate(colas[maquina]):
                    mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                    mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                    if not mp_ok: continue

                    runnable, available_at = verificar_disponibilidad(t_cand, maquina)
                    
                    if not runnable: continue
                    
                    es_setup = False
                    if ultima_tarea:
                         es_setup = usa_setup_menor(ultima_tarea, t_cand, t_cand.get("Proceso", ""))

                    if "barniz" in maquina.lower() and i < 5:
                         log_debug(f"Cand[{i}]: {t_cand.get('Cliente')} (Due: {t_cand.get('DueDate')}) - Avail: {available_at} - SetupMenor: {es_setup}")

                    # Si está lista YA (o antes), la tomamos inmediatamente (Gap Filling)

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
                            
                    # -- LÓGICA FRANCOTIRADOR (SMART WAIT) --
                    # Guardamos el mejor candidato de setup para compararlo luego
                    if es_setup:
                         if mejor_candidato_setup is None:
                             mejor_candidato_setup = (i, available_at)
                             if "barniz" in maquina.lower(): log_debug(f"MARKING SETUP CANDIDATE: IDX {i}")
                         else:
                             if available_at < mejor_candidato_setup[1]:
                                 mejor_candidato_setup = (i, available_at)
                                 if "barniz" in maquina.lower(): log_debug(f"UPDATING SETUP CANDIDATE: IDX {i}")

                
                
                # --- APPLY SMART WAIT / FRANCOTIRADOR LOGIC ---
                TOLERANCIA = timedelta(minutes=90)
                final_decision = None # (idx, dt)

                if "barniz" in maquina.lower(): 
                    log_debug(f"End Loop. IdxCand: {idx_cand}. BestFut: {mejor_candidato_futuro}. BestSetup: {mejor_candidato_setup}")

                # 1. Si ya tenemos uno listo (idx_cand != -1), checkeamos si vale la pena ESPERAR por setup
                if idx_cand != -1 and mejor_candidato_setup:
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
                        
                        # A: Auto roba a Manual o Iberica
                        elif maquina in auto_names:
                            # Targets: Manuales + Iberica
                            targets_robo = manuales + iberica
                            for m_target in targets_robo:
                                if not colas.get(m_target): continue
                                for i, t_cand in enumerate(colas[m_target]):
                                    if t_cand["Proceso"].strip() != "Troquelado": continue

                                    cant = float(t_cand.get("CantidadPliegos", 0) or 0)
                                    if cant < 3000: continue
                                    
                                    # Validar medidas para Auto (Min 38x38)
                                    anc = float(t_cand.get("PliAnc", 0) or 0); lar = float(t_cand.get("PliLar", 0) or 0)
                                    if not _validar_medidas_troquel(maquina, anc, lar): continue

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
                                    if not _validar_medidas_troquel(maquina, anc, lar): continue
                                    
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
                                        if not _validar_medidas_troquel(maquina, anc, lar): continue

                                        mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                                        mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                                        if not mp_ok: continue
                                        
                                        runnable, available_at = verificar_disponibilidad(t_cand, maquina)
                                        if runnable and (not available_at or available_at <= current_agenda_dt):
                                            tarea_encontrada = t_cand; fuente_maquina = vecina; idx_robado = i; break
                                    if tarea_encontrada: break

                        # Z: Iberica roba a Auto o Manual
                        elif any(m in maquina for m in iberica):
                            # Z.1: Robar a Auto
                            if auto_name and colas.get(auto_name):
                                for i, t_cand in enumerate(colas[auto_name]):
                                    if t_cand["Proceso"].strip() != "Troquelado": continue
                                    
                                    # REGLA: Iberica roba lo que le sirva (asumimos lógica similar a Manual/Auto)
                                    # Preferencia: Si hay algo en auto, intentar robarlo?
                                    # User dijo: "para el robo de la automatica hay que poner que la iberica este como opcion para robar"
                                    # AND "Iberica puede robar a las manuales y a la automatica".
                                    
                                    anc = float(t_cand.get("PliAnc", 0) or 0); lar = float(t_cand.get("PliLar", 0) or 0)
                                    if not _validar_medidas_troquel(maquina, anc, lar): continue
                                    
                                    mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                                    mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                                    if not mp_ok: continue
                                    
                                    runnable, available_at = verificar_disponibilidad(t_cand, maquina)
                                    if runnable and (not available_at or available_at <= current_agenda_dt):
                                        tarea_encontrada = t_cand; fuente_maquina = auto_name; idx_robado = i; break
                            
                            # Z.2: Robar a Manuales
                            if not tarea_encontrada:
                                for m_manual in manuales:
                                    if not colas.get(m_manual): continue
                                    for i, t_cand in enumerate(colas[m_manual]):
                                        if t_cand["Proceso"].strip() != "Troquelado": continue
                                    
                                        anc = float(t_cand.get("PliAnc", 0) or 0); lar = float(t_cand.get("PliLar", 0) or 0)
                                        if not _validar_medidas_troquel(maquina, anc, lar): continue

                                        mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                                        mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                                        if not mp_ok: continue
                                        
                                        runnable, available_at = verificar_disponibilidad(t_cand, maquina)
                                        if runnable and (not available_at or available_at <= current_agenda_dt):
                                            tarea_encontrada = t_cand; fuente_maquina = m_manual; idx_robado = i; break
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
                                                                "Bocas", "Poses", "Cliente", "Cliente-articulo", "Proceso", "Maquina", "DueDate", "PliAnc", "PliLar", "MateriaPrima", "Gramaje"]} |
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
                                                            "Bocas", "Poses", "Cliente", "Cliente-articulo", "Proceso", "Maquina", "DueDate", "PliAnc", "PliLar", "MateriaPrima", "Gramaje"]} |
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
                Fin_OT=('Fin', 'max'),
                DueDate=('DueDate', 'max')
            ).reset_index()
        )
        due_date_deadline_ot = pd.to_datetime(resumen_ot["DueDate"].dt.date) + timedelta(hours=18)
        resumen_ot["Fin_OT"] = pd.to_datetime(resumen_ot["Fin_OT"]) # Ensure datetime
        
        resumen_ot["Atraso_h"] = ((resumen_ot["Fin_OT"] - due_date_deadline_ot).dt.total_seconds() / 3600.0).clip(lower=0).fillna(0.0).round(2) 
        resumen_ot["EnRiesgo"] = resumen_ot["Atraso_h"] > 0
        
        # --- NUEVO: CÁLCULO DE RETRASO POR TAREA (POR MÁQUINA) ---
        # Calculamos el retraso individual de cada tarea respecto a la fecha final de la OT.
        # Esto permite identificar qué máquinas están entregando fuera de término.
        
        # Fecha límite de la OT (mismo deadline para todas las tareas de la OT)
        # Ojo: schedule["DueDate"] ya viene del merge/append y tiene hora 00:00 (timestamp)
        # Queremos Deadline = DueDate (date) + 18:00
        
        if not schedule.empty:
            schedule_deadline = pd.to_datetime(schedule["DueDate"].dt.date) + timedelta(hours=18)
            
            schedule["Atraso_h"] = ((schedule["Fin"] - schedule_deadline).dt.total_seconds() / 3600.0).clip(lower=0).fillna(0.0).round(2)
            schedule["EnRiesgo"] = schedule["Atraso_h"] > 0
        
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
