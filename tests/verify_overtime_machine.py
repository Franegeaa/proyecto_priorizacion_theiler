
import sys
import os
import pandas as pd
from datetime import datetime, time, date, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.schedulers.agenda import _reservar_en_agenda
from modules.config_loader import get_horas_totales_dia, es_dia_habil

def log(msg):
    with open("tests/debug_result_machine.txt", "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def test_machine_specific_overtime():
    # Clear log
    with open("tests/debug_result_machine.txt", "w", encoding="utf-8") as f:
        f.write("=== TEST: Machine Specific Overtime ===\n")

    viernes = date(2025, 12, 5)
    sabado = date(2025, 12, 6)
    domingo = date(2025, 12, 7)
    lunes = date(2025, 12, 8)

    # Configuración: Maquina A tiene horas extras el Sabado. Maquina B no.
    cfg = {
        "jornada": pd.DataFrame({"Parametro": ["Horas_base_por_dia"], "Valor": [8.5]}),
        "feriados": set(),
        "horas_extras": {
            "Maquina A": { sabado: 4.0 },
            "Maquina B": {}
        },
        "downtimes": []
    }

    # Test 1: Maquina A
    log("\n--- Testing Maquina A (Con Extras) ---")
    log(f"Es habil Sabado para Maquina A? {es_dia_habil(sabado, cfg, maquina='Maquina A')}")
    assert es_dia_habil(sabado, cfg, maquina='Maquina A') == True
    
    agenda_a = {
        "fecha": viernes,
        "hora": time(14, 0),
        "resto_horas": 2.0,
        "nombre": "Maquina A"
    }
    
    # 10 Horas necesarias
    # Viernes: 2h (Resto)
    # Sabado: 4h (Extras)
    # Lunes: 4h
    bloques_a = _reservar_en_agenda(agenda_a, 10.0, cfg)
    for i, (inicio, fin) in enumerate(bloques_a):
        dur = (fin - inicio).total_seconds() / 3600
        log(f"Bloque {i}: {inicio} -> {fin} ({dur:.2f}h)")

    # Assert Maquina A usó el sabado
    assert bloques_a[1][0].date() == sabado
    
    # Test 2: Maquina B
    log("\n--- Testing Maquina B (SIN Extras) ---")
    log(f"Es habil Sabado para Maquina B? {es_dia_habil(sabado, cfg, maquina='Maquina B')}")
    assert es_dia_habil(sabado, cfg, maquina='Maquina B') == False
    
    agenda_b = {
        "fecha": viernes,
        "hora": time(14, 0),
        "resto_horas": 2.0,
        "nombre": "Maquina B"
    }
    
    # 10 Horas necesarias
    # Viernes: 2h
    # Sabado: SALTADO
    # Domingo: SALTADO
    # Lunes: 8h (consume todo el dia casi) -> 8.5h disponibles
    bloques_b = _reservar_en_agenda(agenda_b, 10.0, cfg)
    for i, (inicio, fin) in enumerate(bloques_b):
        dur = (fin - inicio).total_seconds() / 3600
        log(f"Bloque {i}: {inicio} -> {fin} ({dur:.2f}h)")

    # Assert Maquina B NO usó el sabado (Bloque 1 debe ser Lunes)
    assert bloques_b[1][0].date() == lunes

    log("\n¡Test Pasado Exitosamente!")

if __name__ == "__main__":
    try:
        test_machine_specific_overtime()
    except AssertionError as e:
        log(f"FALLO ASSERTION: {e}")
        raise
