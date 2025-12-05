from datetime import datetime, timedelta, time
from modules import config_loader as hours_module
from modules.config_loader import proximo_dia_habil

def _reservar_en_agenda(agenda_m, horas_necesarias, cfg):
    """
    Reserva 'horas_necesarias' en la agenda de una máquina,
    respetando paros programados (downtimes) y feriados.
    Si un bloque se superpone con un paro, lo corta antes del paro.
    """
    fecha = agenda_m["fecha"]
    hora_actual = datetime.combine(fecha, agenda_m["hora"])
    resto = agenda_m["resto_horas"]
    
    # h_dia ahora es dinamico dentro del loop
    # h_dia = horas_por_dia(cfg) 

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
        # 1. Calcular duración del día dinámicamente POR MÁQUINA
        h_dia_hoy = hours_module.get_horas_totales_dia(fecha, cfg, maquina=nombre_maquina)
        
        # Si hoy no hay horas (ej. feriado sin extras), saltar al próximo
        if h_dia_hoy <= 0:
            fecha = proximo_dia_habil(fecha + timedelta(days=1), cfg, maquina=nombre_maquina)
            hora_actual = datetime.combine(fecha, time(7, 0))
            # Recalcular resto para el nuevo día
            resto = hours_module.get_horas_totales_dia(fecha, cfg, maquina=nombre_maquina)
            continue

        # Si llegamos a un nuevo día, el resto debe ser el total de ese día
        if hora_actual.time() == time(7, 0):
             resto = h_dia_hoy

        # PAUSA FIJA DE ALMUERZO (13:30 → 14:00) para el día actual
        almuerzo_inicio = datetime.combine(fecha, time(13, 30))
        almuerzo_fin = datetime.combine(fecha, time(14, 0))
        
        # Combinar paros configurados con el almuerzo del día
        paros_activos = paros_maquina + [(almuerzo_inicio, almuerzo_fin)]
        paros_activos.sort(key=lambda x: x[0])

        # Si no queda resto de día → avanzar al siguiente día hábil
        if resto <= 1e-9:
            fecha = proximo_dia_habil(fecha + timedelta(days=1), cfg, maquina=nombre_maquina)
            hora_actual = datetime.combine(fecha, time(7, 0))
            # resto se actualizará en la siguiente iteración
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

        # CALCULO DE FIN DE TURNO DINÁMICO
        inicio_jornada = datetime.combine(fecha, time(7, 0))
        duracion_bruta_h = h_dia_hoy + 0.5 # Sumamos la media hora de almuerzo
        fin_turno = inicio_jornada + timedelta(hours=duracion_bruta_h)
        
        limite_fin_dia = min(
            fin_turno,
            hora_actual + timedelta(hours=h, minutes=1) # +1 min buffer
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

        # Validar bloqueo por redondeo (loop infinito protection)
        if fin_bloque <= hora_actual:
             if proximo_paro and proximo_paro > hora_actual:
                  hora_actual = proximo_paro
             else:
                  fecha = proximo_dia_habil(fecha + timedelta(days=1), cfg, maquina=nombre_maquina)
                  hora_actual = datetime.combine(fecha, time(7, 0))
             continue

        # Duración efectiva del bloque
        duracion_h = (fin_bloque - hora_actual).total_seconds() / 3600.0

        if duracion_h <= 1e-5: 
             if hora_actual >= fin_turno:
                fecha = proximo_dia_habil(fecha + timedelta(days=1), cfg, maquina=nombre_maquina)
                hora_actual = datetime.combine(fecha, time(7, 0))
                continue
             else:
                 hora_actual += timedelta(minutes=1)
                 continue

        # Registrar bloque válido
        bloques.append((hora_actual, fin_bloque))

        # Actualizar contadores
        hora_actual = fin_bloque
        resto -= duracion_h
        h -= duracion_h
        
        if resto < 0: resto = 0

        # Si terminamos justo en el inicio de un paro → saltarlo
        for inicio, fin in paros_maquina:
            if abs((hora_actual - inicio).total_seconds()) < 1e-6:
                hora_actual = fin
                break

        # Fin del turno → siguiente día hábil
        if hora_actual >= fin_turno:
            fecha = proximo_dia_habil(
                hora_actual.date() + timedelta(days=1), cfg, maquina=nombre_maquina
            )
            hora_actual = datetime.combine(fecha, time(7, 0))

    # Guardar estado final de agenda
    agenda_m["fecha"] = hora_actual.date()
    agenda_m["hora"] = hora_actual.time()
    agenda_m["resto_horas"] = resto
    agenda_m["nombre"] = nombre_maquina

    return bloques
