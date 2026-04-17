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
    
    # Check if this exact OT has PEN_Plastificado
    teps = df[df["Cliente-articulo"].astype(str).str.contains("TEPPANYAKI", case=False, na=False)]
    for idx, t in teps.iterrows():
        print("Encontrado:", t["Cliente-articulo"])
        print("PEN_Plastificado:", t["_PEN_Plastificado"])
        
        ot_id = t["OT_id"]
        
        today = datetime(2026, 3, 27, 7, 0).date()
        start_time = time(7, 0)
        
        schedule, _, _, _ = programar(df[df["OT_id"] == ot_id], cfg, start=today, start_time=start_time)
        
        print(f"\n--- SCHEDULE PARA {t['Cliente-articulo']} ---")
        if schedule.empty:
            print("No se agendó")
        else:
            for i, row in schedule.iterrows():
                print(f"{row['Proceso']} en {row['Maquina']}: {row['Inicio']} -> {row['Fin']}")
        print("="*40)

if __name__ == "__main__":
    simulate_teppanyaki()
