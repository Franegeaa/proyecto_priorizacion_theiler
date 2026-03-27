import pandas as pd
from collections import deque
import sys
import os

sys.path.append(os.getcwd())
from modules.schedulers.priorities import _cola_troquelada

try:
    df = pd.read_excel('FormIAConsulta1a (7).xlsx')
    q = df[df['TroqueladoraDdp'] == 105.0].copy() # Assume 105 is Troq 2 Ema
    
    # Process columns as in priorities.py
    q["ManualPriority"] = pd.to_numeric(q.get("ManualPriority"), errors="coerce").fillna(9999)
    # Using the columns I saw in previous views
    q["PrioriTr"] = pd.to_numeric(q.get("PrioriTr"), errors="coerce").fillna(9999)
    q["DueDate"] = pd.to_datetime(q.get("FECH/ENT."), errors="coerce").fillna(pd.Timestamp.max)
    
    queue = _cola_troquelada(q)
    
    print("\nTROQ 2 QUEUE ORDER:")
    for i, item in enumerate(list(queue)[:20]):
        art = str(item.get('ART/DDP', ''))
        prio = item.get('PrioriTr')
        man = item.get('ManualPriority')
        troq = item.get('CodTroTapa')
        due = item.get('DueDate')
        print(f"{i+1:3d}. Prio Excel: {prio} | Man: {man} | Troq: {troq} | Due: {due} | Art: {art[:30]}")

except Exception as e:
    import traceback
    traceback.print_exc()
