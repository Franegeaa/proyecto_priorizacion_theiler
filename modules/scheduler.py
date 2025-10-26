import pandas as pd
from datetime import datetime, timedelta, time
from collections import defaultdict, deque

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
    """Reserva 'horas_necesarias' en la agenda de una máquina.
    Retorna [(inicio, fin)] (puede partirse en varios días)."""
    fecha = agenda_m["fecha"]
    hora_actual = datetime.combine(fecha, agenda_m["hora"])
    resto = agenda_m["resto_horas"]
    h_dia = horas_por_dia(cfg)

    bloques = []
    h = horas_necesarias
    while h > 1e-9:
        if resto <= 1e-9:
            fecha = proximo_dia_habil(fecha + timedelta(days=1), cfg)
            hora_actual = datetime.combine(fecha, time(8, 0))
            resto = h_dia
        usar = min(h, resto)
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
    """Devuelve la lista de procesos pendientes según los flags de la orden y el orden estándar."""
    flujo = orden_std or [
        "Guillotina", "Impresión Flexo", "Impresión Offset", "Barnizado",
        "OPP", "Stamping", "Cuño", "Encapado", "Troquelado",
        "Descartonado", "Ventana", "Pegado"
    ]

    pendientes = []
    if es_si(orden.get("_PEN_Guillotina")):
        pendientes.append("Guillotina")
    if es_si(orden.get("_PEN_ImpresionFlexo")):
        pendientes.append("Impresión Flexo")
    if es_si(orden.get("_PEN_ImpresionOffset")):
        pendientes.append("Impresión Offset")
    if es_si(orden.get("_PEN_Barnizado")):
        pendientes.append("Barnizado")
    if es_si(orden.get("_PEN_OPP")):
        pendientes.append("OPP")
    if es_si(orden.get("_PEN_Troquelado")):
        pendientes.append("Troquelado")
    if es_si(orden.get("_PEN_Descartonado")):
        pendientes.append("Descartonado")
    if es_si(orden.get("_PEN_Ventana")):
        pendientes.append("Ventana")
    if es_si(orden.get("_PEN_Pegado")):
        pendientes.append("Pegado")

    orden_idx = {p: i for i, p in enumerate(flujo)}
    pendientes.sort(key=lambda p: orden_idx.get(p, 999))
    return pendientes


# =======================================================
# Selección de máquina
# =======================================================

def elegir_maquina(proceso, orden, cfg, plan_actual=None):
    """Selecciona la máquina adecuada según proceso, material y agrupamientos."""
    proc_lower = proceso.lower()
    candidatos = cfg["maquinas"][cfg["maquinas"]["Proceso"].str.lower().str.contains(proc_lower.split()[0])]["Maquina"].tolist()
    if not candidatos:
        return None

    # Troquelado
    if proceso == "Troquelado":
        cant = float(orden.get("CantidadPliegos", 0)) / float(orden.get("Boca1_ddp", 1) or 1)
        cod_troquel = str(orden.get("CodigoTroquel", "")).strip().lower()
        manuales = [m for m in candidatos if "manual" in m.lower()]
        auto = [m for m in candidatos if "autom" in m.lower()]

        if cant > 3000 and auto:
            return auto[0]
        if not manuales:
            return candidatos[0]

        plan_actual = plan_actual or {}
        cargas_horas = {m: sum(item.get("horas", 0) for item in plan_actual.get(m, [])) for m in manuales}
        return min(cargas_horas, key=cargas_horas.get)

    # Impresión
    if "impresión" in proc_lower:
        mat = str(orden.get("MateriaPrima", "")).lower()
        if "flexo" in proc_lower or "micro" in mat:
            flexos = [m for m in candidatos if "flexo" in m.lower()]
            return flexos[0] if flexos else None
        if "offset" in proc_lower or "cartulin" in mat:
            offsets = [m for m in candidatos if "offset" in m.lower()]
            return offsets[0] if offsets else None

    # Ventana
    if "ventan" in proc_lower:
        vent = [m for m in candidatos if "ventan" in m.lower()]
        return vent[0] if vent else None

    # Pegado
    if "peg" in proc_lower:
        pegs = [m for m in candidatos if "peg" in m.lower() or "pegad" in m.lower()]
        return pegs[0] if pegs else None

    return candidatos[0]


# =======================================================
# Claves de prioridad
# =======================================================

