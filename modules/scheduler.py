import pandas as pd
from datetime import datetime, timedelta, time
from modules.config_loader import es_si, horas_por_dia, proximo_dia_habil, construir_calendario
from modules.tiempos_y_setup import (
    capacidad_pliegos_h, setup_base_min, setup_menor_min,
    usa_setup_menor, tiempo_operacion_h
)

# ----------------------------------------------------------------------
# ⚙️ Elegir máquina según proceso y tipo de orden
# ----------------------------------------------------------------------
def elegir_maquina(proceso, orden, cfg):
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


# ----------------------------------------------------------------------
# ⏰ Avanzar el reloj (maneja días hábiles y jornadas)
# ----------------------------------------------------------------------
def avanzar_reloj(agenda_m, horas_necesarias, cfg):
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


# ----------------------------------------------------------------------
# 🔁 Secuencia de procesos según columnas pendientes
# ----------------------------------------------------------------------
def secuencia_para_orden(orden, cfg):
    pasos = []

    # Usar las columnas _PEN_* para definir qué procesos deben ejecutarse
    if es_si(orden.get("_PEN_Guillotina")):
        pasos.append("Guillotina")

    # Impresión diferenciada
    if es_si(orden.get("_PEN_ImpresionFlexo")):
        pasos.append("Impresión Flexo")
    elif es_si(orden.get("_PEN_ImpresionOffset")):
        pasos.append("Impresión Offset")

    if es_si(orden.get("_PEN_Barnizado")):
        pasos.append("Barnizado")
    if es_si(orden.get("_PEN_Encapado")):
        pasos.append("Encapado")
    if es_si(orden.get("_PEN_OPP")):
        pasos.append("OPP")
    if es_si(orden.get("_PEN_Troquelado")):
        pasos.append("Troquelado")
    if es_si(orden.get("_PEN_Descartonado")):
        pasos.append("Descartonado")
    if es_si(orden.get("_PEN_Ventana")):
        pasos.append("Ventana")
    if es_si(orden.get("_PEN_Pegado")):
        pasos.append("Pegado")

    return pasos


# ----------------------------------------------------------------------
# 🧮 Planificador principal
# ----------------------------------------------------------------------
def programar(df_ordenes, cfg, start=None):
    """Devuelve un schedule con dependencias entre procesos (flujo por OT)."""
    agenda = construir_calendario(cfg, start=start)
    maquinas = cfg["maquinas"]["Maquina"].unique()
    ultimo_en_maquina = {maquina: None for maquina in maquinas}
    filas = []

    # ID único de orden = ORDEN + PED
    df_ordenes["OT_id"] = df_ordenes["CodigoProducto"].astype(str) + "-" + df_ordenes["Subcodigo"].astype(str)

    # Fecha base (Entrega o Ajustada)
    fecha_col = "FechaEntregaAjustada" if "FechaEntregaAjustada" in df_ordenes.columns else "FechaEntrega"

    # Determinar columna de troquel (si existe)
    if "CodigoTroquel" in df_ordenes.columns:
        troquel_col = "CodigoTroquel"
    elif "CodigoTroquelTapa" in df_ordenes.columns:
        troquel_col = "CodigoTroquelTapa"
    elif "CodigoTroquelCuerpo" in df_ordenes.columns:
        troquel_col = "CodigoTroquelCuerpo"
    else:
        troquel_col = None

    # Ordenar: primero por fecha, luego por troquel (si hay), luego por cantidad
    if troquel_col:
        base = df_ordenes.sort_values([fecha_col, troquel_col, "CantidadPliegos"], ascending=[True, True, False])
    else:
        base = df_ordenes.sort_values([fecha_col, "CantidadPliegos"], ascending=[True, False])

    # Recorrer cada orden (OT_id)
    for ot_id, grupo in base.groupby("OT_id"):
        orden = grupo.iloc[0]
        pasos = secuencia_para_orden(orden, cfg)

        fin_anterior = None

        for proceso in pasos:
            maquina = elegir_maquina(proceso, orden, cfg)
            if not maquina:
                continue

            # Calcular tiempo de setup y proceso
            setup_h, proc_h = tiempo_operacion_h(orden, proceso, maquina, cfg)
            prev = ultimo_en_maquina.get(maquina)

            # Evaluar tipo de setup
            if usa_setup_menor(prev, orden, proceso):
                setup_min = setup_menor_min(proceso, maquina, cfg)
                motivo_setup = "Setup menor (mismo troquel/cliente/colores/tamaño)"
            else:
                setup_min = setup_base_min(proceso, maquina, cfg)
                motivo_setup = "Setup base"

            total_h = (setup_min / 60.0) + proc_h

            # Dependencias entre procesos (en secuencia)
            if fin_anterior is not None:
                if fin_anterior > datetime.combine(agenda[maquina]["fecha"], agenda[maquina]["hora"]):
                    agenda[maquina]["fecha"] = fin_anterior.date()
                    agenda[maquina]["hora"] = fin_anterior.time()
                    agenda[maquina]["resto_horas"] = horas_por_dia(cfg) - 0.01

            # Reservar tiempo (puede ocupar varios días)
            bloques = avanzar_reloj(agenda[maquina], total_h, cfg)
            inicio = bloques[0][0]
            fin = bloques[-1][1]

            filas.append({
                "OT_id": ot_id,
                "CodigoProducto": orden.get("CodigoProducto"),
                "Subcodigo": orden.get("Subcodigo"),
                "Cliente": orden.get("Cliente"),
                "Proceso": proceso,
                "Maquina": maquina,
                "Setup_min": round(setup_min, 2),
                "Proceso_h": round(proc_h, 3),
                "Inicio": inicio,
                "Fin": fin,
                "Motivo": motivo_setup
            })

            ultimo_en_maquina[maquina] = orden.to_dict()
            fin_anterior = fin

    sch = pd.DataFrame(filas)
    sch = sch.sort_values(["OT_id", "Inicio"]).reset_index(drop=True)
    return sch
