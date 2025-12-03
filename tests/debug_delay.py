import pandas as pd
from datetime import datetime, time, date, timedelta
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.scheduler import programar

def test_urgent_delay():
    print("=== Testing Urgent Delay for OT E7362-2061404 ===")
    
    # 1. Mock Configuration
    cfg = {
        "maquinas": pd.DataFrame({
            "Maquina": ["Automatica", "Manual 1", "Flexo"],
            "Proceso": ["Troquelado", "Troquelado", "Impresión Flexo"],
            "Capacidad_pliegos_hora": [1000, 500, 2000],
            "Setup_base_min": [30, 30, 60],
            "Setup_menor_min": [10, 10, 20]
        }),
        "downtimes": [],
        "feriados": set(),
        "orden_std": ["Impresión Flexo", "Troquelado"],
        "horas_laborales": 9,
        "jornada": pd.DataFrame({
            "Parametro": ["Horas_base_por_dia", "Horas_extra_por_dia"],
            "Valor": [9.0, 0.0]
        })
    }
    
    today = date(2025, 12, 3) # Match user's start date
    start_time = time(7, 0)
    
    # 2. Create Test Data
    # Target OT: E7362-2061404
    # Urgent: Yes
    # Process: Flexo -> Troquelado
    # Flexo starts 12-03.
    
    # We create a scenario where there are MANY other Urgent tasks for Automatica
    # to see if they block it.
    
    orders = []
    
    # TARGET OT
    # Force to Automatica by size (100x100 > Manual Max)
    orders.append({
        "CodigoProducto": "E7362", "Subcodigo": "2061404", "CantidadProductos": 400, 
        "Proceso": "Impresión Flexo", "Urgente": "Si", "FechaEntrega": date(2025, 12, 20),
        "MateriaPrima": "Carton", "Cliente": "LA CELESTE", "Poses": 1, "BocasTroquel": 1,
        "_PEN_ImpresionFlexo": "Si", "_PEN_Troquelado": "Si", "CodigoTroquel": "T_TARGET",
        "PliAnc": 100, "PliLar": 100, "CantidadPliegos": 400, "Colores": "C-M-Y-K"
    })
    orders.append({
        "CodigoProducto": "E7362", "Subcodigo": "2061404", "CantidadProductos": 400, 
        "Proceso": "Troquelado", "Urgente": "Si", "FechaEntrega": date(2025, 12, 20),
        "MateriaPrima": "Carton", "Cliente": "LA CELESTE", "Poses": 1, "BocasTroquel": 1,
        "_PEN_ImpresionFlexo": "Si", "_PEN_Troquelado": "Si", "CodigoTroquel": "T_TARGET",
        "PliAnc": 100, "PliLar": 100, "CantidadPliegos": 400, "Colores": "C-M-Y-K"
    })

    # BLOCKERS (Non-Urgent tasks for Automatica)
    # They fit in Auto (40x40 is > 38x38) and we force them to Auto by quantity > 3000
    
    for i in range(5):
        orders.append({
            "CodigoProducto": f"BLOCKER_{i}", "Subcodigo": "1", "CantidadProductos": 5000, 
            "Proceso": "Troquelado", "Urgente": "No", "FechaEntrega": date(2025, 12, 10), # EARLIER but Non-Urgent
            "MateriaPrima": "Carton", "Cliente": "OTHER", "Poses": 1, "BocasTroquel": 1,
            "_PEN_Troquelado": "Si", "CodigoTroquel": f"T_BLOCKER_{i}",
            "PliAnc": 40, "PliLar": 40, "CantidadPliegos": 5000
        })

    df_ordenes = pd.DataFrame(orders)
    
    # Run Scheduler
    # Capture stdout to file
    with open('tests/debug_result.txt', 'w', encoding='utf-8') as f:
        sys.stdout = f
        
        print("Running programar...")
        schedule, _, _, _ = programar(df_ordenes, cfg, start=today, start_time=start_time)
        
        print("\n--- Schedule Result ---")
        if schedule.empty:
            print("Error: Schedule is empty!")
        else:
            print(schedule[["OT_id", "Maquina", "Proceso", "Inicio", "Fin", "Motivo"]].to_string())
            
            auto_sched = schedule[schedule["Maquina"].str.contains("Automatica", case=False)].sort_values("Inicio")
            target_row = auto_sched[auto_sched["OT_id"] == "E7362-2061404"]
            
            if not target_row.empty:
                print(f"\nTarget OT scheduled at: {target_row.iloc[0]['Inicio']}")
            else:
                print("\nTarget OT NOT scheduled on Automatica.")
                
        sys.stdout = sys.__stdout__ # Restore stdout

if __name__ == "__main__":
    test_urgent_delay()
