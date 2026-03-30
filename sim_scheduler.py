import pandas as pd
from datetime import date, time
from modules.utils.config_loader import cargar_config
from modules.utils.data_processor import process_uploaded_dataframe
from modules.scheduler import programar

# Load config
cfg = cargar_config("config/Config_Priorizacion_Theiler.xlsx")

# Load data
df_raw = pd.read_excel('FormIAConsulta1a (8).xlsx')
df = process_uploaded_dataframe(df_raw)

# Fix config for simulation
cfg["maquinas_activas"] = cfg["maquinas"]["Maquina"].tolist()
cfg["feriados"] = []
cfg["locked_assignments"] = {}
cfg["manual_overrides"] = {}
cfg["custom_ids"] = {}
cfg["downtimes"] = []
cfg["horas_extras"] = {}

schedule, carga_md, resumen_ot, detalle_maquina = programar(df, cfg, start=date(2026, 3, 30), start_time=time(7, 0))

print(f"Total tasks scheduled: {len(schedule)}")
if not schedule.empty:
    offset_sched = schedule[schedule["Maquina"] == "Heidelberg"]
    print(f"Tasks scheduled on Heidelberg: {len(offset_sched)}")
    
    if not offset_sched.empty:
        print("\n--- SCHEDULED HEIDELBERG TASKS ---")
        show_cols = ["OT_id", "Cliente", "Proceso", "MateriaPrima", "Urgente", "PrioriImp", "Inicio", "Fin"]
        print(offset_sched[show_cols].head(15).to_string())
    
    pendientes = []
    for i, row in df.iterrows():
        if row.get("_PEN_ImpresionOffset") == True:
            ot = row["OT_id"]
            if schedule.empty or not ((schedule["OT_id"] == ot) & (schedule["Proceso"] == "Impresión Offset")).any():
                pendientes.append(ot)
                
    print(f"\nOrders with _PEN_ImpresionOffset=True but NOT scheduled for Impresión Offset: {len(pendientes)}")
    print(pendientes[:10])
