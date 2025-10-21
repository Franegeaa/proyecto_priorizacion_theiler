import pandas as pd
from datetime import datetime, timedelta, time
from collections import defaultdict, deque

from modules.config_loader import (
    es_si, horas_por_dia, proximo_dia_habil, construir_calendario
)
from modules.tiempos_y_setup import (
    setup_base_min, setup_menor_min, usa_setup_menor, tiempo_operacion_h
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

def _procesos_pendientes_de_orden(orden: pd.Series):
    flujo = [
        "Guillotina",
        "Impresión Flexo",
        "Impresión Offset",
        "Barnizado",
        "OPP",
        "Troquelado",
        "Descartonado",
        "Ventana",
        "Pegado",
    ]
    pendientes = []

    # Marcar sólo procesos que están pendientes (True)
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
# Selección de máquina por proceso
# =======================================================

def elegir_maquina(proceso, orden, cfg, plan_actual=None):
    """Selecciona la máquina adecuada según proceso, material y agrupamientos."""
    proc_lower = proceso.lower()
    candidatos = cfg["maquinas"][cfg["maquinas"]["Proceso"].str.lower().str.contains(proc_lower.split()[0])]["Maquina"].tolist()

    if not candidatos:
        return None

    # === TROQUELADO ===
    if proceso == "Troquelado":
        cant = float(orden.get("CantidadPliegos", 0))
        cod_troquel = str(orden.get("CodigoTroquel", "")).strip().lower()

        # 1️⃣ Si >3000 pliegos → automática
        if cant > 3000 and "Automática" in candidatos:
            return "Automática"

        manuales = [m for m in candidatos if "manual" in m.lower()]
        if not manuales:
            return candidatos[0]

        # 2️⃣ Buscar si ya existe una orden con mismo troquel asignada a alguna manual
        if plan_actual is not None and cod_troquel:
            for m in manuales:
                ot_misma_maquina = plan_actual.get(m, [])
                for ot in ot_misma_maquina:
                    if str(ot.get("CodigoTroquel", "")).strip().lower() == cod_troquel:
                        return m  # agrupar en misma máquina

        # 3️⃣ Si no existe grupo, asignar a la manual con menor carga (cantidad de OTs)
        cargas = {m: len(plan_actual.get(m, [])) if plan_actual else 0 for m in manuales}
        m_sel = min(cargas, key=cargas.get)
        return m_sel

    # === IMPRESIÓN ===
    if "impresión" in proc_lower:
        mat = str(orden.get("MateriaPrima", "")).lower()
        if "flexo" in proc_lower or "micro" in mat or "corrug" in mat:
            flexos = [m for m in candidatos if "flexo" in m.lower()]
            return flexos[0] if flexos else None
        if "offset" in proc_lower or "cartulin" in mat:
            offsets = [m for m in candidatos if "offset" in m.lower()]
            return offsets[0] if offsets else None

    # === Ventana ===
    if "ventan" in proc_lower:
        vent = [m for m in candidatos if "ventan" in m.lower()]
        return vent[0] if vent else None

    # === Pegado ===
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

def _expandir_tareas(df: pd.DataFrame, cfg, fecha_col: str):
    tareas = []
    for idx, row in df.iterrows():
        ot = f"{row['CodigoProducto']}-{row['Subcodigo']}"
        colores = row.get("Colores", "")
        pendientes = _procesos_pendientes_de_orden(row)
        for proceso in pendientes:
            maquina = elegir_maquina(proceso, row, cfg)
            if not maquina:
                continue

            tareas.append({
                "idx": idx,
                "OT_id": ot,
                "CodigoProducto": row.get("CodigoProducto"),
                "Subcodigo": row.get("Subcodigo"),
                "Cliente": row.get("Cliente"),
                "Proceso": proceso,
                "Maquina": maquina,
                "DueDate": row.get(fecha_col),
                "GroupKey": _clave_prioridad_maquina(proceso, row),
                "CantidadPliegos": row.get("CantidadPliegos", 0),
                "MateriaPrimaPlanta": row.get("MateriaPrimaPlanta", row.get("MPPlanta")),
                "CodigoTroquel": row.get("CodigoTroquel") or row.get("CodTroTapa") or row.get("CodTroCuerpo") or "",
                "Colores": colores,
            })

    tasks = pd.DataFrame(tareas)
    if not tasks.empty:
        tasks["DueDate"] = pd.to_datetime(tasks["DueDate"], dayfirst=True, errors="coerce")
    return tasks


# =======================================================
# Programador principal
# =======================================================

def programar(df_ordenes: pd.DataFrame, cfg, start=None):
    """Planifica respetando precedencias + agrupamiento por troquel (manual/automática)."""
    if df_ordenes.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # ---------- IDs y fecha de compromiso ----------
    df_ordenes["OT_id"] = df_ordenes["CodigoProducto"].astype(str) + "-" + df_ordenes["Subcodigo"].astype(str)
    fecha_col = "FechaEntregaAjustada" if "FechaEntregaAjustada" in df_ordenes.columns else "FechaEntrega"

    # ---------- Calendario / estado por máquina ----------
    agenda = construir_calendario(cfg, start=start)
    maquinas = cfg["maquinas"]["Maquina"].unique()
    ultimo_en_maquina = {m: None for m in maquinas}

    # ---------- Expandir tareas ----------
    tasks = _expandir_tareas(df_ordenes, cfg, fecha_col)
    if tasks.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # ---------- Reasignación Troquelado Manual: mismo troquel => misma manual (menor carga), >3000 => Automática ----------
    troq_cfg = cfg["maquinas"][cfg["maquinas"]["Proceso"].str.lower().eq("troquelado")]
    manuales = [m for m in troq_cfg["Maquina"].tolist() if "manual" in str(m).lower()]
    auto_names = [m for m in troq_cfg["Maquina"].tolist() if "autom" in str(m).lower()]
    auto_name = auto_names[0] if auto_names else None

    if manuales:
        carga_manual = {m: 0 for m in manuales}
        troquel_a_manual = {}
        for i in tasks.index:
            if tasks.at[i, "Proceso"] != "Troquelado":
                continue
            cant = float(tasks.at[i, "CantidadPliegos"] or 0)
            troq = str(df_ordenes.loc[tasks.at[i, "idx"]].get("CodigoTroquel", "")).strip().lower()

            # Automática por tamaño
            if cant > 3000 and auto_name is not None:
                tasks.at[i, "Maquina"] = auto_name
                continue

            if not troq:
                continue

            if troq in troquel_a_manual:
                sel = troquel_a_manual[troq]
            else:
                sel = min(carga_manual, key=carga_manual.get)
                troquel_a_manual[troq] = sel
            tasks.at[i, "Maquina"] = sel
            carga_manual[sel] += 1

    # ---------- Construcción de colas ----------
    # Para troqueladoras: agrupar por troquel y ordenar los GRUPOS por DueDate mínima del grupo,
    # manteniendo consecutivas las OTs del mismo troquel.
    colas = {}

    def _cola_impresora(q: pd.DataFrame) -> deque:
        """Agrupa OTs con la misma combinación de colores en impresoras
        (Offset / Flexo), priorizando por DueDate mínima del grupo."""
        if q.empty:
            return deque()

        q = q.copy()
        
        if "Colores" in q.columns:
            colores = q["Colores"]
        else:
            colores = pd.Series("", index=q.index)

        q["_color_key"] = (
            colores
            .fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
        )

        grupos = []
        for color_key, g in q.groupby("_color_key", dropna=False):
            due_min = pd.to_datetime(g["DueDate"], errors="coerce").min()
            if pd.isna(due_min):
                due_min = pd.Timestamp.max

            # Orden interno dentro del grupo
            g_sorted = g.sort_values(["DueDate", "CantidadPliegos"], ascending=[True, False])
            grupos.append((due_min, color_key, g_sorted.to_dict("records")))

        # Priorizar los grupos por DueDate más próxima
        grupos.sort(key=lambda x: x[0])

        lista_final = []
        for _, _, recs in grupos:
            lista_final.extend(recs)

        return deque(lista_final)

    def _cola_troquelada(q: pd.DataFrame) -> deque:
        """Agrupa OTs con el mismo troquel para que se planifiquen consecutivas,
        priorizando los grupos según la menor DueDate del conjunto (DEBUG)."""
        if q.empty:
            return deque()

        q = q.copy()

        # === Obtener columna de troquel ===
        if "CodigoTroquel" in q.columns:
            troq_col = q["CodigoTroquel"]
        elif "CodTroTapa" in q.columns:
            troq_col = q["CodTroTapa"]
        elif "CodTroCuerpo" in q.columns:
            troq_col = q["CodTroCuerpo"]
        else:
            troq_col = pd.Series("", index=q.index)

        q["_troq_key"] = troq_col.fillna("").astype(str).str.strip().str.lower()

        grupos = []
        for troq, g in q.groupby("_troq_key", dropna=False):
            due_min = pd.to_datetime(g["DueDate"], errors="coerce").min()
            if pd.isna(due_min):
                due_min = pd.Timestamp.max

            g_sorted = g.sort_values(["DueDate", "CantidadPliegos"], ascending=[True, False])
            grupos.append((due_min, troq, g_sorted.to_dict("records")))

        # Ordenar por due_min
        grupos.sort(key=lambda x: x[0])

        # Aplanar manteniendo agrupamiento
        lista = []
        for _, _, recs in grupos:
            lista.extend(recs)

        return deque(lista)


    for m in maquinas:
        q = tasks[tasks["Maquina"] == m].copy()
        if q.empty:
            colas[m] = deque()
            continue

        m_lower = m.lower()

        if ("manual" in m_lower) or ("autom" in m_lower) or ("troquel" in m_lower):
            colas[m] = _cola_troquelada(q)
        elif ("offset" in m_lower) or ("flexo" in m_lower) or ("impres" in m_lower):
            colas[m] = _cola_impresora(q)
        else:
            q.sort_values(by=["DueDate", "GroupKey", "CantidadPliegos"],
                        ascending=[True, True, False], inplace=True)
            colas[m] = deque(q.to_dict("records"))

    # ---------- Precedencias ----------
    anterior = {
        "Impresión Flexo": "Guillotina",
        "Impresión Offset": "Guillotina",
        "Barnizado": "Impresión Offset",
        "OPP": "Encapado",
        "Troquelado": "OPP",
        "Descartonado": "Troquelado",
        "Ventana": "Descartonado",
        "Pegado": "Ventana",
    }

    pendientes_por_ot = defaultdict(set)
    for _, t in tasks.iterrows():
        pendientes_por_ot[t["OT_id"]].add(t["Proceso"])
    completado = defaultdict(set)

    carga_reg = []
    filas = []
    h_dia = horas_por_dia(cfg)

    def quedan_tareas():
        return any(len(q) > 0 for q in colas.values())

    def lista_para_ejecutar(t):
        proc = t["Proceso"]; ot = t["OT_id"]; prev = anterior.get(proc)
        if prev and prev in pendientes_por_ot[ot]:
            return prev in completado[ot]
        return True

    # ---------- Bucle de planificación ----------
    progreso = True
    while quedan_tareas() and progreso:
        progreso = False
        for maquina in maquinas:
            if not colas.get(maquina):
                continue

            # elegimos la primera ejecutable con MP disponible
            idx_cand = None
            for i, t in enumerate(colas[maquina]):
                mp = str(t.get("MateriaPrimaPlanta")).strip().lower()
                mp_ok = (mp in ("false", "0", "no", "falso", "")) or (t.get("MateriaPrimaPlanta") is False)
                if not mp_ok:
                    continue
                if lista_para_ejecutar(t):
                    idx_cand = i
                    break
            if idx_cand is None:
                continue

            # traer candidata al frente
            for _ in range(idx_cand):
                colas[maquina].rotate(-1)
            t = colas[maquina].popleft()
            orden = df_ordenes.loc[t["idx"]]

            # tiempos
            _, proc_h = tiempo_operacion_h(orden, t["Proceso"], maquina, cfg)

            # setup base
            setup_min = setup_base_min(t["Proceso"], maquina, cfg)
            motivo = "Setup base"

            # troquel consecutivo => setup 0
            if (
                t["Proceso"] == "Troquelado"
                and ultimo_en_maquina.get(maquina)
                and str(ultimo_en_maquina[maquina].get("CodigoTroquel", "")).strip().lower()
                   == str(orden.get("CodigoTroquel", "")).strip().lower()
            ):
                setup_min = 0
                motivo = "Mismo troquel (sin setup)"
            elif usa_setup_menor(ultimo_en_maquina.get(maquina), orden, t["Proceso"]):
                setup_min = setup_menor_min(t["Proceso"], maquina, cfg)
                motivo = "Setup menor (cluster)"

            total_h = proc_h + setup_min/60.0
            if pd.isna(total_h) or total_h <= 0:
                continue

            # reservar agenda
            bloques = _reservar_en_agenda(agenda[maquina], total_h, cfg)
            if not bloques:
                continue
            inicio = bloques[0][0]; fin = bloques[-1][1]

            # carga por día
            for b_ini, b_fin in bloques:
                d = b_ini.date()
                horas = (b_fin - b_ini).total_seconds()/3600.0
                carga_reg.append({"Fecha": d, "Maquina": maquina, "HorasPlanificadas": horas, "CapacidadDia": h_dia})

            # atraso
            atraso_h = 0.0
            if pd.notna(t["DueDate"]):
                due_dt = pd.to_datetime(t["DueDate"])
                if fin > due_dt:
                    atraso_h = (fin - due_dt).total_seconds()/3600.0

            # salida (incluye troquel/colores)
            filas.append({
                "OT_id": t["OT_id"],
                "CodigoProducto": t["CodigoProducto"],
                "Subcodigo": t["Subcodigo"],
                "Cliente": t["Cliente"],
                "Proceso": t["Proceso"],
                "Maquina": t["Maquina"],
                "Setup_min": round(setup_min, 2),
                "Proceso_h": round(proc_h, 3),
                "Inicio": inicio,
                "Fin": fin,
                "DueDate": pd.to_datetime(t["DueDate"]) if pd.notna(t["DueDate"]) else pd.NaT,
                "Motivo": motivo,
                "Atraso_h": round(atraso_h, 2),
                "CodigoTroquel": orden.get("CodigoTroquel"),
                "Colores": orden.get("Colores"),
            })

            ultimo_en_maquina[maquina] = orden.to_dict()
            completado[t["OT_id"]].add(t["Proceso"])
            progreso = True

    # ---------- Salidas ----------
    schedule = pd.DataFrame(filas)
    if not schedule.empty:
        schedule.sort_values(["OT_id", "Inicio"], inplace=True, ignore_index=True)

    if not schedule.empty:
        fin_ot = schedule.groupby("OT_id")["Fin"].max().reset_index().rename(columns={"Fin": "Fin_OT"})
        due = schedule.groupby("OT_id")["DueDate"].max().reset_index()
        resumen_ot = fin_ot.merge(due, on="OT_id", how="left")
        resumen_ot["Atraso_h"] = (
            (resumen_ot["Fin_OT"] - resumen_ot["DueDate"]).dt.total_seconds()/3600.0
        ).clip(lower=0).fillna(0.0).round(2)
        resumen_ot["EnRiesgo"] = resumen_ot["Atraso_h"] > 0
    else:
        resumen_ot = pd.DataFrame(columns=["OT_id","Fin_OT","DueDate","Atraso_h","EnRiesgo"])

    carga_md = pd.DataFrame(carga_reg)
    if not carga_md.empty:
        carga_md = carga_md.groupby(["Fecha","Maquina","CapacidadDia"], as_index=False)["HorasPlanificadas"].sum()
        carga_md["HorasExtra"] = (carga_md["HorasPlanificadas"] - carga_md["CapacidadDia"]).clip(lower=0).round(2)

    detalle_maquina = (
        schedule.sort_values(["Maquina","Inicio"])
        .groupby("Maquina")[["OT_id","Proceso","Inicio","Fin","CodigoTroquel","Colores","DueDate"]]
        .apply(lambda x: x.reset_index(drop=True))
        .reset_index(level=0)
    )

    return schedule, carga_md, resumen_ot, detalle_maquina