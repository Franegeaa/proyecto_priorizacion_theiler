import pandas as pd
from collections import deque
import os
import sys

# Mocking modules that might not be easily importable
sys.path.append(os.getcwd())

from modules.schedulers.priorities import _cola_impresora_universal
from modules.utils.config_loader import cargar_configuracion

try:
    df = pd.read_excel('FormIAConsulta1a (7).xlsx')
    
    # Simulate partial loading from scheduler.py
    q = df.copy()
    q["_fecha_imp"] = pd.to_datetime(q["FechaImDdp"], errors="coerce")
    q["_priori_imp_num"] = pd.to_numeric(q["PrioriImp"], errors="coerce").fillna(9999)
    # Mocking other columns the priority module expects
    q["ManualPriority"] = pd.to_numeric(q["ManualPriority"], errors="coerce").fillna(9999)
    q["Urgente"] = q.get("UrgePed", False).fillna(False)
    q["DueDate"] = pd.to_datetime(q["FECH/ENT."], errors="coerce")
    q["_cliente_key"] = q["CLIENTE"].str.lower().str.strip()
    q["_troq_key"] = q["CodTroTapa"].str.lower().str.strip()
    q["_color_key"] = q["Color 1"].fillna("").astype(str) + q["Color 2"].fillna("").astype(str)
    
    # Filter for the specific machine or just printing
    q_imp = q[q['ImpresionSNDpd'] == True].copy()
    
    queue = _cola_impresora_universal(q_imp)
    
    print("\nDRY RUN QUEUE ORDER:")
    found = []
    for i, item in enumerate(queue):
        art = str(item.get('ART/DDP', ''))
        if 'ESTANDAR' in art.upper() or 'MOSTACHYS' in art.upper() or 'MANJARES' in art.upper():
            print(f"{i+1:3d}. Art: {art[:30]} | Manual: {item['ManualPriority']} | Excel: {item['_priori_imp_num']} | Due: {item['DueDate']}")
            found.append(item)
            
except Exception as e:
    import traceback
    traceback.print_exc()
