import pandas as pd
from datetime import datetime, timedelta, time, date
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
# Definición de procesos pendientes para cada OT (usan _PEN_*)
# =======================================================

def _procesos_pendientes_de_orden(orden: pd.Series):
    """Devuelve lista de procesos pendientes para esta OT en orden estándar."""
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

    # Ordenar según flujo
    orden_idx = {p: i for i, p in enumerate(flujo)}
    pendientes.sort(key=lambda p: orden_idx.get(p, 999))
    return pendientes


# =======================================================
# Selección de máquina por proceso (según tus reglas)
# =======================================================

def _elegir_maquina_proceso(proceso: str, orden: pd.Series, cfg):
    candidatos = cfg["maquinas"].query("Proceso==@proceso")["Maquina"].tolist()
    if not candidatos:
        return None

    if proceso == "Troquelado" and float(orden.get("CantidadPliegos", 0)) > 3000:
        if "Automática" in candidatos:
            return "Automática"

    if proceso == "Impresión Flexo" and "Flexo" in candidatos:
        return "Flexo"
    if proceso == "Impresión Offset" and "Offset" in candidatos:
        return "Offset"

    if proceso == "Ventana" and "Ventanas" in candidatos:
        return "Ventanas"

    return candidatos[0]


# =======================================================
# Claves de prioridad por máquina (minimizan setups)
# =======================================================

def _clave_prioridad_maquina(proceso: str, orden: pd.Series):
    """Tupla de ordenamiento para clusterizar y reducir setups."""
    marca = str(orden.get("Cliente") or "").strip().lower()
    colores = str(orden.get("Colores") or "").strip().lower()
    troquel = str(orden.get("CodigoTroquel") or "").strip().lower()
    material = str(orden.get("MateriaPrima") or "").strip().lower()
    pli_anc = orden.get("PliAnc")
    pli_lar = orden.get("PliLar")

    if proceso in ("Impresión Flexo", "Impresión Offset"):
        # Marca → Colores → Tamaño
        return (marca, colores, pli_anc, pli_lar)
    if proceso == "Troquelado":
        return (troquel,)
    if proceso == "Ventana":
        return (material, pli_anc, pli_lar)
    return tuple()


# =======================================================
# Expandir en tareas por proceso pendiente
# =======================================================

def _expandir_tareas(df: pd.DataFrame, cfg, fecha_col: str):
    """
    Devuelve DataFrame 'tasks' con una fila por proceso pendiente:
    [idx, OT_id, Proceso, Maquina, DueDate, GroupKey, CantidadPliegos, MateriaPrimaPlanta]
    """
    tareas = []
    for idx, row in df.iterrows():
        ot = f"{row['CodigoProducto']}-{row['Subcodigo']}"
        pendientes = _procesos_pendientes_de_orden(row)
        for proceso in pendientes:
            maquina = _elegir_maquina_proceso(proceso, row, cfg)
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
                "CantidadPliegos": row.get("CantidadPliegos", row.get("CANT/DDP", 0)),
                "MateriaPrimaPlanta": row.get("MateriaPrimaPlanta", row.get("MPPlanta")),
            })
    tasks = pd.DataFrame(tareas)
    if not tasks.empty:
        tasks["DueDate"] = pd.to_datetime(tasks["DueDate"], dayfirst=True, errors="coerce")
    return tasks


# =======================================================
# Programador principal
# =======================================================

