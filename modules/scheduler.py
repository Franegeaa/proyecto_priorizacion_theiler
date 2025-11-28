import pandas as pd
from datetime import datetime, timedelta, time
from collections import defaultdict, deque
import random

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
    if es_si(orden.get("_PEN_ImpresionFlexo")) and not es_si(orden.get("PeliculaArt")): pendientes.append("Impresión Flexo")
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
                "Urgente": es_si(row.get("Urgente", False)) # Nueva bandera de urgencia
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
            return w >= 38 and l >= 38
        
        # Manuales: Maximos definidos (Ancho x Largo)
        # Manual 1: Max 80 x 105
        if "manual 1" in m or "manual1" in m:
            return w <= 80 and l <= 105
        
        # Manual 2: Max 66 x 90
        if "manual 2" in m or "manual2" in m:
            return w <= 66 and l <= 90
            
        # Manual 3: Max 70 x 100
        if "manual 3" in m or "manual3" in m:
            return w <= 70 and l <= 100
            
        return True # Por defecto si no matchea nombre

    if not tasks.empty and manuales: 
        if "CodigoTroquel" not in tasks.columns: tasks["CodigoTroquel"] = ""
        tasks["CodigoTroquel"] = tasks["CodigoTroquel"].fillna("").astype(str).str.strip().str.lower()
        
        cap = {} 
        for m in manuales + ([auto_name] if auto_name else []):
            if m: cap[m] = float(capacidad_pliegos_h("Troquelado", m, cfg) or 3000.0)
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
                
                # Datos para validación de medidas (usamos el maximo del grupo para asegurar)
                anc = g["PliAnc"].max()
                lar = g["PliLar"].max()
                bocas = float(g["Bocas"].max()) # Tomamos el maximo de bocas del grupo

                grupos.append((due_min, troq_key, g.index.tolist(), total_pliegos, anc, lar, bocas))
            grupos.sort() 

            for _, troq_key, idxs, total_pliegos, anc, lar, bocas in grupos:
                candidatas = []
                
                # 1. Validar candidatos por TAMAÑO primero
                posibles = manuales + ([auto_name] if auto_name else [])
                candidatos_tamano = [m for m in posibles if _validar_medidas_troquel(m, anc, lar)]
                
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
                
                # 4. DEFAULT (<= 3000 y <= 6 Bocas) -> Cualquiera compatible
                else:
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

    def _cola_impresora_flexo(q): 
        # Lógica Clustering (Agrupa Color -> Urgencia del Grupo)
        if q.empty: return deque()
        q = q.copy()
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
            grupos.append((not es_urgente, due_min, troq, g_sorted.to_dict("records")))
        grupos.sort()
        return deque([item for _, _, _, recs in grupos for item in recs])

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

    def lista_para_ejecutar(t, maquina_contexto=None): 
        def clean(s):
            if not s: return ""
            s = str(s).lower().strip()
            trans = str.maketrans("áéíóúüñ", "aeiouun")
            s = s.translate(trans)
            # Alias Agresivos
            if "flexo" in s: return "impresion flexo"
            if "offset" in s: return "impresion offset"
            # if "troquel" in s: return "troquelado"
            return s

        proc_actual_clean = clean(t["Proceso"])
        ot = t["OT_id"]
        flujo_clean = [clean(p) for p in flujo_estandar]
        
        if proc_actual_clean not in flujo_clean: return True
            
        idx = flujo_clean.index(proc_actual_clean)
        pendientes_clean = {clean(p) for p in pendientes_por_ot[ot]}
        prev_procs_names = []
        for p_raw in flujo_estandar[:idx]:
            if clean(p_raw) in pendientes_clean:
                prev_procs_names.append(p_raw)

        if not prev_procs_names: return True

        completados_clean = {clean(c) for c in completado[ot]}

        for p in prev_procs_names:
            if clean(p) not in completados_clean:
                return False 
        
        last_end = max((fin_proceso[ot].get(p) for p in prev_procs_names if fin_proceso[ot].get(p)), default=None)
        
        if last_end:
            # Si nos pasan contexto (ej. quien roba), usamos ese. Si no, el de la tarea.
            maq = maquina_contexto if maquina_contexto else t["Maquina"]
            
            # Protección extra: Si maq es POOL, no podemos chequear agenda.
            if "POOL" in str(maq): return True 

            current_agenda = datetime.combine(agenda[maq]["fecha"], agenda[maq]["hora"])
            
            if current_agenda < last_end:
                fecha_destino = last_end.date()
                hora_destino = last_end.time()

                if not es_dia_habil(fecha_destino, cfg):
                    fecha_destino = proximo_dia_habil(fecha_destino - timedelta(days=1), cfg)
                    hora_destino = time(7, 0) # Turno inicia a las 7
                
                agenda[maq]["fecha"] = fecha_destino
                agenda[maq]["hora"] = hora_destino
                h_usadas = (hora_destino.hour - 7) + (hora_destino.minute / 60.0)
                agenda[maq]["resto_horas"] = max(0, h_dia - h_usadas)

        return True 

    def _prioridad_dinamica(m):
        if "autom" in m.lower():
            return (0, agenda[m]["fecha"], agenda[m]["hora"])
        return (1, agenda[m]["fecha"], agenda[m]["hora"])

    progreso = True
    while quedan_tareas() and progreso:
        progreso = False
        
        # Mezclar máquinas para evitar sesgo hacia la primera (Descartonadora 1)
        maquinas_shuffled = list(maquinas)
        random.shuffle(maquinas_shuffled)
        
        for maquina in maquinas_shuffled:
        # for maquina in maquinas:
            if not colas.get(maquina): 
                
                # --- SISTEMA DE RESCATE (CRÍTICO) ---
                # Si la cola se vació pero quedó alguien encerrado en el buffer, ¡LIBÉRALO!
                if buffer_espera.get(maquina):
                    print(f"🚨 RESCATE FINAL: Liberando {len(buffer_espera[maquina])} tareas del buffer.")
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
            while tareas_agendadas: 
                tareas_agendadas = False
                
                # --- CHEQUEO DE SEGURIDAD PREVIO ---
                if not colas.get(maquina):
                    if buffer_espera.get(maquina):
                         print(f"🚨 RESCATE INTERMEDIO: Liberando {len(buffer_espera[maquina])} tareas.")
                         colas[maquina].extendleft(reversed(buffer_espera[maquina]))
                         buffer_espera[maquina] = []
                    else:
                        # EXCEPCIÓN: Si es Descartonadora y hay tareas en el POOL, ¡NO ROMPER!
                        if "descartonad" in maquina.lower() and colas.get("POOL_DESCARTONADO"):
                            pass # Dejar pasar
                        else:
                            break
                
                # ==========================================================
                # PASO 1: BÚSQUEDA DE CANDIDATA (Estricta)
                # ==========================================================
                idx_cand = -1 
                for i, t_cand in enumerate(colas[maquina]):
                    mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                    mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                    if not mp_ok: continue

                    if lista_para_ejecutar(t_cand, maquina):
                        idx_cand = i
                        break
                
                # ==========================================================
                # PASO 2: INTENTO DE ROBO (Casos A, B, C, D)
                # ==========================================================
                tarea_robada = False
                if idx_cand == -1:
                    if buffer_espera.get(maquina):
                         print(f"⚠️ PACIENCIA AGOTADA: No hay pareja. Libero {len(buffer_espera[maquina])} tareas.")
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
                            for i, t_cand in enumerate(colas["POOL_DESCARTONADO"]):
                                # Validar MP
                                mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                                mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                                if not mp_ok: continue
                                
                                if lista_para_ejecutar(t_cand, maquina):
                                    tarea_encontrada = t_cand
                                    fuente_maquina = "POOL_DESCARTONADO"
                                    idx_robado = i
                                    break
                        
                        if tarea_encontrada:
                            # Ejecutar robo del POOL inmediatamente
                            pass # Se procesa abajo en el bloque común de robo
                        
                        # A: Auto roba a Manual
                        elif maquina in auto_names:
                            for m_manual in manuales:
                                if not colas.get(m_manual): continue
                                for i, t_cand in enumerate(colas[m_manual]):
                                    if t_cand["Proceso"].strip() != "Troquelado": continue
                                    
                                    # Validar medidas para Auto (Min 38x38)
                                    anc = float(t_cand.get("PliAnc", 0) or 0); lar = float(t_cand.get("PliLar", 0) or 0)
                                    if not _validar_medidas_troquel(maquina, anc, lar): continue

                                    mp = str(t_cand.get("MateriaPrimaPlanta")).strip().lower()
                                    mp_ok = mp in ("false", "0", "no", "falso", "") or not t_cand.get("MateriaPrimaPlanta")
                                    if not mp_ok: continue
                                    if lista_para_ejecutar(t_cand, maquina):
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
                                    if lista_para_ejecutar(t_cand, maquina):
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
                                        if lista_para_ejecutar(t_cand, maquina):
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
                                    if lista_para_ejecutar(t_cand, maquina):
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
                    # Traemos la tarea al frente
                    if not tarea_robada and idx_cand > 0:
                        colas[maquina].rotate(-idx_cand)
                    
                    t_candidata = colas[maquina][0]
                    se_ejecuta_ya = True
                    es_barniz = "barniz" in t_candidata["Proceso"].lower()
                    
                    if es_barniz:
                        # 1. CONSOLIDACIÓN: Si hay gente en el buffer, ¡traerlos YA!
                        if buffer_espera[maquina]:
                            # Traemos todo lo del buffer al inicio de la cola
                            # Buffer: [B1, B2] -> Cola: [B1, B2, Actual...]
                            # Para mantener orden: extendleft con reversed
                            colas[maquina].extendleft(reversed(buffer_espera[maquina]))
                            buffer_espera[maquina] = [] # Limpiar buffer
                            
                            print(f"🎯 FRANCOTIRADOR: Reagrupando {len(colas[maquina])} barnices.")
                            # YA NO hacemos continue. Dejamos que fluya para EJECUTAR la primera tarea del grupo.
                            # Esto rompe el ciclo infinito de agrupar-desagrupar.
                            se_ejecuta_ya = True 


                        # 2. MIRAR AL FUTURO (Solo si el buffer estaba vacío, o sea, ya consolidamos)
                        # Identificar bloque contiguo de barnices en el tope
                        bloque_barniz = []
                        idx = 0
                        while idx < len(colas[maquina]):
                            t = colas[maquina][idx]
                            if "barniz" in t["Proceso"].lower():
                                bloque_barniz.append(t)
                                idx += 1
                            else:
                                break
                        
                        # Mirar 3 tareas MÁS ALLÁ del bloque
                        rango_vision = 3
                        encontre_pareja = False
                        limit = min(len(colas[maquina]), idx + rango_vision)
                        
                        for k in range(idx, limit):
                            futura = colas[maquina][k]
                            if "barniz" in futura["Proceso"].lower():
                                # Chequeo MP simple
                                mp = str(futura.get("MateriaPrimaPlanta")).strip().lower()
                                mp_ok = mp in ("false", "0", "no", "falso", "") or not futura.get("MateriaPrimaPlanta")
                                
                                if mp_ok:
                                    encontre_pareja = True
                                    print(f"👀 OJO: Veo barniz futuro {futura['OT_id']} en pos {k}. Reteniendo bloque de {len(bloque_barniz)} tareas.")
                                    break
                        
                        if encontre_pareja:
                            # Guardamos TODO el bloque en el buffer
                            # Ojo: hay que sacarlos de la cola
                            for _ in range(len(bloque_barniz)):
                                t_removed = colas[maquina].popleft()
                                buffer_espera[maquina].append(t_removed)
                            
                            se_ejecuta_ya = False
                            progreso = True # ¡IMPORTANTE! Hemos hecho algo (buffer), así que el sistema sigue vivo.
                            continue

                    #========================================
                    # PASO 4: EJECUCIÓN FINAL
                    #========================================

                    if se_ejecuta_ya:
                        t = colas[maquina].popleft()
                        orden = df_ordenes.loc[t["idx"]].copy()

                        # Inyección de datos calculados
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
                        segundos_netos = sum((b_fin - b_ini).total_seconds() for b_ini, b_fin in bloques)
                        duracion_h = round(segundos_netos / 3600.0, 3)

                        fin_proceso[t["OT_id"]][t["Proceso"]] = fin
                        for b_ini, b_fin in bloques:
                            carga_reg.append({"Fecha": b_ini.date(), "Maquina": maquina, 
                                                "HorasPlanificadas": (b_fin - b_ini).total_seconds() / 3600.0, 
                                                "CapacidadDia": h_dia})

                        filas.append({k: t.get(k) for k in ["OT_id", "CodigoProducto", "Subcodigo", "CantidadPliegos", "CantidadPliegosNetos",
                                                            "Bocas", "Poses", "Cliente", "Cliente-articulo", "Proceso", "Maquina", "DueDate", "PliAnc", "PliLar",
                                                            "CodigoTroquel", "Colores"]} |
                                     {"Setup_min": round(setup_min, 2), "Proceso_h": round(proc_h, 3), 
                                      "Inicio": inicio, "Fin": fin, "Duracion_h": duracion_h, "Motivo": motivo})

                        completado[t["OT_id"]].add(t["Proceso"])
                        ultimo_en_maquina[maquina] = t 
                        progreso = True; tareas_agendadas = True
                        
                        if tarea_robada: break 

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
    