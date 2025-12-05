
import sys
import os
import pandas as pd
from datetime import datetime, time, date, timedelta

# Arreglar imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.schedulers.agenda import _reservar_en_agenda
from modules.config_loader import get_horas_totales_dia, es_dia_habil


def log(msg):
    with open("tests/debug_result.txt", "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def test_overtime_logic():
    # Clear file
    with open("tests/debug_result.txt", "w", encoding="utf-8") as f:
        f.write("=== TEST: Overtime on Saturday ===\n")
    
    # 1. Configuración Mock
    viernes = date(2025, 12, 5)
    sabado = date(2025, 12, 6)
    domingo = date(2025, 12, 7)
    lunes = date(2025, 12, 8)
    
    cfg = {
        "jornada": pd.DataFrame({"Parametro": ["Horas_base_por_dia"], "Valor": [8.5]}),
        "feriados": set(),
        "horas_extras": {
            sabado: 4.0 
        },
        "downtimes": []
    }
    
    log(f"Es hábil Viernes? {es_dia_habil(viernes, cfg)}")
    log(f"Es hábil Sábado (con extras)? {es_dia_habil(sabado, cfg)}")
    log(f"Es hábil Domingo? {es_dia_habil(domingo, cfg)}")
    
    agenda_m = {
        "fecha": viernes,
        "hora": time(14, 0),
        "resto_horas": 2.0,
        "nombre": "Maquina Test"
    }
    
    log("\nReservando 10 horas...")
    bloques = _reservar_en_agenda(agenda_m, 10.0, cfg)
    
    for i, (inicio, fin) in enumerate(bloques):
        dur = (fin - inicio).total_seconds() / 3600
        log(f"Bloque {i}: {inicio} -> {fin} ({dur:.2f}h)")
        
    try:
        # Validaciones
        # Bloque 1: Viernes
        assert bloques[0][0].date() == viernes
        assert bloques[0][1].time() == time(16, 0)
        
        # Bloque 2: Sábado
        assert bloques[1][0].date() == sabado
        # Expected: 7:00 -> 11:00 (4h)
        # Actual check
        dur_sab = (bloques[1][1] - bloques[1][0]).total_seconds() / 3600
        log(f"Duracion Sabado: {dur_sab}")
        assert abs(dur_sab - 4.0) < 0.1
        
        # Bloque 3: Lunes
        assert bloques[2][0].date() == lunes
        dur_lun = (bloques[2][1] - bloques[2][0]).total_seconds() / 3600
        log(f"Duracion Lunes: {dur_lun}")
        assert abs(dur_lun - 4.0) < 0.1
        
        log("\n¡Test Pasado Exitosamente!")
    except AssertionError as e:
        log(f"FALLO ASSERTION: {e}")
        raise

if __name__ == "__main__":
    test_overtime_logic()
