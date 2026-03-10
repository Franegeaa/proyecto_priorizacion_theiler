import sys
import os
import pandas as pd
from datetime import datetime, date, time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from modules.utils.config_loader import load_config_and_data
from modules.scheduler import programar
from modules.schedulers.tasks import _expandir_tareas
from modules.schedulers.priorities import _cola_impresora_offset

def debug_heidelberg_queue():
    cfg = load_config_and_data()
    df_ordenes = cfg['df_ordenes']
    
    tasks = _expandir_tareas(df_ordenes, cfg)
    
    tasks_heidelberg = tasks[tasks["Maquina"].astype(str).str.contains("Heidelberg", case=False, na=False)].copy()
    
    print(f"Total tasks for Heidelberg: {len(tasks_heidelberg)}")
    
    # Generate the queue
    q = _cola_impresora_offset(tasks_heidelberg)
    
    print("\n=== Initial Heidelberg Queue Order ===")
    for i, t in enumerate(q):
        prod = str(t.get("CodigoProducto", "")) + " " + str(t.get("Cliente-articulo", ""))
        prio = t.get("ManualPriority")
        client = t.get("Cliente", "")
        colores = t.get("Colores", "")
        troq = t.get("CodigoTroquel", "")
        due = t.get("DueDate")
        print(f"{i:03d} | Prio: {prio} | Prod: {prod[:30]} | Cli: {client[:15]} | Col: {colores} | Troq: {troq} | Due: {due}")

if __name__ == "__main__":
    debug_heidelberg_queue()
