
import pandas as pd
import sys
import os

# Add root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.utils.config_loader import cargar_config, construir_calendario
from modules.utils.data_processor import cargar_datos
from modules.schedulers.tasks import _expandir_tareas
from modules.schedulers.priorities import _cola_impresora_offset, _clave_prioridad_maquina
from modules.utils.tiempos_y_setup import usa_setup_menor

def investigate():
    cfg = cargar_config()
    df_ordenes = cargar_datos(cfg)
    
    # Filter for Los Nativos orders
    # Check "Cliente" column
    # Using the IDs from the screenshot
    target_ids = ["E7398-2025277", "E7398-2025278"]
    
    # Reconstruct OT_id in df_ordenes if not present (data_processor usually does it?)
    if "OT_id" not in df_ordenes.columns:
         df_ordenes["OT_id"] = df_ordenes["CodigoProducto"].astype(str) + "-" + df_ordenes["Subcodigo"].astype(str)
         
    nativos_orders = df_ordenes[df_ordenes["OT_id"].isin(target_ids)]
    
    print(f"Found {len(nativos_orders)} orders for Los Nativos.")
    
    print("\n--- Order Details ---")
    for _, row in nativos_orders.iterrows():
        print(f"OT: {row['OT_id']}")
        print(f"  Cliente: '{row['Cliente']}'")
        print(f"  Colores: '{row['Colores']}'")
        print(f"  CodigoTroquel: '{row['CodigoTroquel']}'")
        print(f"  DueDate: {row['DueDate']}")
        print(f"  Urgente: {row['Urgente']}")
        print(f"  FechaLlegadaChapas: {row['FechaLlegadaChapas']}")
        print(f"  FechaLlegadaTroquel: {row['FechaLlegadaTroquel']}")
        print("-" * 30)
        
    # Check Expandir Tareas
    tasks = _expandir_tareas(df_ordenes, cfg)
    nativos_tasks = tasks[tasks["OT_id"].isin(target_ids)]
    
    print("\n--- Offset Tasks ---")
    offset_tasks = nativos_tasks[nativos_tasks["Proceso"].str.contains("Offset", case=False, na=False)]
    
    for _, t in offset_tasks.iterrows():
        print(f"Task for {t['OT_id']}: {t['Proceso']}")
        
    if len(offset_tasks) >= 2:
        t1 = offset_tasks.iloc[0].to_dict()
        t2 = offset_tasks.iloc[1].to_dict()
        print("\n--- Setup Check ---")
        print(f"Checking setup between {t1['OT_id']} and {t2['OT_id']}")
        is_setup = usa_setup_menor(t1, t2, "Impresión Offset")
        print(f"usa_setup_menor: {is_setup}")
        
    # Check Queue Logic
    # Fake queue with these tasks
    q = offset_tasks.copy()
    # Add a dummy task to see sorting against it
    # We need to see how they are grouped.
    
    print("\n--- Queue Sorting (Priorities) ---")
    queue = _cola_impresora_offset(q)
    print("Queue Order:")
    for item in queue:
        print(f"  OT: {item['OT_id']} | Due: {item['DueDate']} | Client: {item['Cliente']}")

if __name__ == "__main__":
    investigate()
