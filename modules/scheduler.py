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

def elegir_maquina(proceso, orden, cfg):
    """Selecciona la máquina adecuada según proceso y material (con debug)."""
    proc_lower = proceso.lower()
    print(f"\n🧩 [DEBUG] Evaluando proceso: {proceso}")

    # Mostrar todos los procesos configurados
    print("📋 Procesos en config:", cfg["maquinas"]["Proceso"].unique().tolist())

    # Filtrado original
    candidatos = cfg["maquinas"][cfg["maquinas"]["Proceso"].str.lower().str.contains(proc_lower.split()[0])]["Maquina"].tolist()
    print(f"🔍 Palabra clave buscada: '{proc_lower.split()[0]}' → Candidatos encontrados: {candidatos}")

    if not candidatos:
        print(f"⚠️ No se encontraron máquinas candidatas para '{proceso}'")
        return None

    # 🔹 Troquelado
    if proceso == "Troquelado":
        cant = float(orden.get("CantidadPliegos", 0))
        if cant > 3000 and "Automática" in candidatos:
            print("✅ Seleccionada troqueladora Automática (>3000 pliegos)")
            return "Automática"
        manuales = [m for m in candidatos if "manual" in m.lower()]
        if manuales:
            m_sel = manuales[hash(orden["CodigoProducto"]) % len(manuales)]
            print(f"✅ Seleccionada troqueladora Manual: {m_sel}")
            return m_sel

    # 🔹 Impresión
    if "impresión" in proc_lower:
        mat = str(orden.get("MateriaPrima", "")).lower()
        print(f"🧾 Materia prima: {mat}")

        # FLEXO → microcorrugado
        if "flexo" in proc_lower or "micro" in mat or "corrug" in mat:
            flexos = [m for m in candidatos if "flexo" in m.lower()]
            print(f"🎨 Flexo posibles: {flexos}")
            return flexos[0] if flexos else None

        # OFFSET → cartulina
        if "offset" in proc_lower or "cartulin" in mat:
            offsets = [m for m in candidatos if "offset" in m.lower()]
            print(f"🖨 Offset posibles: {offsets}")
            return offsets[0] if offsets else None

    # 🔹 Ventana
    if "ventan" in proc_lower:
        vent = [m for m in candidatos if "ventan" in m.lower()]
        print(f"🪟 Ventanas posibles: {vent}")
        return vent[0] if vent else None

    # 🔹 Pegado
    if "peg" in proc_lower:
        pegs = [m for m in candidatos if "peg" in m.lower() or "pegad" in m.lower()]
        print(f"📦 Pegadoras posibles: {pegs}")
        return pegs[0] if pegs else None

    # 🔹 Fallback
    print(f"⚙️ Default → {candidatos[0]}")
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
        pendientes = _procesos_pendientes_de_orden(row)
        for proceso in pendientes:
            maquina = elegir_maquina(proceso, row, cfg)
            if not maquina:
                print(f"⚠️ {ot} → no se encontró máquina para {proceso}")
                continue

            # Log específico para impresión y pegado
            if "impresión" in proceso.lower() or "pegado" in proceso.lower():
                print(f"🧱 {ot} → {proceso}, máquina candidata: {maquina}")

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
            })

    tasks = pd.DataFrame(tareas)
    if not tasks.empty:
        tasks["DueDate"] = pd.to_datetime(tasks["DueDate"], dayfirst=True, errors="coerce")
        print("📊 Tareas generadas:", tasks["Proceso"].value_counts(dropna=False).to_dict())
    else:
        print("⚠️ No se generaron tareas pendientes.")
    return tasks


# =======================================================
# Programador principal
# =======================================================

