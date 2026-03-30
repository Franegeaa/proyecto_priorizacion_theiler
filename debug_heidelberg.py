import pandas as pd
from datetime import date, time, datetime
from modules.utils.config_loader import cargar_config
from modules.utils.data_processor import process_uploaded_dataframe
from modules.scheduler import _expandir_tareas
from modules.schedulers.priorities import _cola_impresora_offset
import collections

# Load config
cfg = cargar_config("config/Config_Priorizacion_Theiler.xlsx")
cfg["maquinas_activas"] = cfg["maquinas"]["Maquina"].tolist()

# Load data
df_raw = pd.read_excel('FormIAConsulta1a (8).xlsx')
df = process_uploaded_dataframe(df_raw)

# Expand tasks
tasks = _expandir_tareas(df, cfg)

# Get Heidelberg tasks
h_tasks = tasks[tasks["Maquina"] == "Heidelberg"].copy()
if h_tasks.empty:
    print("No tasks for Heidelberg!")
    exit()

# Get the queue as the scheduler would
q = _cola_impresora_offset(h_tasks)
# q is a deque of dicts (tasks)

print(f"Heidelberg queue size: {len(q)}")

# Simulate the state for B5982
# We need to recreate the dependencies logic
pendientes_por_ot = collections.defaultdict(set)
for _, t in tasks.iterrows():
    pendientes_por_ot[t["OT_id"]].add(t["Proceso"])

completado = collections.defaultdict(set)
# Assume no tasks completed yet

flujo_estandar = [p.strip() for p in cfg.get("orden_std", [])]

def clean(s):
    if not s: return ""
    s = str(s).lower().strip()
    trans = str.maketrans("áéíóúüñ", "aeiouun")
    s = s.translate(trans)
    if "flexo" in s: return "impresion flexo"
    if "offset" in s: return "impresion offset"
    if "troquel" in s: return "troquelado"
    return s

def mock_verificar(t):
    ot = t["OT_id"]
    proc_actual = t["Proceso"]
    proc_actual_clean = clean(proc_actual)
    
    local_flujo = list(flujo_estandar)
    if t.get("ProcesoDpd"):
        # The logic in scheduler.py reorders the flow based on ProcesoDpd
        # I'll simplify here but try to be accurate
        pass 
    
    flujo_clean = [clean(p) for p in local_flujo]
    if proc_actual_clean not in flujo_clean:
        return True, "Not in flow"
        
    idx = flujo_clean.index(proc_actual_clean)
    pendientes_clean = {clean(p) for p in pendientes_por_ot[ot]}
    
    deps = []
    for p_clean in flujo_clean[:idx]:
        if p_clean in pendientes_clean:
            if p_clean not in {clean(c) for c in completado[ot]}:
                deps.append(p_clean)
                
    if deps:
        return False, f"Blocked by: {deps}"
    
    # Check MateriaPrimaPlanta
    mp = str(t.get("MateriaPrimaPlanta")).strip().lower()
    mp_ok = mp in ("false", "0", "no", "falso", "") or not t.get("MateriaPrimaPlanta")
    if not mp_ok:
        return False, f"Blocked by MP: {t.get('MateriaPrimaPlanta')}"
        
    return True, "Ready"

print("\n--- FIRST 10 TASKS IN HEIDELBERG QUEUE ---")
for i in range(min(10, len(q))):
    t = q[i]
    runnable, reason = mock_verificar(t)
    print(f"{i}: OT={t['OT_id']} | Proc={t['Proceso']} | PrioriImp={t.get('PrioriImp')} | {reason}")
