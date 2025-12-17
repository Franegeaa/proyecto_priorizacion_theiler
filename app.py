import streamlit as st
import pandas as pd
from datetime import datetime, date, time, timedelta
from io import BytesIO
from collections import Counter
import plotly.graph_objects as go
from modules.config_loader import cargar_config, es_dia_habil, horas_por_dia
from modules.scheduler import programar
import streamlit.components.v1 as components

# Opcional: Plotly para Gantt
try:
    import plotly.express as px
    _HAS_PLOTLY = True
except Exception:
    _HAS_PLOTLY = False

st.set_page_config(page_title="Priorización de Órdenes", layout="wide")
st.title("📦 Planificador de Producción – Theiler Packaging")

archivo = st.file_uploader("📁 Subí el Excel de órdenes desde Access (.xlsx)", type=["xlsx"])

color_map_procesos = {
    "Cortadora Bobina": "lightgray", #Gris claro
    "Guillotina": "dimgray",        # Gris oscuro
    "Impresión Offset": "mediumseagreen", # Verde mar
    "Impresión Flexo": "darkorange",
    "Plastificado": "violet",      
    "Barnizado": "gold",            # Dorado (o "Barniz" si se llama así)
    "Barniz": "gold",               # Añade variantes si es necesario
    "OPP": "slateblue",             # Azul pizarra
    "Stamping": "firebrick",        # Rojo ladrillo
    "Cuño": "darkcyan",             # Cian oscuro (Añade si es un proceso)
    "Encapado": "sandybrown",       # Marrón arena (Añade si es un proceso)
    "Troquelado": "lightcoral",     # Coral claro
    "Descartonado": "dodgerblue",   # Azul brillante
    "Ventana": "skyblue",           # Azul cielo
    "Pegado": "mediumpurple",         # Púrpura medio
}

def ordenar_maquinas_personalizado(lista_maquinas):
    """Ordena máquinas según prioridad operativa definida por el usuario."""
    prioridades = [
        (1, ["bobina", "cortadora de bobinas"]),
        (2, ["guillotina"]),
        (3, ["offset", "heidelberg"]),
        (4, ["flexo", "flexo 2 col"]),
        (5, ["stamping"]),
        (6, ["plastificadora"]),
        (7, ["encapado"]),
        (8, ["cuño"]),
        (9, ["automat", "automát", "duyan"]),
        (10, ["manual 1", "manual-1", "manual1", "troq nº 2 ema"]),
        (11, ["manual 2", "manual-2", "manual2", "troq nº 1 gus"]),
        (12, ["manual 3", "manual-3", "manual3"]),
        (13, ["iberica"]),
        (14, ["descartonadora 1"]),
        (15, ["descartonadora 2"]),
        (16, ["descartonadora 3"]),
        (17, ["ventana", "pegadora ventana"]),
        (18, ["pegadora", "pegado", "pegadora universal"]),
    ]

    def clave(nombre):
        nombre_str = str(nombre).lower()
        for prioridad, patrones in prioridades:
            if any(pat in nombre_str for pat in patrones):
                return (prioridad, nombre_str)
        return (len(prioridades) + 1, nombre_str)

    return sorted(lista_maquinas, key=clave, reverse=True)