def programar(df_ordenes: pd.DataFrame, cfg, start=None):
    """Planifica todas las tareas pendientes respetando precedencias."""
    if df_ordenes.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    df_ordenes["OT_id"] = df_ordenes["CodigoProducto"].astype(str) + "-" + df_ordenes["Subcodigo"].astype(str)
    fecha_col = "FechaEntregaAjustada" if "FechaEntregaAjustada" in df_ordenes.columns else "FechaEntrega"

    agenda = construir_calendario(cfg, start=start)
    maquinas = cfg["maquinas"]["Maquina"].unique()
    ultimo_en_maquina = {m: None for m in maquinas}

    tasks = _expandir_tareas(df_ordenes, cfg, fecha_col)
    if tasks.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

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

    colas = {}
    for m in maquinas:
        q = tasks[tasks["Maquina"] == m].copy()
        if q.empty:
            colas[m] = deque()
            continue
        q.sort_values(by=["DueDate", "GroupKey", "CantidadPliegos"], ascending=[True, True, False], inplace=True)
        colas[m] = deque(q.to_dict("records"))

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
        proc = t["Proceso"]
        ot = t["OT_id"]
        prev = anterior.get(proc)
        if prev and prev in pendientes_por_ot[ot]:
            return prev in completado[ot]
        return True

    progreso = True
    while quedan_tareas() and progreso:
        progreso = False
        for maquina in maquinas:
            if not colas.get(maquina):
                continue

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

            for _ in range(idx_cand):
                colas[maquina].rotate(-1)
            t = colas[maquina].popleft()
            orden = df_ordenes.loc[t["idx"]]

            setup_h, proc_h = tiempo_operacion_h(orden, t["Proceso"], maquina, cfg)

            if usa_setup_menor(ultimo_en_maquina.get(maquina), orden, t["Proceso"]):
                setup_min = setup_menor_min(t["Proceso"], maquina, cfg)
                motivo = "Setup menor (cluster)"
            else:
                setup_min = setup_base_min(t["Proceso"], maquina, cfg)
                motivo = "Setup base"

            total_h = proc_h + setup_min / 60.0

            # ✅ Protección ante tiempos nulos
            if pd.isna(total_h) or total_h <= 0:
                print(f"⚠️ Se omitió {t['OT_id']} - {t['Proceso']} ({maquina}) por duración inválida ({total_h})")
                continue

            bloques = _reservar_en_agenda(agenda[maquina], total_h, cfg)
            if not bloques:
                print(f"⚠️ Agenda vacía al reservar {t['OT_id']} - {t['Proceso']} ({maquina})")
                continue

            inicio = bloques[0][0]
            fin = bloques[-1][1]

            # Carga por día
            for b_ini, b_fin in bloques:
                d = b_ini.date()
                horas = (b_fin - b_ini).total_seconds() / 3600.0
                carga_reg.append({
                    "Fecha": d,
                    "Maquina": maquina,
                    "HorasPlanificadas": horas,
                    "CapacidadDia": h_dia
                })

            atraso_h = 0.0
            if pd.notna(t["DueDate"]):
                due_dt = pd.to_datetime(t["DueDate"])
                if fin > due_dt:
                    atraso_h = (fin - due_dt).total_seconds() / 3600.0

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
            })
            ultimo_en_maquina[maquina] = orden.to_dict()
            completado[t["OT_id"]].add(t["Proceso"])
            progreso = True

    schedule = pd.DataFrame(filas)
    if not schedule.empty:
        schedule.sort_values(["OT_id", "Inicio"], inplace=True, ignore_index=True)

    fin_ot = schedule.groupby("OT_id")["Fin"].max().reset_index().rename(columns={"Fin": "Fin_OT"})
    due = schedule.groupby("OT_id")["DueDate"].max().reset_index()
    resumen_ot = fin_ot.merge(due, on="OT_id", how="left")
    resumen_ot["Atraso_h"] = (
        (resumen_ot["Fin_OT"] - resumen_ot["DueDate"]).dt.total_seconds() / 3600.0
    ).clip(lower=0).fillna(0.0).round(2)
    resumen_ot["EnRiesgo"] = resumen_ot["Atraso_h"] > 0

    carga_md = pd.DataFrame(carga_reg)
    if not carga_md.empty:
        carga_md = carga_md.groupby(["Fecha", "Maquina", "CapacidadDia"], as_index=False)["HorasPlanificadas"].sum()
        carga_md["HorasExtra"] = (carga_md["HorasPlanificadas"] - carga_md["CapacidadDia"]).clip(lower=0).round(2)

    return schedule, carga_md, resumen_ot
