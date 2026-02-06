
import pandas as pd
from modules.schedulers.machines import elegir_maquina, validar_medidas_troquel

# 1. Mock Config
data = {
    "Maquina": ["Duyan", "Troq Nº 2 Ema", "Troq Nº 1 Gus", "Iberica", "Troqueladora Automatica"],
    "Proceso": ["Troquelado", "Troquelado", "Troquelado", "Troquelado", "Troquelado"]
}
cfg = {
    "maquinas": pd.DataFrame(data)
}

# 2. Mock Orden (E7493-2025232)
# Dimensions: 36 x 51
orden = {
    "CodigoProducto": "E7493-2025232",
    "PliAnc": 36,
    "PliLar": 51,
    "CodigoTroquel": "A316"
}

# 3. Test Validation
print("--- TEST VALIDATION DIRECTLY ---")
for m in cfg["maquinas"]["Maquina"]:
    valid = validar_medidas_troquel(m, 36, 51)
    print(f"Machine: {m} | 36x51 Valid? {valid}")

# 4. Test Selection
print("\n--- TEST SELECTION ---")
seleccion = elegir_maquina("Troquelado", orden, cfg)
print(f"Original Selection (Default Order): {seleccion}")

# 5. Test with ONLY Duyan (Simulate manual machines disabled)
cfg_only_duyan = {
    "maquinas": pd.DataFrame({"Maquina": ["Duyan"], "Proceso": ["Troquelado"]})
}
seleccion_only_duyan = elegir_maquina("Troquelado", orden, cfg_only_duyan)
print(f"Selection with ONLY Duyan: {seleccion_only_duyan}")
