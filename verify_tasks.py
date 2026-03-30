import pandas as pd
from datetime import date, time
from modules.utils.config_loader import cargar_config
from modules.utils.data_processor import process_uploaded_dataframe
from modules.scheduler import _expandir_tareas

# Load config
cfg = cargar_config("config/Config_Priorizacion_Theiler.xlsx")

# Load data
df_raw = pd.read_excel('FormIAConsulta1a (8).xlsx')
df = process_uploaded_dataframe(df_raw)

# Expand tasks
tasks = _expandir_tareas(df, cfg)

print(f"Total tasks expanded: {len(tasks)}")
if not tasks.empty:
    print("\nMachine counts in tasks:")
    print(tasks["Maquina"].value_counts())
    
    print("\nProcesses for Heidelberg:")
    h_tasks = tasks[tasks["Maquina"] == "Heidelberg"]
    if h_tasks.empty:
        # If no tasks for Heidelberg, maybe they are called 'Offset'?
        o_tasks = tasks[tasks["Maquina"] == "Offset"]
        if not o_tasks.empty:
            print("Tasks found for 'Offset' (not Heidelberg!):")
            print(o_tasks["Proceso"].value_counts())
        else:
            print("No tasks found for 'Heidelberg' OR 'Offset'.")
            # Let's check why elegir_maquina failed.
            from modules.schedulers.machines import elegir_maquina
            for idx, row in df.iterrows():
                if row.get("_PEN_ImpresionOffset"):
                    ot = row["OT_id"]
                    proc = "Impresión Offset"
                    maq = elegir_maquina(proc, row, cfg)
                    print(f"OT: {ot} | Material: {row['MateriaPrima']} | Assigned to: {maq}")
                    break
    else:
        print(h_tasks["Proceso"].value_counts())
        print("\nSample Offset tasks:")
        print(h_tasks[h_tasks["Proceso"] == "Impresión Offset"][["OT_id", "Cliente", "MateriaPrima"]].head())

# Check config machines again
print("\nMachines in cfg['maquinas']:")
print(cfg["maquinas"][["Maquina", "Proceso"]])
