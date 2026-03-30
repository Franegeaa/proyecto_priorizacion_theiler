import pandas as pd
from datetime import date, time, datetime
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

# Debug specific OT
target_ot = "B5982-0101340"
print(f"--- Debugging {target_ot} ---")
row = df[df["OT_id"] == target_ot].iloc[0]
print(f"Impresion Offset Pending Flag: {row.get('_PEN_ImpresionOffset')}")
print(f"Material: {row.get('MateriaPrima')}")
print(f"PeliculaArt: {row.get('PeliculaArt')}")
print(f"FechaLlegadaChapas: {row.get('FechaLlegadaChapas')}")

# Run scheduler
schedule, carga_md, resumen_ot, detalle_maquina = programar(df, cfg, start=date(2026, 3, 30), start_time=time(7, 0))

print(f"\nTotal tasks scheduled: {len(schedule)}")
if not schedule.empty:
    target_tasks = schedule[schedule["OT_id"] == target_ot]
    print(f"Tasks scheduled for {target_ot}:")
    print(target_tasks[["Proceso", "Maquina", "Inicio", "Fin"]].to_string())

# Check all Impression Offset tasks
offset_tasks = schedule[schedule["Proceso"] == "Impresión Offset"]
print(f"\nTotal 'Impresión Offset' tasks scheduled: {len(offset_tasks)}")
if not offset_tasks.empty:
    print(offset_tasks[["OT_id", "Maquina"]].head())
else:
    # If 0, let's look at the colas at the beginning of the scheduler
    # We'll have to manually check why they fail.
    # Let's check machines and processes
    print("\nMachines in config:")
    print(cfg["maquinas"][["Maquina", "Proceso"]])
