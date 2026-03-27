import pandas as pd
from collections import deque
import os
import sys

# Mocking modules
sys.path.append(os.getcwd())

from modules.schedulers.priorities import _cola_impresora_universal

try:
    df = pd.read_excel('FormIAConsulta1a (7).xlsx')
    
    # Pre-processing as in scheduler.py
    q = df.copy()
    q["_fecha_imp"] = pd.to_datetime(q["FechaImDdp"], errors="coerce")
    q["_priori_imp_num"] = pd.to_numeric(q["PrioriImp"], errors="coerce").fillna(9999)
    q["ManualPriority"] = pd.to_numeric(q["ManualPriority"], errors="coerce").fillna(9999)
    q["Urgente"] = q.get("UrgePed", False).fillna(False)
    q["DueDate"] = pd.to_datetime(q["FECH/ENT."], errors="coerce")
    
    # Matching keys for priorities.py
    q["_cliente_key"] = q["CLIENTE"].str.lower().str.strip()
    q["_troq_key"] = q["CodTroTapa"].astype(str).str.lower().str.strip()
    q["_color_key"] = q["Color 1"].fillna("").astype(str)
    
    # Filter for Heidelberg (ImpresoraDdp 31.0)
    q_heid = q[(q['ImpresionSNDpd'] == True) & (q['ImpresoraDdp'] == 31.0)].copy()
    
    print(f"Total Heidelberg tasks: {len(q_heid)}")
    
    queue_deque = _cola_impresora_universal(q_heid)
    queue = list(queue_deque)
    
    print("\nACTUAL QUEUE ORDER (DRY RUN):")
    for i, item in enumerate(queue[:30]):
        art = str(item.get('ART/DDP', ''))
        prio_imp = item.get('_priori_imp_num')
        prio_man = item.get('ManualPriority')
        due = item.get('DueDate')
        print(f"{i+1:3d}. Art: {art[:30]} | Man: {prio_man} | Exc: {prio_imp} | Due: {due}")

except Exception as e:
    import traceback
    traceback.print_exc()
