import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.demo_data import generate_demo_dataframe
from modules.data_processor import process_uploaded_dataframe
from modules.scheduler import programar
from modules.schedulers.tasks import _expandir_tareas
from modules.config_loader import cargar_config, construir_calendario, es_dia_habil
import pandas as pd

def verify_demo_mode():
    print("--- Verifying Demo Mode (Static File) ---")
    try:
        # 1. Load Data
        df = generate_demo_dataframe()
        print(f"Loaded DataFrame with {len(df)} rows.")
        if df.empty:
            print("ERROR: DataFrame is empty. Check file path 'config/FormIAConsulta1a 23-01-26.xlsx'.")
            return False
            
        # 2. Process Data
        print("\n--- Processing Data ---")
        df_processed = process_uploaded_dataframe(df)
        print("Data processed successfully.")
        
        # Check flags
        print("\n--- Checking Flags ---")
        flags = [c for c in df_processed.columns if c.startswith("_PEN_")]
        total_pending = 0
        for f in flags:
            count = df_processed[f].sum()
            total_pending += count
            if count > 0:
                print(f"{f}: {count} orders pending")
            
        if total_pending == 0:
            print("CRITICAL WARNING: No pending flags set! Schedule will be empty.")

        # 3. Task Expansion
        print("\n--- Testing Task Expansion ---")
        config_path = "config/Config_Priorizacion_Theiler.xlsx"
        if os.path.exists(config_path):
            cfg = cargar_config(config_path)
            
            tasks = _expandir_tareas(df_processed, cfg)
            print(f"Expanded Tasks: {len(tasks)}")
            if not tasks.empty:
                 print("Tasks sample process:", tasks["Proceso"].unique())
                 print("Tasks sample Machine:", tasks["Maquina"].unique())

            # 4. Simulate Scheduling
            print("\n--- Simulating Scheduling ---")
            start_date = pd.Timestamp.today().date()
            schedule, _, _, _ = programar(df_processed, cfg, start=start_date, start_time="06:00")
            
            print(f"Scheduler finished. Generated {len(schedule)} schedule items.")
            if not schedule.empty:
                print("Schedule Generated Successfully.")
                print("First 3 items:\n", schedule[["Maquina", "OT_id", "Inicio", "Fin"]].head(3))
            else:
                print("Warning: Schedule is empty.")
        else:
            print(f"Warning: Config file not found at {config_path}")
            
        return True
        
    except Exception as e:
        print(f"\nERROR: Demo mode verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    verify_demo_mode()
