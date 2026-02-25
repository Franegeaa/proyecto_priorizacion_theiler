import json
from modules.utils.config_loader import cargar_config, normalize_machine_name

cfg = cargar_config()

# Normalizamos las llaves de maq_to_proc también para que sea a prueba de balas!
maq_to_proc = {}
for m, p in zip(cfg["maquinas"]["Maquina"], cfg["maquinas"]["Proceso"]):
    maq_to_proc[normalize_machine_name(m)] = p

p_maq = "Troq Nº 1 Gus"
print(f"p_maq from DB: {repr(p_maq)}")
print(f"Normalized p_maq: {repr(normalize_machine_name(p_maq))}")
print(f"Result in maq_to_proc: {repr(maq_to_proc.get(normalize_machine_name(p_maq), 'NOT FOUND'))}")

for k in maq_to_proc.keys():
    if "Troq" in k:
        print(f"Key in dict: {repr(k)}")