def _clave_prioridad_maquina(proceso: str, orden: pd.Series):
    marca = str(orden.get("Cliente") or "").strip().lower()
    colores = str(orden.get("Colores") or "").strip().lower()
    troquel = str(orden.get("CodigoTroquel") or "").strip().lower()
    material = str(orden.get("MateriaPrima") or "").strip().lower()
    pli_anc = orden.get("PliAnc")
    pli_lar = orden.get("PliLar")

    if proceso in ("Impresión Flexo", "Impresión Offset"):
        return (marca, colores, pli_anc, pli_lar)
    if proceso == "Troquelado":
        return (troquel,)
    if proceso == "Ventana":
        return (material, pli_anc, pli_lar)
    return tuple()


# =======================================================
# Expandir tareas
# =======================================================

def _expandir_tareas(df: pd.DataFrame, cfg):
    tareas = []
    plan_actual = defaultdict(list)

    for idx, row in df.iterrows():
        ot = f"{row['CodigoProducto']}-{row['Subcodigo']}"
        pendientes = _procesos_pendientes_de_orden(row, cfg.get("orden_std"))

        for proceso in pendientes:
            maquina = elegir_maquina(proceso, row, cfg, plan_actual)
            if not maquina:
                continue

            cant_prod = float(row.get("CantidadProductos", row.get("CantidadPliegos", 0)) or 0)
            poses = float(row.get("Poses", 1) or 1)
            bocas = float(row.get("BocasTroquel", row.get("Boca1_ddp", 1)) or 1)

            if proceso.lower().startswith("impres"):
                pliegos = cant_prod / poses if poses > 0 else cant_prod
            elif proceso.lower().startswith("troquel"):
                pliegos = cant_prod / bocas if bocas > 0 else cant_prod
            else:
                pliegos = float(row.get("CantidadPliegos", cant_prod))

            tareas.append({
                "idx": idx,
                "OT_id": ot,
                "CodigoProducto": row["CodigoProducto"],
                "Subcodigo": row["Subcodigo"],
                "Cliente": row["Cliente"],
                "Proceso": proceso,
                "Maquina": maquina,
                "DueDate": row["FechaEntrega"],
                "GroupKey": _clave_prioridad_maquina(proceso, row),
                "MateriaPrimaPlanta": row.get("MateriaPrimaPlanta", row.get("MPPlanta")),
                "CodigoTroquel": row.get("CodigoTroquel") or "",
                "Colores": row.get("Colores", ""),
                "CantidadPliegos": pliegos,
                "Bocas": bocas,
                "Poses": poses,
            })

    tasks = pd.DataFrame(tareas)
    tasks.drop_duplicates(subset=["OT_id", "Proceso"], inplace=True)
    if not tasks.empty:
        tasks["DueDate"] = pd.to_datetime(tasks["DueDate"], dayfirst=True, errors="coerce")

        # 🔹 Reordenar según el orden estándar de procesos
        if "orden_std" in cfg:
            orden_map = {p: i for i, p in enumerate(cfg["orden_std"], start=1)}
            tasks["_orden_proceso"] = tasks["Proceso"].map(orden_map).fillna(9999)
            tasks.sort_values(["OT_id", "_orden_proceso"], inplace=True)
            tasks.drop(columns=["_orden_proceso"], inplace=True)

    return tasks


# =======================================================
# Programador principal
# =======================================================

