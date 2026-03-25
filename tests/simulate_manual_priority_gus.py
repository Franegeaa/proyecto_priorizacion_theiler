import pandas as pd
from datetime import datetime, time, date
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from modules.scheduler import programar
from modules.utils.config_loader import cargar_config
from modules.utils.data_processor import process_uploaded_dataframe

def simulate_priority():
    cfg = cargar_config('config/Config_Priorizacion_Theiler.xlsx')
    df_raw = pd.read_excel('FormIAConsulta1a (6).xlsx', engine='openpyxl')
    df = process_uploaded_dataframe(df_raw)
    
    if "manual_overrides" not in cfg:
        cfg["manual_overrides"] = {}
    if "manual_priorities" not in cfg["manual_overrides"]:
        cfg["manual_overrides"]["manual_priorities"] = {}
        
    geselinas = df[df["Cliente-articulo"].astype(str).str.contains("GESELINA", case=False, na=False)]
    test_idx = geselinas.index[-1]
    test_ot = df.loc[test_idx, "OT_id"]
    key_proc = (test_ot, "Troq Nº 1 Gus")
    cfg["manual_overrides"]["manual_priorities"][key_proc] = 1
    
    today = datetime(2026, 3, 27, 7, 0).date()
    start_time = time(7, 0)
    
    schedule, _, _, _ = programar(df, cfg, start=today, start_time=start_time)
    
    gus_sched = schedule[schedule["Maquina"] == "Troq Nº 1 Gus"]
    gus_sched = gus_sched.sort_values(by="Inicio")
    print("\n-- Troq Nº 1 Gus Schedule --")
    for idx, row in gus_sched.iterrows():
         print(f"{row['Inicio'].strftime('%d/%m %H:%M')} -> {row['Fin'].strftime('%d/%m %H:%M')} | Prio: {row.get('ManualPriority', 9999)} | OT: {row['OT_id']} | Art: {row['Cliente-articulo'][:20]}")

if __name__ == "__main__":
    simulate_priority()