def programar(df_ordenes: pd.DataFrame, cfg, start=None):
    """
    Devuelve:
      schedule: detalle por proceso con Inicio/Fin y Atraso_h
      carga_md: carga por máquina y día (HorasPlanificadas, CapacidadDia, HorasExtra)
      resumen_ot: Fin_OT y atraso por OT

    Reglas:
      - Solo programa procesos pendientes (_PEN_*).
      - Colas por máquina, ordenadas por DueDate → GroupKey → Cantidad desc.
      - Respeta dependencias de flujo estándar.
      - MPPlanta: solo programa si es False (o vacío).
      - Jornada y feriados desde cfg.
    """
    if df_ordenes.empty:
        vac = pd.DataFrame(columns=[
            "OT_id","CodigoProducto","Subcodigo","Cliente","Proceso","Maquina",
            "Setup_min","Proceso_h","Inicio","Fin","Motivo","Atraso_h"
        ])
        return vac, pd.DataFrame(), pd.DataFrame()

    # ID único y fecha
    df_ordenes["OT_id"] = df_ordenes["CodigoProducto"].astype(str) + "-" + df_ordenes["Subcodigo"].astype(str)
    fecha_col = "FechaEntregaAjustada" if "FechaEntregaAjustada" in df_ordenes.columns else "FechaEntrega"

    # Agenda por máquina
    agenda = construir_calendario(cfg, start=start)
    maquinas = cfg["maquinas"]["Maquina"].unique()
    ultimo_en_maquina = {m: None for m in maquinas}

    # Expandir tareas
    tasks = _expandir_tareas(df_ordenes, cfg, fecha_col)
    if tasks.empty:
        vac = pd.DataFrame(columns=[
            "OT_id","CodigoProducto","Subcodigo","Cliente","Proceso","Maquina",
            "Setup_min","Proceso_h","Inicio","Fin","Motivo","Atraso_h"
        ])
        return vac, pd.DataFrame(), pd.DataFrame()

    # Precedencias (flujo estándar)
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

    # Colas por máquina
    colas = {}
    for m in maquinas:
        q = tasks[tasks["Maquina"] == m].copy()
        if q.empty:
            colas[m] = deque()
            continue
        q.sort_values(by=["DueDate", "GroupKey", "CantidadPliegos"], ascending=[True, True, False], inplace=True)
        colas[m] = deque(q.to_dict("records"))

    # Estados
    pendientes_por_ot = defaultdict(set)
    for _, t in tasks.iterrows():
        pendientes_por_ot[t["OT_id"]].add(t["Proceso"])
    completado = defaultdict(set)

    # Carga por máquina/día
    carga_reg = []

    filas = []

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
    h_dia = horas_por_dia(cfg)

    while quedan_tareas() and progreso:
        progreso = False
        for maquina in maquinas:
            if not colas.get(maquina):
                continue

            # Buscar primera tarea ejecutable y con MP disponible (MPPlanta == False)
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

            # Traer la candidata al frente y popleft
            for _ in range(idx_cand):
                colas[maquina].rotate(-1)
            t = colas[maquina].popleft()

            orden = df_ordenes.loc[t["idx"]]
            # Tiempos
            setup_h, proc_h = tiempo_operacion_h(orden, t["Proceso"], maquina, cfg)

            # Setup menor si corresponde (troquel/cliente/colores/tamaño iguales al anterior en esa máquina)
            if usa_setup_menor(ultimo_en_maquina.get(maquina), orden, t["Proceso"]):
                setup_min = setup_menor_min(t["Proceso"], maquina, cfg)
                motivo = "Setup menor (cluster)"
            else:
                setup_min = setup_base_min(t["Proceso"], maquina, cfg)
                motivo = "Setup base"

            total_h = proc_h + setup_min/60.0

            # Reservar en agenda
            bloques = _reservar_en_agenda(agenda[maquina], total_h, cfg)
            inicio = bloques[0][0]
            fin = bloques[-1][1]

            # Registrar carga por día
            for b_ini, b_fin in bloques:
                d = b_ini.date()
                horas = (b_fin - b_ini).total_seconds()/3600.0
                carga_reg.append({"Fecha": d, "Maquina": maquina, "HorasPlanificadas": horas, "CapacidadDia": h_dia})

            # Atraso por tarea vs DueDate
            atraso_h = 0.0
            if pd.notna(t["DueDate"]):
                due_dt = pd.to_datetime(t["DueDate"])
                if fin > due_dt:
                    atraso_h = (fin - due_dt).total_seconds()/3600.0

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

    # Resumen por OT
    if not schedule.empty:
        fin_ot = schedule.groupby("OT_id")["Fin"].max().reset_index().rename(columns={"Fin": "Fin_OT"})
        due = schedule.groupby("OT_id")["DueDate"].max().reset_index()
        resumen_ot = fin_ot.merge(due, on="OT_id", how="left")
        resumen_ot["Atraso_h"] = (
            (resumen_ot["Fin_OT"] - resumen_ot["DueDate"]).dt.total_seconds()/3600.0
        ).clip(lower=0).fillna(0.0).round(2)
        resumen_ot["EnRiesgo"] = resumen_ot["Atraso_h"] > 0
    else:
        resumen_ot = pd.DataFrame(columns=["OT_id", "Fin_OT", "DueDate", "Atraso_h", "EnRiesgo"])

    # Carga por máquina/día
    carga_md = pd.DataFrame(carga_reg)
    if not carga_md.empty:
        carga_md = carga_md.groupby(["Fecha", "Maquina", "CapacidadDia"], as_index=False)["HorasPlanificadas"].sum()
        carga_md["HorasExtra"] = (carga_md["HorasPlanificadas"] - carga_md["CapacidadDia"]).clip(lower=0).round(2)

    return schedule, carga_md, resumen_ot
