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
    
    # Init blank overrides if not present
    if "manual_overrides" not in cfg:
        cfg["manual_overrides"] = {}
    if "manual_priorities" not in cfg["manual_overrides"]:
        cfg["manual_overrides"]["manual_priorities"] = {}
        
    geselinas = df[df["Cliente-articulo"].astype(str).str.contains("GESELINA", case=False, na=False)]
    if not geselinas.empty:
        df = df.copy() # Avoid SettingWithCopyWarning
        test_idx = geselinas.index[-1]
        test_ot = df.loc[test_idx, "OT_id"]
        
        # Inject directly into tasks.py dictionary expected format (tuple of OT, MACHINE)
        # Assuming we want to force it on Troq Nº 1 Gus to compete with TEPPANYAKI
        key_proc = (test_ot, "Troq Nº 1 Gus")
        cfg["manual_overrides"]["manual_priorities"][key_proc] = 1
        
        print(f"Forced cfg ManualPriority=1 on {key_proc}")
    else:
        print("No se encontró GESELINA")
        return
        
    tep_exact = df[df["Cliente-articulo"].astype(str).str.contains("TEPPANYAKI", case=False, na=False)]
    if not tep_exact.empty:
        tep_ot = tep_exact.iloc[0]["OT_id"]
        print(f"TEPPANYAKI OT_id: {tep_ot}, PrioriImp: {tep_exact.iloc[0].get('PrioriImp')}")
    else:
        print("No se encontró TEPPANYAKI")
        return
        
    today = datetime(2026, 3, 27, 7, 0).date()
    start_time = time(7, 0)
    
    schedule, _, _, _ = programar(df, cfg, start=today, start_time=start_time)
    
    print("\n-- Schedule Results --")
    sched_test = schedule[schedule["OT_id"].isin([test_ot, tep_ot])]
    
    sched_test = sched_test.sort_values(by="Inicio")
    for idx, row in sched_test.iterrows():
         if row['Proceso'] == 'Troquelado':
             print(f"{row['OT_id']} - {row['Proceso']} en {row['Maquina']}: {row['Inicio']} -> {row['Fin']} (Prio: {row.get('ManualPriority', 'N/A')})")

if __name__ == "__main__":
    simulate_priority()
