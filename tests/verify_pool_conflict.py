import pandas as pd
from datetime import datetime, time, date, timedelta
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.scheduler import programar

def test_pool_conflict():
    print("=== Testing POOL Priority Conflict (Urgency vs Successor) ===")
    
    # 1. Mock Configuration
    cfg = {
        "maquinas": pd.DataFrame({
            "Maquina": ["ZZ_Descartonadora", "Descartonadora 2", "Pegadora 1"],
            "Proceso": ["Descartonado", "Descartonado", "Pegado"],
            "Capacidad_pliegos_hora": [1000, 1000, 1000],
            "Setup_base_min": [30, 30, 30],
            "Setup_menor_min": [10, 10, 10]
        }),
        "downtimes": [],
        "feriados": set(),
        "orden_std": ["Descartonado", "Pegado"],
        "horas_laborales": 9,
        "jornada": pd.DataFrame({
            "Parametro": ["Horas_base_por_dia", "Horas_extra_por_dia"],
            "Valor": [9.0, 0.0]
        })
    }
    
    today = date.today()
    start_time = time(7, 0)
    
    # 2. Create Test Data
    
    # Scenario 1: Urgent (No Succ) vs Non-Urgent (Succ)
    # Task A: Urgent, No Successor. Ready.
    # Task B: Not Urgent, Has Successor. Ready.
    # Expected: Task A (Urgency wins).
    
    # Scenario 2: Non-Urgent (No Succ) vs Non-Urgent (Succ)
    # Task C: Not Urgent, No Successor. Due T+1. Ready.
    # Task D: Not Urgent, Has Successor. Due T+10. Ready.
    # Expected: Task D (Successor wins among non-urgent).
    
    df_ordenes = pd.DataFrame([
        # Scenario 1
        {
            "CodigoProducto": "A_Urg", "Subcodigo": "1", "CantidadProductos": 1000, 
            "Proceso": "Descartonado", "Urgente": "Si", "FechaEntrega": today,
            "MateriaPrima": "Papel", "Cliente": "C1", "Poses": 1, "BocasTroquel": 1,
            "_PEN_Descartonado": "Si"
        },
        {
            "CodigoProducto": "B_Succ", "Subcodigo": "1", "CantidadProductos": 1000, 
            "Proceso": "Descartonado", "Urgente": "No", "FechaEntrega": today + timedelta(days=10),
            "MateriaPrima": "Papel", "Cliente": "C2", "Poses": 1, "BocasTroquel": 1,
            "_PEN_Descartonado": "Si", "_PEN_Pegado": "Si"
        },
    ])
    
    # Run Scheduler for Scenario 1
    print("\n--- Scenario 1: Urgent (No Succ) vs Non-Urgent (Succ) ---")
    schedule1, _, _, _ = programar(df_ordenes, cfg, start=today, start_time=start_time)
    
    if not schedule1.empty:
        t1 = schedule1[schedule1["Maquina"] == "ZZ_Descartonadora"].iloc[0]
        print(f"First task: {t1['OT_id']}")
        if t1['OT_id'] == "A_Urg-1":
            print("SUCCESS: Urgent task picked first.")
        else:
            print("FAILURE: Non-Urgent task picked first.")
    
    # Scenario 2
    df_ordenes_2 = pd.DataFrame([
        {
            "CodigoProducto": "C_NoSucc", "Subcodigo": "1", "CantidadProductos": 1000, 
            "Proceso": "Descartonado", "Urgente": "No", "FechaEntrega": today + timedelta(days=1),
            "MateriaPrima": "Papel", "Cliente": "C3", "Poses": 1, "BocasTroquel": 1,
            "_PEN_Descartonado": "Si"
        },
        {
            "CodigoProducto": "D_Succ", "Subcodigo": "1", "CantidadProductos": 1000, 
            "Proceso": "Descartonado", "Urgente": "No", "FechaEntrega": today + timedelta(days=10),
            "MateriaPrima": "Papel", "Cliente": "C4", "Poses": 1, "BocasTroquel": 1,
            "_PEN_Descartonado": "Si", "_PEN_Pegado": "Si"
        },
    ])
    
    # Note: C_NoSucc comes first in list and has earlier DueDate.
    # But D_Succ has successor.
    # We expect D_Succ to be picked if we prioritize successor in non-urgent.
    
    print("\n--- Scenario 2: Non-Urgent (No Succ) vs Non-Urgent (Succ) ---")
    schedule2, _, _, _ = programar(df_ordenes_2, cfg, start=today, start_time=start_time)
    
    if not schedule2.empty:
        t2 = schedule2[schedule2["Maquina"] == "ZZ_Descartonadora"].iloc[0]
        print(f"First task: {t2['OT_id']}")
        if t2['OT_id'] == "D_Succ-1":
            print("SUCCESS: Successor task picked first (among non-urgent).")
        else:
            print("FAILURE: Successor task NOT picked first.")

if __name__ == "__main__":
    try:
        test_pool_conflict()
    except Exception as e:
        import traceback
        traceback.print_exc()
