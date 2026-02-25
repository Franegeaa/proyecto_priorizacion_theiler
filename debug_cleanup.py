from modules.utils.config_loader import cargar_config, normalize_machine_name
import json

db_json = {"E7493-2025101|Guillotina 1": 1, "E7442-3047112|Heidelberg": 1, "E7493-2025101|Heidelberg": 2, "E7442-3047112|Duyan": 1, "E7493-2025101|Troq N\u00ba 2 Ema": 3, "E7493-2025101|Troq N\u00ba 1 Gus": 3, "E7442-3047112|Troq N\u00ba 2 Ema": 1}

priorities = {}
for k, v in db_json.items():
    if "|" in k:
        p = k.split("|", 1)
        priorities[(p[0], p[1])] = v

cfg = cargar_config()
maq_to_proc = dict(zip(cfg["maquinas"]["Maquina"], cfg["maquinas"]["Proceso"]))

# Simulate saving a new priority: OT="E7493-2025101" to "Duyan" (which is Troquelado)
ot = "E7493-2025101"
maq_normalized = "Duyan"
current_proc = maq_to_proc.get(maq_normalized, "")

print(f"Assigning to {maq_normalized}, Target Process: {current_proc}")

stale_keys = []
for (p_ot, p_maq) in list(priorities.keys()):
    if p_ot == ot and p_maq != maq_normalized:
        other_proc = maq_to_proc.get(p_maq, "")
        print(f"Comparing with existing: {p_ot} / {repr(p_maq)} -> Process: {repr(other_proc)}")
        if other_proc == current_proc or (current_proc in other_proc and len(current_proc)>3):
            stale_keys.append((p_ot, p_maq))

print(f"Keys to delete: {stale_keys}")

