from datetime import datetime, timedelta, time
from modules.config_loader import horas_por_dia, proximo_dia_habil

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

    while h > 1e-9:
        # PAUSA FIJA DE ALMUERZO (13:30 → 14:00) para el día actual
        almuerzo_inicio = datetime.combine(fecha, time(13, 30))
        almuerzo_fin = datetime.combine(fecha, time(14, 0))
        
        # Combinar paros configurados con el almuerzo del día
        paros_activos = paros_maquina + [(almuerzo_inicio, almuerzo_fin)]
        paros_activos.sort(key=lambda x: x[0])

        # Si no queda resto de día → avanzar al siguiente día hábil
        if resto <= 1e-9:
            fecha = proximo_dia_habil(fecha + timedelta(days=1), cfg)
            hora_actual = datetime.combine(fecha, time(7, 0))
            resto = h_dia
            continue

        # Si estamos dentro de un paro → avanzar al final del paro
        dentro_paro = False
        for inicio, fin in paros_activos:
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
        for inicio, fin in paros_activos:
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
