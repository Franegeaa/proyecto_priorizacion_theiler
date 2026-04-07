import pandas as pd
from datetime import datetime, time, date
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from modules.scheduler import programar
from modules.utils.config_loader import cargar_config
from modules.utils.data_processor import process_uploaded_dataframe

def simulate_teppanyaki():
    cfg = cargar_config('config/Config_Priorizacion_Theiler.xlsx')
    
    df_raw = pd.read_excel('FormIAConsulta1a (6).xlsx', engine='openpyxl')
    df = process_uploaded_dataframe(df_raw)
    
    today = datetime(2026, 3, 27, 7, 0).date()
    start_time = time(7, 0)
    
    schedule, _, _, _ = programar(df, cfg, start=today, start_time=start_time)
    
    tep_sched = schedule[schedule["Cliente-articulo"].astype(str).str.contains("TEPPANYAKI", case=False, na=False)]
    print("\n--- TEPPANYAKI ---")
    if tep_sched.empty:
        print("No se agendó TEPPANYAKI")
    else:
        for idx, row in tep_sched.iterrows():
            print(f"{row['Proceso']} en {row['Maquina']}: {row['Inicio']} -> {row['Fin']}")

if __name__ == "__main__":
    simulate_teppanyaki()
