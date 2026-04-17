
import sys
import os
import pandas as pd
from datetime import datetime, time, timedelta, date
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock external dependencies
import modules.utils.tiempos_y_setup
modules.utils.tiempos_y_setup.tiempo_operacion_h = MagicMock(return_value=(0, 1.0)) # 1 hour per task
modules.utils.tiempos_y_setup.usa_setup_menor = MagicMock(return_value=False)
modules.utils.tiempos_y_setup.capacidad_pliegos_h = MagicMock(return_value=1000)
modules.utils.tiempos_y_setup.setup_base_min = MagicMock(return_value=15)
modules.utils.tiempos_y_setup.setup_menor_min = MagicMock(return_value=5)

from modules.scheduler import programar

def run_test():
    # 1. Setup Config
    # We need a setup where:
    # - Printer (Flexo) is the bottleneck or target.
    # - Guillotine feeds the Printer.
    cfg = {
        "jornada": pd.DataFrame({"Parametro": ["Horas_base_por_dia"], "Valor": [24]}),
        "feriados": set(),
        "orden_std": ["Guillotina", "Impresión Flexo"], 
        "maquinas": pd.DataFrame({
            "Maquina": ["Guillotina 1", "Flexo 1"],
            "Proceso": ["Guillotina", "Impresión Flexo"]
        }),
        "pending_processes": [],
        "ignore_constraints": True
    }

    # 2. Scenarios
    # Client A (GROUP): 
    #   - A1: Direct to Print (Ready Now)
    #   - A2: Needs Guillotine (Ready Now)
    # Client B (NOISE):
    #   - B1: Needs Guillotine (Ready Now)
    
    # Expected Flow (FIFO / Default):
    # T=0: Printer takes A1 (starts 0-1). Guillotine takes B1 (starts 0-1) [Assume B1 comes first in list or random]
    # T=1: Printer free. Guillotine finishes B1. Guillotine starts A2 (1-2).
    # T=1: Printer takes B1 (if ready) or waits for A2?
    # Ideally: Guillotine should prioritize A2 because A1 is already at printer!
    
    # Let's force B1 to be "ahead" of A2 in the input DF to verify FIFO bias.
    
    df = pd.DataFrame([
        # A1: Direct to Print (Already passed Guillotine or doesn't need it)
        {
            "CodigoProducto": "A1", "Subcodigo": "1", "Cliente": "ClientA",
            "CantidadPliegos": 1000, "MateriaPrima": "Carton",
            "_PEN_Guillotina": "NO", "_PEN_ImpresionFlexo": "SÍ",
            "DueDate": datetime.now() + timedelta(days=10),
            "FechaEntrega": datetime.now() + timedelta(days=10)
        },
        # B1: Needs Guillotine (Noise) - OLDER DUE DATE or FIRST IN LIST
        {
            "CodigoProducto": "B1", "Subcodigo": "1", "Cliente": "ClientB",
            "CantidadPliegos": 1000, "MateriaPrima": "Carton",
            "_PEN_Guillotina": "SÍ", "_PEN_ImpresionFlexo": "SÍ",
            "DueDate": datetime.now() + timedelta(days=5), # Urgent!
            "FechaEntrega": datetime.now() + timedelta(days=5) 
        },
        # A2: Needs Guillotine (Group friend of A1)
        {
            "CodigoProducto": "A2", "Subcodigo": "1", "Cliente": "ClientA",
            "CantidadPliegos": 1000, "MateriaPrima": "Carton",
            "_PEN_Guillotina": "SÍ", "_PEN_ImpresionFlexo": "SÍ",
            "DueDate": datetime.now() + timedelta(days=10),
            "FechaEntrega": datetime.now() + timedelta(days=10)
        }
    ])
    
    # Add dummies
    for col in ["Bocas", "PliAnc", "PliLar", "ProcesoDpd", "Urgente", "MateriaPrimaPlanta"]:
        df[col] = "" # Defaults
        
    print("Running scheduler...")
    agenda_df, _, _, _ = programar(df, cfg, start=date.today())
    
    # Check Guillotine Schedule
    guill = agenda_df[agenda_df["Maquina"] == "Guillotina 1"].sort_values("Inicio")
    print("\nGuillotine Schedule:")
    print(guill[["OT_id", "Cliente", "Inicio", "Fin"]].to_string())
    
    # Check if A2 comes before B1?
    # In standard FIFO, B1 (Due Day 5) should come before A2 (Due Day 10).
    # But with Group Priority, if we implement it, A2 should hopefully jump ahead 
    # IF A1 is "Actively Printing".
    
    # However, A1 starts printing at T=0. 
    # Guillotine decision happens at T=0.
    # Logic needs to see A1 in "Impresion Flexo" queue?
    # A1 is in Printer Queue at start? Yes.
    
    if len(guill) >= 2:
        first_guill = guill.iloc[0]["OT_id"]
        print(f"\nFirst in Guillotine: {first_guill}")
        
        if "A2" in first_guill:
            print("RESULT: A2 prioritized (Group Logic working or serendipity).")
        else:
            print("RESULT: B1 prioritized (Standard FIFO/Due Date).")

if __name__ == "__main__":
    run_test()