if archivo is not None:
    df = pd.read_excel(archivo)

    if "cfg" not in st.session_state:
        st.session_state.cfg = cargar_config("config/Config_Priorizacion_Theiler.xlsx")

    cfg = st.session_state.cfg   # <- SIEMPRE usar el mismo cfg    

    maquinas_todas = sorted(cfg["maquinas"]["Maquina"].unique().tolist())
    
    with st.expander("Añadir un velocidades de máquina (opcional)"):
        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
        with col1:
            d_maquina_s = st.selectbox(
                "Máquina", 
                options=maquinas_todas, # Solo máquinas activas
                key="d_maquina_s"
            )

        maquina = d_maquina_s

        vel_valor = cfg["maquinas"].loc[cfg["maquinas"]["Maquina"] == maquina, "Capacidad_pliegos_hora"].values[0]
        setup_valor = cfg["maquinas"].loc[cfg["maquinas"]["Maquina"] == maquina, "Setup_base_min"].values[0]
        setup_min_valor = cfg["maquinas"].loc[cfg["maquinas"]["Maquina"] == maquina, "Setup_menor_min"].values[0]

        with col2:
            vel_valor = st.number_input("Velocidad de máquina (pliegos/hora)", value=int(vel_valor), key=f"vel_{maquina}")
            if vel_valor > 0:
                cfg["maquinas"].loc[cfg["maquinas"]["Maquina"] == maquina, "Capacidad_pliegos_hora"] = int(vel_valor)
            else:
                st.warning("La velocidad debe ser mayor que 0.")
        with col3:
            setup_valor = st.number_input("Setup base (min)", value=int(setup_valor), key=f"setup_{maquina}")
            if setup_valor > 0:
                cfg["maquinas"].loc[cfg["maquinas"]["Maquina"] == maquina, "Setup_base_min"] = int(setup_valor)
            else:
                st.warning("El setup base debe ser mayor que 0.")
        with col4:
            setup_min_valor = st.number_input("Setup menor (min)", value=int(setup_min_valor), key=f"setup_menor_{maquina}")
            if setup_min_valor > 0:
                cfg["maquinas"].loc[cfg["maquinas"]["Maquina"] == maquina, "Setup_menor_min"] = int(setup_min_valor)
            else:
                st.warning("El setup menor debe ser mayor que 0.")
            
    st.subheader("⚙️ Parámetros de jornada")

    hoy = date.today()
    fecha_inicio_plan = st.date_input(
        "📅 Fecha de inicio de la planificación:",
        value=hoy,
        min_value=hoy,
    )

    hora_inicio_plan = st.time_input(
        "⏰ Hora de inicio de la planificación:",
        value=pd.to_datetime("07:00").time()
    )

    # --- NUEVO: Input de Feriados ---
    placeholder_feriados = "Pega una lista de fechas (ej. 21/11/2025), una por línea o separadas por coma."
    feriados_texto = st.text_area(
        "Días feriados (opcional):",
        placeholder_feriados,
        height=100
    )
    
    feriados_lista = []
    # Revisa que el texto no esté vacío y no sea el placeholder
    if feriados_texto and feriados_texto.strip() != placeholder_feriados:
        # Limpia el texto, reemplaza comas por saltos de línea
        texto_limpio = feriados_texto.replace(",", "\n")
        fechas_str = [f.strip() for f in texto_limpio.split("\n") if f.strip()]
        
        for f_str in fechas_str:
            try:
                # Intenta parsear la fecha (acepta varios formatos como AAAA-MM-DD o DD/MM/AAAA)
                feriados_lista.append(pd.to_datetime(f_str, dayfirst=True, errors='raise').date())
            except Exception as e:
                st.warning(f"No se pudo entender la fecha feriado: '{f_str}'. Ignorando.")
    
    # Inyectamos los feriados en la configuración
    cfg["feriados"] = feriados_lista
    if feriados_lista:
        st.info(f"Se registrarán {len(feriados_lista)} días feriados que no se planificarán.")
    # --- FIN NUEVO ---

    # --- NUEVO: SELECCIÓN DE MÁQUINAS ACTIVAS ---
    st.subheader("🏭 Máquinas Disponibles")
    maquinas_activas = st.multiselect(
        "Seleccioná las máquinas que se usarán en esta planificación:",
        options=maquinas_todas,
        default=[m for m in maquinas_todas if "Manual 3" not in m and "Descartonadora 3" not in m and "Iberica" not in m]
    )
    
    # Filtramos la configuración ANTES de pasarla al scheduler
    cfg_plan = cfg.copy()
    cfg_plan["maquinas"] = cfg["maquinas"][cfg["maquinas"]["Maquina"].isin(maquinas_activas)].copy()
    
    if len(maquinas_activas) < len(maquinas_todas):
        st.warning(f"Planificando solo con {len(maquinas_activas)} de {len(maquinas_todas)} máquinas.")
    # --- FIN NUEVO ---

    # --- NUEVO: TIEMPO FUERA DE SERVICIO (DOWNTIME) ---
    st.subheader("🔧 Tiempo Fuera de Servicio (Paros Programados)")

    # Usamos st.session_state para guardar la lista de paros
    if "downtimes" not in st.session_state:
        st.session_state.downtimes = []

    # UI para agregar un paro
    with st.expander("Añadir un paro de máquina (opcional)"):
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            d_maquina = st.selectbox(
                "Máquina", 
                options=maquinas_activas, # Solo máquinas activas
                key="d_maquina"
            )
        with col2:
            d_fecha_inicio = st.date_input("Fecha Inicio", value=fecha_inicio_plan, key="d_fecha_inicio")
        with col3:
            d_hora_inicio = st.time_input("Hora Inicio", value=time(8, 0), key="d_hora_inicio")
        
        col4, col5, col6 = st.columns([2, 1, 1])
        with col4:
            st.write("") # Espaciador
        with col5:
            d_fecha_fin = st.date_input("Fecha Fin", value=d_fecha_inicio, key="d_fecha_fin")
        with col6:
            d_hora_fin = st.time_input("Hora Fin", value=time(12, 0), key="d_hora_fin")

        if st.button("Añadir Paro"):
            dt_inicio = datetime.combine(d_fecha_inicio, d_hora_inicio)
            dt_fin = datetime.combine(d_fecha_fin, d_hora_fin)
            
            if dt_fin <= dt_inicio:
                st.error("Error: La fecha/hora de fin debe ser posterior a la de inicio.")
            else:
                st.session_state.downtimes.append({
                    "maquina": d_maquina,
                    "start": dt_inicio,
                    "end": dt_fin
                })
                st.success(f"Paro añadido para {d_maquina} de {dt_inicio} a {dt_fin}")

        st.session_state.downtimes = pd.DataFrame(st.session_state.downtimes).drop_duplicates().to_dict(orient="records")
    # Mostrar paros añadidos
    if st.session_state.downtimes:
        st.write("Paros programados:")
        for i, dt in enumerate(st.session_state.downtimes):
            st.info(f"{i+1}: **{dt['maquina']}** fuera de servicio desde {dt['start']} hasta {dt['end']}")
    
    # Inyectamos la lista de paros en la configuración
    cfg["downtimes"] = st.session_state.downtimes
    
    # --- NUEVO: HORAS EXTRAS ---
    st.subheader("⏳ Horas Extras")
    
    # 1. Calcular los días de la semana de la planificación
    start_of_week_plan = fecha_inicio_plan 
    dias_semana = []
    lista_dias_str = []
    map_str_date = {}
    
    for i in range(7):
        dia_actual = start_of_week_plan + timedelta(days=i)
        nombre = dia_actual.strftime('%A')
        label = f"{nombre} {dia_actual.strftime('%d/%m')}"
        dias_semana.append(dia_actual)
        lista_dias_str.append(label)
        map_str_date[label] = dia_actual

    # 2. Selección de máquinas para horas extras
    # Usamos un expander para no ensuciar tanto la UI principal si no se usa
    with st.expander("Planificar Horas Extras (por máquina)"):
        
        # 2.1 Seleccionar QUE máquinas harán horas extras
        maquinas_con_extras = st.multiselect(
            "Seleccioná las máquinas que harán horas extras:",
            options=maquinas_activas, # Solo las que se van a usar
            default=[]
        )
        
        horas_extras_general = {} # Diccionario Maquina -> {Fecha -> Horas}
        
        if maquinas_con_extras:
            st.markdown("---")
            for maq in maquinas_con_extras:
                st.markdown(f"#### 🏭 {maq}")
                
                # Para cada máquina, un multiselect de días
                dias_sel_maq = st.multiselect(
                    f"Días de horas extras para {maq}:",
                    options=lista_dias_str,
                    default=[],
                    key=f"dias_he_{maq}"
                )
                
                horas_extras_maq = {}
                if dias_sel_maq:
                    # Layout de inputs
                    cols_he = st.columns(len(dias_sel_maq)) if len(dias_sel_maq) <= 4 else st.columns(4)
                    
                    for idx, dia_label in enumerate(dias_sel_maq):
                        col_obj = cols_he[idx % 4]
                        fecha_obj = map_str_date[dia_label]
                        
                        with col_obj:
                            horas = st.number_input(
                                f"{dia_label} ({maq})",
                                min_value=0.0, 
                                max_value=24.0, 
                                value=2.0, 
                                step=0.5,
                                label_visibility="collapsed", # Ahorrar espacio visual
                                key=f"he_{maq}_{fecha_obj}"
                            )
                            # Etiqueta manual pequeña
                            st.caption(f"{dia_label}")
                            
                            if horas > 0:
                                horas_extras_maq[fecha_obj] = horas
                
                if horas_extras_maq:
                    horas_extras_general[maq] = horas_extras_maq
                st.markdown("---")

        if horas_extras_general:
             total_dias = sum(len(v) for v in horas_extras_general.values())
             st.info(f"Se han configurado horas extras para {len(horas_extras_general)} máquinas.")

    # Inyectamos las horas extras en la configuración (Estructura: {Maquina: {Fecha: Horas}})
    cfg["horas_extras"] = horas_extras_general
    # --- FIN NUEVO ---

    # --- NUEVO: TIEMPO FUERA DE SERVICIO (DOWNTIME) ---
    start_datetime = datetime.combine(fecha_inicio_plan, hora_inicio_plan)
    
    # --- RENOMBRADO ---
    df.rename(columns={
        "ORDEN": "CodigoProducto",
        "Ped.": "Subcodigo",
        "CLIENTE": "Cliente",
        "ART/DDP": "Cliente-articulo",
        "Razon Social": "RazonSocial",
        "CANT/DDP": "CantidadPliegos",
        "FECH/ENT.": "FechaEntrega",
        "Mat/Prim1": "MateriaPrima",
        "MPPlanta": "MateriaPrimaPlanta",
        "CodTroTapa": "CodigoTroquelTapa",
        "CodTroCuerpo": "CodigoTroquelCuerpo",
        "FechaChaDpv": "FechaLlegadaChapas",
        "FechaTroDpv": "FechaLlegadaTroquel",
        "Pli Anc": "PliAnc",
        "Pli Lar": "PliLar",
    }, inplace=True)

    # --- COLORES COMBINADOS ---
    color_cols = [c for c in df.columns if str(c).startswith("Color")]
    df["Colores"] = df[color_cols].fillna("").astype(str).agg("-".join, axis=1) if color_cols else ""

    # --- PARSEO DE FECHAS (CUSTOM ESPAÑOL) ---
    def parse_spanish_date(date_str):
        if pd.isna(date_str) or str(date_str).strip() == "":
            return pd.NaT
        
        s = str(date_str).lower().strip()
        # Mapa de meses abreviados español
        meses = {
            "ene": "01", "feb": "02", "mar": "03", "abr": "04", "may": "05", "jun": "06",
            "jul": "07", "ago": "08", "sep": "09", "oct": "10", "nov": "11", "dic": "12"
        }
        
        try:
            # Intento formato '12-dic-25' o '12-dic-2025'
            for mes_name, mes_num in meses.items():
                if mes_name in s:
                    s = s.replace(mes_name, mes_num)
                    break
            
            # Reemplazar separadores comunes
            s = s.replace("-", "/").replace(".", "/")
            
            return pd.to_datetime(s, dayfirst=True)
        except:
            return pd.NaT

    if "FechaLlegadaChapas" in df.columns:
        df["FechaLlegadaChapas"] = df["FechaLlegadaChapas"].apply(parse_spanish_date)
    
    if "FechaLlegadaTroquel" in df.columns:
        df["FechaLlegadaTroquel"] = df["FechaLlegadaTroquel"].apply(parse_spanish_date)

    # --- FLAGS SOLO PENDIENTES ---
    def to_bool_series(names):
        for c in names:
            if c in df.columns:
                return df[c].astype(str).str.strip().str.lower().isin(["verdadero", "true", "si", "sí", "1", "x"])
        return pd.Series(False, index=df.index)

    df["_PEN_Corte_Bobina"] = to_bool_series(["CorteSNDdp"])
    df["_PEN_Guillotina"]   = to_bool_series(["GuillotinadoSNDpd"])
    df["_PEN_Barnizado"]    = to_bool_series(["Barniz"])
    df["_PEN_Encapado"]     = to_bool_series(["Encapa", "EncapadoSND"])
    df["_PEN_Cuño"]         = to_bool_series(["Cuño", "CuñoSND"])
    df["_PEN_Plastificado"]  = to_bool_series(["Plastifica", "PlastificadoSND"]) 
    df["_PEN_Stamping"]     = to_bool_series(["StampSNDdp", "StampingSND"])
    df["_PEN_OPP"]          = to_bool_series(["OPPSNDpd", "OPPSND"])
    df["_PEN_Troquelado"]   = to_bool_series(["TroqueladoSNDpd", "TroqueladoSND"])
    df["_PEN_Descartonado"] = to_bool_series(["DescartonadoSNDpd", "DescartonadoSND"])
    df["_PEN_Ventana"]      = to_bool_series(["PegadoVSNDpd", "PegadoVSND"])
    df["_PEN_Pegado"]       = to_bool_series(["PegadoSNDpd", "PegadoSND"])
    df["_IMP_Dorso"]      = to_bool_series(["Dorso"])      # Flexo → doble pasada
    df["_IMP_FreyDorDpd"] = to_bool_series(["FreyDorDpd"])    # Offset → doble pasada

    # --- TROQUEL PREFERIDO ---
    for c in ["CodigoTroquel", "CodigoTroquelTapa", "CodigoTroquelCuerpo", "CodTroTapa", "CodTroCuerpo"]:
        if c in df.columns:
            df["CodigoTroquel"] = df[c]
            break

    # --- IMPRESIÓN: SEPARAR OFFSET/FLEXO ---
    mat = df.get("MateriaPrima", "").astype(str).str.lower()
    imp_pend = to_bool_series(["ImpresionSNDpd", "ImpresionSND"])
    df["_PEN_ImpresionFlexo"]  = imp_pend & (mat.str.contains("micro", na=False) )
    df["_PEN_ImpresionOffset"] = imp_pend & (mat.str.contains("cartulina", na=False) | mat.str.contains("carton", na=False) | mat.str.contains("papel", na=False) )

    # --- OT_ID ---
    if "OT_id" not in df.columns:
        df["OT_id"] = (
           df["CodigoProducto"].astype(str).str.strip() + "-" + df["Subcodigo"].astype(str).str.strip() 
        )

    # --- NUEVO: IMAGEN DE PLANTA (PROCESOS EN CURSO) ---
    st.subheader("📸 Imagen de Planta (Procesos en Curso)")
    
    if "pending_processes" not in st.session_state:
        st.session_state.pending_processes = []

    with st.expander("Cargar procesos en curso (Prioridad Absoluta)"):
        st.info("⚠️ Los procesos cargados aquí se agendarán **primero** en la máquina seleccionada, eliminando esa tarea de la lista pendiente original para evitar duplicados.")
        
        col_p1, col_p2, col_p3, col_p4, col_p5 = st.columns([2, 1.5, 2, 1, 1])
        
        # 1. Máquina
        with col_p1:
            pp_maquina = st.selectbox("Máquina", options=maquinas_activas, key="pp_maquina")
            
        # 2. OT (Filtrada por proceso pendiente en esa máquina)
        # Buscar el proceso de la maquina
        proc_maq = cfg_plan["maquinas"].loc[cfg_plan["maquinas"]["Maquina"] == pp_maquina, "Proceso"]
        try:
             proc_maq_val = proc_maq.iloc[0] if not proc_maq.empty else ""
        except:
             proc_maq_val = ""

        # Mapeo simple de Proceso -> Columna _PEN
        # Normalizamos un poco (quitamos acentos y espacios para matchear lo que creamos arriba)
        # Las columnas creadas son: _PEN_Guillotina, _PEN_Barnizado, _PEN_ImpresionFlexo, etc.
        
        def normalize_proc_key(p):
            p = str(p).lower().replace("ó","o").replace("é","e").replace("í","i").replace("á","a").replace("ú","u")
            p = p.replace(" ", "") # impresionflexo
            return p

        # Mapa manual de seguridad o heuristica
        col_target = None
        p_clean = normalize_proc_key(proc_maq_val)
        
        # Intentamos matchear
        for c in df.columns:
            if c.startswith("_PEN_"):
                suffix = c.replace("_PEN_", "").lower()
                if suffix == p_clean:
                    col_target = c
                    break
        
        # Fallback especificos si la heuristica falla
        if not col_target:
            if "flexo" in p_clean: col_target = "_PEN_ImpresionFlexo"
            elif "offset" in p_clean: col_target = "_PEN_ImpresionOffset"
            elif "troquel" in p_clean: col_target = "_PEN_Troquelado"
            elif "pegad" in p_clean: col_target = "_PEN_Pegado"
        
        # Filtrado
        if col_target and col_target in df.columns:
            # Solo los que tienen TRUE en esa columna
            ots_disponibles = sorted(df[df[col_target] == True]["OT_id"].unique().tolist())
        else:
            # Si no encontramos mapeo, mostramos todas (fallback)
            ots_disponibles = sorted(df["OT_id"].unique().tolist()) if "OT_id" in df.columns else []

        with col_p2:
            pp_ot = st.selectbox("Orden de Trabajo (OT)", options=ots_disponibles, key="pp_ot")
            
        # 3. Cantidad Pendiente
        with col_p3:
            cliente_val = ""
            if pp_ot:
                 try: 
                     cliente_val = df.loc[df["OT_id"] == pp_ot, "Cliente"].iloc[0]
                 except: 
                     cliente_val = ""
            st.text_input("Cliente", value=cliente_val, disabled=True, key=f"pp_cli_{pp_ot}")

        with col_p4:
            pp_qty = st.number_input("Cant. Pendiente", min_value=1, value=1000, step=100, key="pp_qty")
            
        # 4. Botón Agregar
        with col_p5:
            st.write("") # Spacer
            st.write("") 
            if st.button("➕ Cargar", key="btn_add_pp"):
                st.session_state.pending_processes.append({
                    "maquina": pp_maquina,
                    "ot_id": pp_ot,
                    "cantidad_pendiente": pp_qty
                })
                st.success(f"Cargado: {pp_maquina} -> {pp_ot} ({pp_qty})")

        # Mostrar tabla de pendientes
        if st.session_state.pending_processes:
            # Mostrar tabla de pendientes
            st.write("📋 **Procesos en Curso Cargados:**")
            
            # Header simula tabla
            h1, h2, h3, h4 = st.columns([3, 3, 2, 1])
            h1.markdown("**Máquina**")
            h2.markdown("**OT**")
            h3.markdown("**Cant.**")
            h4.markdown("")

            for i, item in enumerate(st.session_state.pending_processes):
                c1, c2, c3, c4 = st.columns([3, 3, 2, 1])
                with c1: st.write(item["maquina"])
                with c2: st.write(item["ot_id"])
                with c3: st.write(item["cantidad_pendiente"])
                with c4:
                    if st.button("❌", key=f"del_pp_{i}", help="Eliminar este proceso"):
                        st.session_state.pending_processes.pop(i)
                        st.rerun()
            
            st.markdown("---")
            # Botón para limpiar todo si se equivocan
            if st.button("Limpiar TODO", key="btn_clear_pp"):
               st.session_state.pending_processes = []
               st.rerun()

    # Inyectamos en la config
    cfg["pending_processes"] = st.session_state.pending_processes
    # --- FIN NUEVO ---

    st.info("🧠 Generando programa…")

    def _cfg_hash(cfg):
        return hash(pd.util.hash_pandas_object(cfg["maquinas"], index=True).sum())
    
    # schedule, carga_md, resumen_ot, detalle_maquina = programar(df, cfg, start=fecha_inicio_plan, start_time=hora_inicio_plan)
    @st.cache_data(show_spinner="🧠 Calculando planificación…")
    def generar_planificacion(df, cfg, fecha_inicio_plan, hora_inicio_plan):
        # Ejecuta solo una vez mientras los parámetros no cambien
        cfg_hash = _cfg_hash(cfg)  # Forzar recálculo si cfg cambia
        return programar(df, cfg, start=fecha_inicio_plan, start_time=hora_inicio_plan)

    # 🧩 Llamada cacheada
    schedule, carga_md, resumen_ot, detalle_maquina = generar_planificacion(df, cfg_plan, fecha_inicio_plan, hora_inicio_plan)

    # ==========================
    # Métricas principales
    # ==========================

    col1, col2, col3, col4 = st.columns(4)
    total_ots = resumen_ot["OT_id"].nunique() if not resumen_ot.empty else 0
    atrasadas = int(resumen_ot["EnRiesgo"].sum()) if not resumen_ot.empty else 0
    horas_extra_total = float(carga_md["HorasExtra"].sum()) if not carga_md.empty else 0.0

    col1.metric("Órdenes planificadas", total_ots)
    col2.metric("Órdenes atrasadas", atrasadas)
    col3.metric("Horas extra (totales)", f"{horas_extra_total:.1f} h")
    col4.metric("Jornada (h/día)", f"{horas_por_dia(cfg):.1f}")

    # ==========================
    # Seguimiento visual (Gantt)
    # ==========================

    st.subheader("📊 Seguimiento (Gantt)")
    if not schedule.empty and _HAS_PLOTLY:
        schedule_gantt = schedule.copy() # Copiamos el original

        # Asegurarnos que las fechas no sean nulas
        min_plan_date = schedule_gantt["Inicio"].min().date() if not schedule_gantt["Inicio"].isnull().all() else date.today()
        max_plan_date = schedule_gantt["Fin"].max().date() if not schedule_gantt["Fin"].isnull().all() else date.today()

        st.markdown("##### 📅 Filtros de Fecha para el Gantt") # Título corregido

        tipo_filtro = st.radio(
            "Seleccionar Rango de Fechas:",
            ["Ver todo", "Día", "Semana",  "Mes"], # "Rango personalizado"],
            index=0,
            horizontal=True,
            key="filtro_fecha_radio"
            )
        
        range_start_dt = None # CORREGIDO: renombrado
        range_end_dt = None   # CORREGIDO: renombrado

        if tipo_filtro == "Día":
            fecha_dia = st.date_input("Seleccioná el día:", value=min_plan_date, min_value=min_plan_date, max_value=max_plan_date, key="filtro_dia")
            range_start_dt = pd.to_datetime(fecha_dia) + pd.Timedelta(hours=7) # CORREGIDO: Asignar a variable correcta
            range_end_dt = range_start_dt + pd.Timedelta(hours=9) # CORREGIDO: Asignar a variable correcta

        elif tipo_filtro == "Semana":
            fecha_semana = st.date_input("Seleccioná un día de la semana:", value=min_plan_date, min_value=min_plan_date, max_value=max_plan_date, key="filtro_semana")
            start_of_week = fecha_semana - pd.Timedelta(days=fecha_semana.weekday())
            range_start_dt = pd.to_datetime(start_of_week) + pd.Timedelta(hours=7) # CORREGIDO: Asignar a variable correcta y convertir a datetime
            range_end_dt = range_start_dt + pd.Timedelta(days=7) + pd.Timedelta(hours=9) # CORREGIDO: Asignar a variable correcta

        elif tipo_filtro == "Mes":
            fecha_mes = st.date_input("Seleccioná un día del mes:", value=min_plan_date, min_value=min_plan_date, max_value=max_plan_date, key="filtro_mes")
            range_start_dt = pd.to_datetime(fecha_mes.replace(day=1)) + pd.Timedelta(hours=7)
            next_month = (fecha_mes.replace(day=28) + pd.Timedelta(days=4))
            range_end_dt = pd.to_datetime(next_month.replace(day=1)) + pd.Timedelta(hours=9)

        elif tipo_filtro == "Ver todo":
            range_start_dt = pd.to_datetime(min_plan_date) + pd.Timedelta(hours=7)
            range_end_dt = pd.to_datetime(min_plan_date) + pd.Timedelta(days=10) + pd.Timedelta(hours=9)

        elif tipo_filtro == "Rango personalizado":
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                # CORREGIDO: Usar st.date_input (tu código tenía st.date.input)
                fecha_inicio_filtro = st.date_input( 
                    "Desde:",
                    value=min_plan_date,
                    min_value=min_plan_date,
                    max_value=max_plan_date,
                    )

            with col_f2:
                fecha_fin_filtro = st.date_input(
                    "Hasta:",
                    value=max_plan_date,
                    min_value=min_plan_date,
                    max_value=max_plan_date,
                    )
            range_start_dt = pd.to_datetime(fecha_inicio_filtro)
            range_end_dt = pd.to_datetime(fecha_fin_filtro) + pd.Timedelta(days=1)
        
        # --- BLOQUE DE FILTRADO CORREGIDO ---
        # 1. Movido FUERA del 'elif'
        # 2. Lógica de solapamiento ARREGLADA
        if range_start_dt is not None and range_end_dt is not None:
            
            # Lógica de solapamiento correcta:
            # La tarea termina DESPUÉS de que el rango empieza Y
            # la tarea empieza ANTES de que el rango termine.
            schedule_gantt = schedule_gantt[
                (schedule_gantt["Fin"] > range_start_dt) &
                (schedule_gantt["Inicio"] < range_end_dt)
            ]
        # --- FIN DE LA CORRECCIÓN ---

        def configurar_eje_x(fig_obj):
            """Ajusta el eje X segun el filtro activo."""
            if fig_obj is None:
                return

            if range_start_dt is not None and range_end_dt is not None:
                fig_obj.update_xaxes(range=[range_start_dt, range_end_dt])

            if tipo_filtro == "Día":
                fig_obj.update_xaxes(
                    dtick=3600000,  # 1 hora en milisegundos
                    tickformat="%H:%M",
                    tickangle=0,
                    showgrid=True,
                    gridcolor="rgba(128, 128, 128, 0.3)",
                    gridwidth=1.2,
                    layer="below traces",
                    tickfont=dict(size=11, color="#666666"),
                )
            else:
                fig_obj.update_xaxes(
                    dtick=86400000,  # 1 día en milisegundos
                    tickformat="%d %b",  # Día y mes
                    tickangle=0,
                    showgrid=True,
                    gridcolor="rgba(128, 128, 128, 0.3)",
                    gridwidth=1.5,
                    layer="below traces",
                    tickfont=dict(size=11, color="#666666"),
                )

                if range_start_dt is not None and range_end_dt is not None:
                    dias_es = {0: "Lun", 1: "Mar", 2: "Mié", 3: "Jue", 4: "Vie", 5: "Sáb", 6: "Dom"}
                    fechas = pd.date_range(start=range_start_dt.date(), end=range_end_dt.date(), freq="D")
                    ticktext = [f"{f.strftime('%d %b')}<br>{dias_es[f.weekday()]}" for f in fechas]
                    tickvals = [pd.Timestamp(f) for f in fechas]
                    fig_obj.update_xaxes(ticktext=ticktext, tickvals=tickvals)

                for f in fechas:
                        tickvals.append(f) # f ya es un Timestamp
                        
                        # Chequea si es fin de semana (Sábado=5, Domingo=6)
                        es_finde = f.weekday() >= 5
                        dia_habil = es_dia_habil(f, cfg)  # NUEVO: chequea si es día hábil

                        if not dia_habil:
                            # 1. Añade el sombreado rojo para el fin de semana
                            fig_obj.add_vrect(
                                x0=f,
                                x1=f + pd.Timedelta(days=1),
                                fillcolor="rgba(255, 0, 0, 0.15)", # Rojo translúcido
                                layer="below", # Detrás de las barras del gantt
                                line_width=0,
                            )
                            # 2. Pone el texto de la etiqueta en rojo
                            ticktext.append(f"<b><span style='color:red'>{f.strftime('%d %b')}<br>{dias_es[f.weekday()]}</span></b>")
                        else:
                            # 3. Etiqueta normal para días de semana
                            ticktext.append(f"{f.strftime('%d %b')}<br>{dias_es[f.weekday()]}")
                    
                # Aplica las nuevas etiquetas
                fig_obj.update_xaxes(ticktext=ticktext, tickvals=tickvals)
                # --- FIN DE LA MODIFICACIÓN ---

        vista = st.radio(
            "Seleccioná el tipo de seguimiento:",
            ["Por Orden de Trabajo (OT)", "Por Máquina"],
            horizontal=True
        )

        fig = None
        todas_las_ot = sorted(schedule["OT_id"].dropna().unique().tolist())
        if schedule_gantt.empty:
            st.info("No hay tareas planificadas en el rango de fechas seleccionado.")
        else:  
            try:
                if vista == "Por Orden de Trabajo (OT)":
                    opciones_ot = ["(Todas)"] + sorted(schedule_gantt["OT_id"].unique().tolist())
                    ot_seleccionada = st.selectbox(
                        "Seguimiento por OT:",
                        opciones_ot,
                        key="gantt_ot_select"
                    )
                    data_gantt = schedule_gantt if ot_seleccionada == "(Todas)" else schedule_gantt[schedule_gantt["OT_id"] == ot_seleccionada]

                    if data_gantt.empty:
                        # CORREGIDO: Mensaje más claro
                        st.info("La OT seleccionada no tiene tareas planificadas (o fue filtrada por fecha).")
                    else:
                        categorias_ot = sorted(data_gantt["OT_id"].dropna().unique().tolist())
                        fig = px.timeline(
                            data_gantt,
                            x_start="Inicio", x_end="Fin",
                            y="OT_id", color="Proceso",
                            color_discrete_map=color_map_procesos,
                            category_orders={"OT_id": categorias_ot},
                            hover_data=["Maquina", "Cliente", "Atraso_h", "DueDate"],
                            title="Procesos por Orden de Trabajo",
                        )
                        if tipo_filtro == "Día":
                            fig.update_layout(
                                yaxis=dict(
                                    categoryorder="array",
                                    categoryarray=categorias_ot
                                ),
                                bargap=0.80,
                                bargroupgap=1,
                            )
                            fig.update_traces(selector=dict(type="bar"), width=0.5)
                        if tipo_filtro != "Ver todo" and opciones_ot != "(Todas)" and tipo_filtro != "Semana" and tipo_filtro != "Mes":
                            fig.update_layout(
                                height=max(300, 30 * len(categorias_ot)),
                            )
                        fig.update_yaxes(autorange="reversed")
                        configurar_eje_x(fig)

                elif vista == "Por Máquina":
                    maquinas_unicas = schedule_gantt["Maquina"].dropna().unique().tolist()
                    maquinas_ordenadas = ordenar_maquinas_personalizado(maquinas_unicas)
                    fig = px.timeline(
                        schedule_gantt,
                        x_start="Inicio", x_end="Fin",
                        y="Maquina", color="Proceso",
                        color_discrete_map=color_map_procesos,
                        category_orders={"Maquina": maquinas_ordenadas},
                        hover_data=["OT_id", "Cliente", "Atraso_h", "DueDate"],
                        title="Procesos por Máquina", # Título corregido
                    )
                    categorias_maquinas = maquinas_ordenadas
                    fig.update_layout(
                        bargap=0.35,
                        bargroupgap=0.0,
                        height=max(420, 50 * len(categorias_maquinas))
                    )
                    fig.update_traces(selector=dict(type="bar"), width=0.5)
                    fig.update_yaxes(autorange="reversed")
                    configurar_eje_x(fig)

            except Exception as e:
                st.warning(f"No se pudo renderizar el gráfico: {e}")

        if fig is not None:
            df_downtimes = pd.DataFrame(cfg.get("downtimes", []))

            if not df_downtimes.empty and vista == "Por Máquina":
                df_downtimes["start"] = pd.to_datetime(df_downtimes["start"], errors="coerce")
                df_downtimes["end"] = pd.to_datetime(df_downtimes["end"], errors="coerce")
                df_downtimes["Proceso"] = "🔧 Paro programado"

                # Agregamos un trace adicional con Plotly Express
                fig_paros = px.timeline(
                    df_downtimes,
                    x_start="start", x_end="end",
                    y="maquina",
                    color="Proceso",
                    color_discrete_map={"🔧 Paro programado": "red"},
                    opacity=0.8,
                    hover_data={"start": True, "end": True},
                )

                # Hacemos las barras más finas y las ponemos encima
                fig_paros.update_traces(marker=dict(line_width=0), width=0.2)
                for trace in fig_paros.data:
                    fig.add_trace(trace)

                # Agregamos leyenda si no existe
                fig.add_annotation(
                    text="🔧 Paros programados",
                    xref="paper", yref="paper",
                    x=1.03, y=1,
                    showarrow=False,
                    font=dict(color="red", size=12)
                )
            st.plotly_chart(fig)
            
    elif not _HAS_PLOTLY:
        st.info("Para ver el Gantt instalá Plotly: `pip install plotly`")
    else:
        st.info("No hay tareas planificadas para mostrar el seguimiento.")

    # ==========================
    # 📋 Detalle (OT / Máquina)
    # ==========================

    st.subheader("🔎 Detalle interactivo")
    modo = st.radio("Ver detalle por:", ["Orden de Trabajo (OT)", "Máquina"], horizontal=True)

    # --- CORRECCIÓN: Usar 'schedule' (el DF completo) para las tablas de detalle ---
    if modo == "Orden de Trabajo (OT)":
        if not schedule.empty: # Usar 'schedule'
            opciones = ["(Todas)"] + sorted(schedule["OT_id"].unique().tolist()) # Usar 'schedule'
            elegido = st.selectbox("Elegí OT:", opciones)
            df_show = schedule if elegido == "(Todas)" else schedule[schedule["OT_id"] == elegido] # Usar 'schedule'
            df_show = df_show.drop(columns=["CodigoProducto", "Subcodigo"], errors="ignore")
            st.dataframe(df_show)
        else:
            st.info("No hay tareas planificadas (verificá pendientes o MPPlanta).")

    else:
        if not schedule.empty and detalle_maquina is not None and not detalle_maquina.empty: # Usar 'schedule'
            maquinas_disponibles = ordenar_maquinas_personalizado(detalle_maquina["Maquina"].unique().tolist())
            maquina_sel = st.selectbox("Seleccioná una máquina:", maquinas_disponibles)

            # Reunir detalle completo para esa máquina
            df_maquina = schedule[schedule["Maquina"] == maquina_sel].copy() # Usar 'schedule'

            # ... (Lógica para agregar CodigoTroquel y Colores) ...
            if "CodigoTroquel" not in df_maquina.columns and "CodigoTroquel" in df.columns:
                 df_maquina = df_maquina.merge(
                     df[["CodigoProducto", "Subcodigo", "CodigoTroquel"]],
                     how="left",
                     left_on=["CodigoProducto", "Subcodigo"],
                     right_on=["CodigoProducto", "Subcodigo"]
                 )

            if "Colores" not in df_maquina.columns and "Colores" in df.columns:
                 df_maquina = df_maquina.merge(
                     df[["CodigoProducto", "Subcodigo", "Colores"]],
                     how="left",
                     left_on=["CodigoProducto", "Subcodigo"],
                     right_on=["CodigoProducto", "Subcodigo"]
                 )
            
            df_maquina.sort_values(by="Inicio", inplace=True)

            # ... (Lógica de columnas dinámicas) ...
            if any(k in maquina_sel.lower() for k in ["troq", "manual", "autom", "duyan", "iberica"]):
                st.write("🧱 Mostrando código de troquel (agrupamiento interno).")
                cols = [
                    "OT_id", "Cliente-articulo", "PliAnc","PliLar", "Bocas","CantidadPliegosNetos", "CantidadPliegos", "CodigoTroquel", 
                    "Proceso", "Inicio", "Fin", "Duracion_h", "DueDate", 
                ]
            elif "bobina" in maquina_sel.lower():
                 st.write("📜 Mostrando detalles de bobina (Materia Prima / Medidas).")
                 cols = [
                    "OT_id", "Cliente-articulo", "MateriaPrima", "Gramaje", "PliAnc", "PliLar", "CantidadPliegos",
                    "Proceso", "Inicio", "Fin", "Duracion_h", "DueDate"
                ]
            elif any(k in maquina_sel.lower() for k in ["offset", "flexo", "impres", "heidel"]):
                st.write("🎨 Mostrando colores del trabajo de impresión.")
                cols = [
                    "OT_id", "Cliente-articulo", "Poses", "CantidadPliegosNetos","CantidadPliegos", "Colores",
                    "CodigoTroquel", "Proceso", "Inicio", "Fin", "Duracion_h", "DueDate", 
                ]
            else:
                cols = [
                    "OT_id", "Cliente-articulo", "CantidadPliegos", "Proceso",
                    "Inicio", "Fin", "Duracion_h", "DueDate"
                ]

            cols_exist = [c for c in cols if c in df_maquina.columns]
            df_maquina_display = df_maquina[cols_exist].drop(columns=["CodigoProducto", "Subcodigo"], errors="ignore")
            st.dataframe(df_maquina_display)
        else:
            st.info("No hay detalle por máquina disponible (verificá que se hayan generado tareas).")
            
    # ==========================
    # Resumen por OT
    # ==========================
    st.subheader("📦 Resumen por OT (Fin vs Entrega)")
    if not resumen_ot.empty:
        resumen_display = resumen_ot.sort_values(["EnRiesgo","Atraso_h","Fin_OT"], ascending=[False, False, True]).copy()
        st.dataframe(resumen_display)
    else:
        st.info("Sin resumen disponible.")
    # ==========================
    # Exportación a Excel
    # ==========================

    st.subheader("💾 Exportar")
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        # 1. Plan por Máquina (Lo que pidió el usuario)
        if not schedule.empty:
            plan_por_maquina = schedule.copy()
            # Ordenar por Máquina y luego por Inicio
            plan_por_maquina.sort_values(by=["Maquina", "Inicio"], inplace=True)
            
            # Seleccionar y reordenar columnas amigables
            cols_export = [
                "Maquina", "Inicio", "Fin", "Duracion_h", 
                "OT_id", "Cliente", "Cliente-articulo", "CodigoProducto", 
                "Proceso", "CantidadPliegos", "Colores", "CodigoTroquel", "DueDate"
            ]
            # Filtrar solo las que existan
            cols_final = [c for c in cols_export if c in plan_por_maquina.columns]
            
            plan_por_maquina[cols_final].to_excel(w, index=False, sheet_name="Plan por Máquina")
        
        # 2. Otras hojas útiles
        schedule.to_excel(w, index=False, sheet_name="Datos Crudos (Schedule)") 
        if not resumen_ot.empty:
            resumen_ot.to_excel(w, index=False, sheet_name="Resumen por OT")
        if not carga_md.empty:
            carga_md.to_excel(w, index=False, sheet_name="Carga Máquina-Día")
            
    buf.seek(0)
    
    
    st.download_button(
        "⬇️ Descargar Excel (.xlsx)",
        data=buf,
        file_name="Plan_Produccion_Theiler.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # 3. Opción CSV para Excel viejo / Configuración regional Argentina
    if not schedule.empty:
        plan_csv = schedule.copy()
        plan_csv.sort_values(by=["Maquina", "Inicio"], inplace=True)
        
        # Mismas columnas que la hoja principal del Excel
        cols_export = [
            "Maquina", "CodigoProducto", "Subcodigo","Cliente", "Cliente-articulo", "Inicio", "Fin", "Duracion_h", 
            "Proceso", "CantidadPliegos", "Colores", "CodigoTroquel", "DueDate"
        ]
        cols_final = [c for c in cols_export if c in plan_csv.columns]
        
        # Generar CSV con ; como separador y , para decimales
        csv_data = plan_csv[cols_final].to_csv(index=False, sep=';', decimal=',', encoding='utf-8-sig')
        
        st.download_button(
            "⬇️ Descargar CSV (Compatible Excel 2010)",
            data=csv_data,
            file_name="Plan_Produccion_Theiler.csv",
            mime="text/csv",
            help="Usá esta opción si el Excel normal te sale todo en una sola celda."
        )

else:
    st.info("⬆️ Subí el archivo Excel de órdenes para comenzar.")
