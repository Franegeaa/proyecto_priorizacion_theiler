
import sys
import os
import pandas as pd
from datetime import datetime, time, timedelta, date
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock external dependencies to avoid complex config setup
import modules.tiempos_y_setup
modules.tiempos_y_setup.tiempo_operacion_h = MagicMock(return_value=(0, 1.0)) # 1 hour per task
modules.tiempos_y_setup.usa_setup_menor = MagicMock(return_value=False)
modules.tiempos_y_setup.capacidad_pliegos_h = MagicMock(return_value=1000)
modules.tiempos_y_setup.setup_base_min = MagicMock(return_value=15)
modules.tiempos_y_setup.setup_menor_min = MagicMock(return_value=5)

from modules.scheduler import programar

def run_test():
    # 1. Setup Config
    cfg = {
        "jornada": pd.DataFrame({"Parametro": ["Horas_base_por_dia"], "Valor": [24]}), # 24h for simplicity
        "feriados": set(),
        "orden_std": ["Impresión Flexo", "Troquelado", "Descartonado"], # Estándar: Imp -> Troq -> Desc
        "maquinas": pd.DataFrame({
            "Maquina": ["Flexo 1", "Troquel 1", "Descartonadora 1"],
            "Proceso": ["Impresión Flexo", "Troquelado", "Descartonado"]
        }),
        "pending_processes": [],
        "ignore_constraints": True # Ignore MP checks etc
    }

    # 2. Create Dummy Orders
    # Order A: Explicitly "T-I" (Troquelado BEFORE Impresion)
    # Order B: Standard (Impresion BEFORE Troquelado)
    df = pd.DataFrame([
        {
            "CodigoProducto": "E7478",
            "Subcodigo": "2039419",
            "Cliente": "Test",
            "CantidadPliegos": 1000,
            "ProcesoDpd": "T-I", # TRIGGER DYNAMIC ORDERING
            "MateriaPrima": "Carton",
            "FechaEntrega": datetime.now() + timedelta(days=10),
            # Pendientes
            "_PEN_ImpresionFlexo": "SÍ",
            "_PEN_Troquelado": "SÍ",
            "_PEN_Descartonado": "NO",
            "Urgente": "NO",
            "DueDate": datetime.now() + timedelta(days=10),
            "Bocas": 1,
            "PliAnc": 50,
            "PliLar": 50
        },
        {
            "CodigoProducto": "ORD_B_Standard",
            "Subcodigo": "1",
            "Cliente": "Test",
            "CantidadPliegos": 1000,
            "ProcesoDpd": "", # Follow Standard
            "MateriaPrima": "Carton",
            "FechaEntrega": datetime.now() + timedelta(days=10),
             # Pendientes
            "_PEN_ImpresionFlexo": "SÍ",
            "_PEN_Troquelado": "SÍ",
            "_PEN_Descartonado": "NO",
            "Urgente": "NO",
            "DueDate": datetime.now() + timedelta(days=10),
            "Bocas": 1,
            "PliAnc": 50,
            "PliLar": 50
        }
    ])

    # 3. Mocks for some column accesses that might happen inside programar
    # Ensure all boolean columns are present or handled? 
    # programar calls _expandir_tareas which checks columns.
    # It constructs 'tasks' DF. 
    # Let's import _expandir_tareas and mock it? No, testing integration is better.
    # But _expandir_tareas relies on CFG and input DF.
    
    # We need to ensure _expandir_tareas generates "Impresion Flexo" and "Troquelado" tasks for these orders.
    # _expandir_tareas usually iterates maquinas or processes.
    # In the code, it's not shown fully but I can guess.
    
    print("Running scheduler...")
    agenda_df, tasks_df, _, _ = programar(df, cfg, start=date.today())
    
    if agenda_df.empty:
        print("ERROR: GENDA IS EMPTY!")
        if not tasks_df.empty:
            print("Tasks generated:")
            print(tasks_df[["OT_id", "Proceso", "Maquina"]].head(10))
        else:
            print("TASKS DF IS ALSO EMPTY.")
        return

    print("\n--- RESULTS ---")
    print("\nUnique OTs in Agenda:", agenda_df["OT_id"].unique())
    print("Agenda Tasks:")
    print(agenda_df[["OT_id", "Proceso", "Maquina", "Inicio", "Fin"]].to_string())
    
    # Analyze Order A (Inverse: T -> I)
    df_a = agenda_df[agenda_df["OT_id"] == "E7478-2039419"]
    if df_a.empty:
        print("ERROR: No schedule for ORD_A!")
    else:
        troq_a = df_a[df_a["Proceso"] == "Troquelado"]
        imp_a = df_a[df_a["Proceso"] == "Impresión Flexo"]
        
        if not troq_a.empty and not imp_a.empty:
            start_t = troq_a.iloc[0]["Inicio"]
            start_i = imp_a.iloc[0]["Inicio"]
            print(f"ORD_A (T-I): Troq Start: {start_t}, Imp Start: {start_i}")
            if start_t < start_i:
                print("SUCCESS: Troquelado started BEFORE Impresion for T-I order.")
            else:
                print("FAILURE: Troquelado started AFTER or EQUAL to Impresion for T-I order (Expected Before).")
        else:
            print("ERROR: Missing tasks for ORD_A")

    # Analyze Order B (Standard: I -> T)
    df_b = agenda_df[agenda_df["OT_id"] == "ORD_B_Standard-1"]
    if df_b.empty:
        print("ERROR: No schedule for ORD_B!")
    else:
        troq_b = df_b[df_b["Proceso"] == "Troquelado"]
        imp_b = df_b[df_b["Proceso"] == "Impresión Flexo"]
        
        if not troq_b.empty and not imp_b.empty:
            start_t = troq_b.iloc[0]["Inicio"]
            start_i = imp_b.iloc[0]["Inicio"]
            print(f"ORD_B (Std): Troq Start: {start_t}, Imp Start: {start_i}")
            if start_i < start_t:
                print("SUCCESS: Impresion started BEFORE Troquelado for Standard order.")
            else:
                print("FAILURE: Impresion started AFTER or EQUAL to Troquelado for Standard order.")
        else:
            print("ERROR: Missing tasks for ORD_B")

if __name__ == "__main__":
    run_test()
