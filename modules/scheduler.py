import pandas as pd
from datetime import datetime, timedelta, time, date
from modules.config_loader import es_si, horas_por_dia, proximo_dia_habil, construir_calendario
from modules.tiempos_y_setup import (
    capacidad_pliegos_h, setup_base_min, setup_menor_min,
    usa_setup_menor, tiempo_operacion_h
)

def elegir_maquina(proceso, orden, cfg):
    candidatos = cfg["maquinas"].query("Proceso==@proceso")["Maquina"].tolist()
    if not candidatos: return None
    if proceso == "Troquelado" and float(orden.get("CantidadPliegos",0)) > 3000:
        if "Automática" in candidatos:
            return "Automática"
    if proceso == "Impresión":
        if es_si(orden.get("ImpresionFlexo")) and "Flexo" in candidatos:
            return "Flexo"
        if es_si(orden.get("ImpresionOffset")) and "Offset" in candidatos:
            return "Offset"
    if proceso == "Ventana" and "Ventanas" in candidatos:
        return "Ventanas"
    return candidatos[0]

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
            hora_actual = datetime.combine(fecha, time(8,0))
            resto = h_dia
        usar = min(h, resto)
        inicio = hora_actual
        fin = inicio + timedelta(hours=usar)
        bloques.append((inicio, fin))
        hora_actual = fin
        resto -= usar
        h -= usar

    agenda_m["fecha"] = hora_actual.date()
    agenda_m["hora"]  = hora_actual.time()
    agenda_m["resto_horas"] = resto
    return bloques

def secuencia_para_orden(orden, cfg):
    sec_personal = str(orden.get("SecuenciaPersonalizada","")).strip()
    if sec_personal:
        pasos = [p.strip() for p in sec_personal.split(">") if p.strip()]
        return pasos
    pasos = []
    flags = {
        "Guillotina": True,
        "Impresión": es_si(orden.get("ImpresionOffset")) or es_si(orden.get("ImpresionFlexo")),
        "Enchapado": es_si(orden.get("Encapado")),
        "OPP":       es_si(orden.get("OPP")),
        "Troquelado": True,
        "Descartonado": es_si(orden.get("Descartonado")) or True,
        "Ventana":   es_si(orden.get("Ventana")),
        "Pegado":    es_si(orden.get("Pegado")),
    }
    for p in cfg["orden_std"]:
        if flags.get(p, False):
            pasos.append(p)
    return pasos

def programar(df_ordenes, cfg, start=None):
    """Devuelve un schedule con dependencias entre procesos (flujo por OT)."""
    agenda = construir_calendario(cfg, start=start)
    maquinas = cfg["maquinas"]["Maquina"].unique()   # array de nombres de máquina
    ultimo_en_maquina = {maquina: None for maquina in maquinas}
    filas = []

    # Generar ID único de OT = ORDEN + PED
    df_ordenes["OT_id"] = df_ordenes["CodigoProducto"].astype(str) + "-" + df_ordenes["Subcodigo"].astype(str)

    # Determinar la columna de fecha que se usará
    fecha_col = (
    "FechaEntregaAjustada"
    if "FechaEntregaAjustada" in df_ordenes.columns
    else "FechaEntrega"
    )

    # --- Determinar columna de troquel disponible ---
    if "CodigoTroquelTapa" in df_ordenes.columns and df_ordenes["CodigoTroquelTapa"].notna().any():
        troquel_col = "CodigoTroquelTapa"
    elif "CodigoTroquelCuerpo" in df_ordenes.columns and df_ordenes["CodigoTroquelCuerpo"].notna().any():
        troquel_col = "CodigoTroquelCuerpo"
    else:
        troquel_col = None

    # --- Ordenar priorizando por fecha, troquel y tamaño ---
    if troquel_col:
        base = df_ordenes.sort_values(
            [fecha_col, troquel_col, "CantidadPliegos"],
            ascending=[True, True, False]
        )
    else:
        base = df_ordenes.sort_values(
            [fecha_col, "CantidadPliegos"],
            ascending=[True, False]
        )

    # Recorrer cada OT (ORDEN + PED)
    for ot_id, grupo in base.groupby("OT_id"):
        orden = grupo.iloc[0]
        pasos = secuencia_para_orden(orden, cfg)

        # Tiempo de finalización del proceso anterior (para dependencias)
        fin_anterior = None  

        for proceso in pasos:
            maquina = elegir_maquina(proceso, orden, cfg)
            if not maquina:
                continue

            # Calcular tiempos de proceso
            setup_h, proc_h = tiempo_operacion_h(orden, proceso, maquina, cfg)
            prev = ultimo_en_maquina.get(maquina)

            # Setup base o reducido
            if usa_setup_menor(prev, orden, proceso):
                setup_min = setup_menor_min(proceso, maquina, cfg)
                motivo_setup = "Setup menor (mismo troquel/cliente/colores/tamaño)"
            else:
                setup_min = setup_base_min(proceso, maquina, cfg)
                motivo_setup = "Setup base"

            total_h = (setup_min / 60.0) + proc_h

            # --- Dependencia: si hay proceso anterior, empieza después de su fin ---
            if fin_anterior is not None:
                # Si el proceso anterior termina más tarde que la disponibilidad de la máquina, esperar
                if fin_anterior > datetime.combine(agenda[maquina]["fecha"], agenda[maquina]["hora"]):
                    agenda[maquina]["fecha"] = fin_anterior.date()
                    agenda[maquina]["hora"] = fin_anterior.time()
                    agenda[maquina]["resto_horas"] = horas_por_dia(cfg) - 0.01  # ajustar levemente

            # Reservar tiempo en la máquina (puede partir entre días)
            bloques = avanzar_reloj(agenda[maquina], total_h, cfg)
            inicio = bloques[0][0]
            fin = bloques[-1][1]

            # Registrar el proceso
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

            # Actualizar referencias
            ultimo_en_maquina[maquina] = orden.to_dict()
            fin_anterior = fin  # <-- el siguiente proceso empieza después de este

    sch = pd.DataFrame(filas)
    sch = sch.sort_values(["OT_id", "Inicio"]).reset_index(drop=True)
    return sch