def programar(df_ordenes: pd.DataFrame, cfg, start=None):
    """Planifica respetando precedencias + agrupamiento por troquel (manual/automática)."""

    if df_ordenes.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    df_ordenes["OT_id"] = df_ordenes["CodigoProducto"].astype(str) + "-" + df_ordenes["Subcodigo"].astype(str)
    agenda = construir_calendario(cfg, start=start)
    maquinas = cfg["maquinas"]["Maquina"].unique()

    # =======================================================
    # ORDEN LÓGICO DE PLANIFICACIÓN POR MÁQUINA
    # =======================================================

    flujo_estandar = [
        "Guillotina",
        "Impresión Flexo",
        "Impresión Offset",
        "Barnizado",
        "Troquelado",
        "Descartonado",
        "Ventana",
        "Pegado",
        "OPP",
        "Encapado",
    ]

    def _orden_proceso(maquina):
        proc_name = cfg["maquinas"].loc[cfg["maquinas"]["Maquina"] == maquina, "Proceso"]
        if proc_name.empty:
            return 999
        proc = proc_name.iloc[0]
        for i, p in enumerate(flujo_estandar):
            if p.lower() in proc.lower():
                return i
        return 999

    maquinas = sorted(cfg["maquinas"]["Maquina"].unique(), key=_orden_proceso)

    print("\n🧭 Orden lógico de planificación por máquina:")
    for m in maquinas:
        print(f"   - {m}")  
    ultimo_en_maquina = {m: None for m in maquinas}

    tasks = _expandir_tareas(df_ordenes, cfg)
    if tasks.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # ---------- Flujo estándar ----------
    flujo_estandar = cfg.get("orden_std", [
        "Guillotina", "Impresión Flexo", "Impresión Offset", "Barnizado",
        "Troquelado", "Descartonado", "Ventana", "Pegado"
    ])

    anterior = {flujo_estandar[i]: flujo_estandar[i - 1] for i in range(1, len(flujo_estandar))}
    pendientes_por_ot = defaultdict(set)
    for _, t in tasks.iterrows():
        pendientes_por_ot[t["OT_id"]].add(t["Proceso"])
    completado = defaultdict(set)
    fin_proceso = defaultdict(dict)  # 🔹 Nuevo: registro de hora de fin por OT y proceso

    carga_reg, filas = [], []
    h_dia = horas_por_dia(cfg)

    def quedan_tareas():
        return any(len(q) > 0 for q in colas.values())

    # ---------- Construcción de colas ----------
    colas = {}
    for m in maquinas:
        q = tasks[tasks["Maquina"] == m].copy()
        q.sort_values(by=["DueDate"], inplace=True)
        colas[m] = deque(q.to_dict("records"))

    # ---------- Lógica de dependencias ----------
    def lista_para_ejecutar(t):
        proc = t["Proceso"]
        ot = t["OT_id"]

        # Si no hay orden estándar, ejecutar normal
        orden_std = cfg.get("orden_std", [])
        if not orden_std:
            return True

        # Índice del proceso actual en el flujo estándar
        if proc not in orden_std:
            return True
        idx_actual = orden_std.index(proc)

        # Buscar todos los procesos anteriores en el flujo estándar
        procesos_previos = orden_std[:idx_actual]

        # Filtrar los que realmente forman parte de esta OT
        procesos_previos_ot = [p for p in procesos_previos if p in pendientes_por_ot[ot]]

        # Si no tiene procesos anteriores pendientes, puede ejecutarse
        if not procesos_previos_ot:
            return True

        # Si alguno de los anteriores aún no se completó → no puede ejecutarse
        for p_prev in procesos_previos_ot:
            if p_prev not in completado[ot]:
                return False

            fin_prev = fin_proceso[ot].get(p_prev)
            if fin_prev:
                fecha_agenda = datetime.combine(agenda[t["Maquina"]]["fecha"], agenda[t["Maquina"]]["hora"])
                if fecha_agenda < fin_prev:
                    # Ajustar la agenda para iniciar justo después del último anterior
                    agenda[t["Maquina"]]["fecha"] = fin_prev.date()
                    agenda[t["Maquina"]]["hora"] = fin_prev.time()
                    agenda[t["Maquina"]]["resto_horas"] = max(0, horas_por_dia(cfg) - (fin_prev.hour - 8))

        return True

    # ---------- Bucle de planificación ----------
    progreso = True
    while quedan_tareas() and progreso:
        progreso = False
        for maquina in maquinas:
            if not colas.get(maquina):
                continue

            idx_cand = None
            for i, t in enumerate(colas[maquina]):
                if lista_para_ejecutar(t):
                    idx_cand = i
                    break
            if idx_cand is None:
                continue

            for _ in range(idx_cand):
                colas[maquina].rotate(-1)
            t = colas[maquina].popleft()
            orden = df_ordenes.loc[t["idx"]]

            _, proc_h = tiempo_operacion_h(orden, t["Proceso"], maquina, cfg)
            setup_min = setup_base_min(t["Proceso"], maquina, cfg)
            total_h = proc_h + setup_min / 60.0
            if pd.isna(total_h) or total_h <= 0:
                continue

            bloques = _reservar_en_agenda(agenda[maquina], total_h, cfg)
            if not bloques:
                continue
            inicio = bloques[0][0]
            fin = bloques[-1][1]

            # Registro de fin de proceso para dependencias
            fin_proceso[t["OT_id"]][t["Proceso"]] = fin

            # Guardar carga y resultado
            for b_ini, b_fin in bloques:
                d = b_ini.date()
                horas = (b_fin - b_ini).total_seconds() / 3600.0
                carga_reg.append({"Fecha": d, "Maquina": maquina, "HorasPlanificadas": horas, "CapacidadDia": h_dia})

            filas.append({
                "OT_id": t["OT_id"],
                "CodigoProducto": t["CodigoProducto"],
                "Subcodigo": t["Subcodigo"],
                "CantidadPliegos": t["CantidadPliegos"],
                "Bocas": t["Bocas"],
                "Poses": t["Poses"],
                "Cliente": t["Cliente"],
                "Proceso": t["Proceso"],
                "Maquina": t["Maquina"],
                "Setup_min": round(setup_min, 2),
                "Proceso_h": round(proc_h, 3),
                "Inicio": inicio,
                "Fin": fin,
                "DueDate": pd.to_datetime(t["DueDate"]) if pd.notna(t["DueDate"]) else pd.NaT,
            })

            completado[t["OT_id"]].add(t["Proceso"])
            progreso = True

    # ---------- Salidas ----------
    schedule = pd.DataFrame(filas)
    if not schedule.empty:
        schedule.sort_values(["OT_id", "Inicio"], inplace=True, ignore_index=True)

    carga_md = pd.DataFrame(carga_reg)
    if not carga_md.empty:
        carga_md = carga_md.groupby(["Fecha", "Maquina", "CapacidadDia"], as_index=False)["HorasPlanificadas"].sum()
        carga_md["HorasExtra"] = (carga_md["HorasPlanificadas"] - carga_md["CapacidadDia"]).clip(lower=0).round(2)

    resumen_ot = (
        schedule.groupby("OT_id")["Fin"].max().reset_index().rename(columns={"Fin": "Fin_OT"})
    )
    if not schedule.empty:
        due = schedule.groupby("OT_id")["DueDate"].max().reset_index()
        resumen_ot = resumen_ot.merge(due, on="OT_id", how="left")
        resumen_ot["Atraso_h"] = (
            (resumen_ot["Fin_OT"] - resumen_ot["DueDate"]).dt.total_seconds() / 3600.0
        ).clip(lower=0).fillna(0.0).round(2)
        resumen_ot["EnRiesgo"] = resumen_ot["Atraso_h"] > 0
    else:
        resumen_ot = pd.DataFrame(columns=["OT_id", "Fin_OT", "DueDate", "Atraso_h", "EnRiesgo"])

    detalle_maquina = (
        schedule.sort_values(["Maquina", "Inicio"])
        .groupby("Maquina")[["OT_id", "Proceso", "Inicio", "Fin", "CodigoProducto", "DueDate"]]
        .apply(lambda x: x.reset_index(drop=True))
        .reset_index(level=0)
    )

    if not schedule.empty:
        schedule = schedule.merge(
            resumen_ot[["OT_id", "Atraso_h"]],
            on="OT_id", how="left"
        )

    # ==========================================================
    # 🔍 DEBUG: Verificación de orden de procesos por OT
    # ==========================================================
    try:
        flujo_estandar = [
            "Guillotina",
            "Impresión Flexo",
            "Impresión Offset",
            "Barnizado",
            "Troquelado",
            "Descartonado",
            "Ventana",
            "Pegado",
        ]
        orden_idx = {p: i for i, p in enumerate(flujo_estandar)}

        print("\n==================== DEBUG ORDEN DE PROCESOS ====================")
        for ot_id, g in schedule.groupby("OT_id"):
            g_sorted = g.sort_values("Inicio")
            procesos = g_sorted["Proceso"].tolist()

            # Convertimos a índices (si un proceso no está en el estándar, le damos 999)
            indices = [orden_idx.get(p, 999) for p in procesos]

            # Buscamos desorden
            desordenes = []
            for i in range(1, len(indices)):
                if indices[i] < indices[i - 1]:
                    desordenes.append((procesos[i - 1], procesos[i]))

            if desordenes:
                print(f"⚠️  OT {ot_id} tiene procesos fuera de orden:")
                for prev, post in desordenes:
                    print(f"   → {prev} ocurre antes que {post}")
            else:
                print(f"✅ OT {ot_id} respeta el orden estándar ({' → '.join(procesos)})")
        print("=================================================================\n")

    except Exception as e:
        print(f"[DEBUG ERROR]: No se pudo verificar el orden de procesos: {e}")

    return schedule, carga_md, resumen_ot, detalle_maquina
