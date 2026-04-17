
import pandas as pd
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

# Mock minimal config
cfg = {
    "maquinas": pd.DataFrame({
        "Maquina": ["Imp1"],
        "Proceso": ["Impresion"],
        "Velocidad": [1000]
    }),
    "manual_overrides": {
        "urgency_overrides": {
            ("123-1", "Impresion"): False # Override to FALSE
        }
    },
    "orden_std": ["Impresion"],
    "horas_por_dia": 24, # Simple
    "dias_laborales": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "turnos": [{"inicio": "00:00", "fin": "23:59"}],
    "feriados": []
}

# Dummy Tasks DataFrame representing what `_expandir_tareas` would return approximately
# or we can test the logic block directly. 
# Testing `programar` is integration testing.
# Let's test the specific logic block insertion by importing? No, it's inside a function.
# I'll replicate the logic block I inserted to verify it works as expected on a dataframe.

def test_override_logic():
    print("Testing Override Logic...")
    
    # Create Tasks DF
    tasks = pd.DataFrame({
        "OT_id": ["123-1", "456-1"],
        "Proceso": ["Impresion", "Impresion"],
        "Urgente": [True, True] # Both start as True (e.g. from Excel)
    })
    
    print("Initial Tasks:")
    print(tasks)
    
    # APPLY LOGIC (Copied from scheduler.py)
    if "manual_overrides" in cfg:
        # 1. Apply Urgency Overrides
        if "urgency_overrides" in cfg["manual_overrides"]:
            urg_overrides = cfg["manual_overrides"]["urgency_overrides"]
            
            for (ot_urg, proc_urg), is_urgent in urg_overrides.items():
                print(f"Applying override: {ot_urg}, {proc_urg} -> {is_urgent}")
                mask = (tasks["OT_id"].astype(str) == str(ot_urg)) & (tasks["Proceso"].astype(str) == str(proc_urg))
                
                if mask.any():
                    tasks.loc[mask, "Urgente"] = is_urgent
                    
    print("\nTasks after Override:")
    print(tasks)
    
    # Assertions
    val_123 = tasks.loc[tasks["OT_id"] == "123-1", "Urgente"].iloc[0]
    val_456 = tasks.loc[tasks["OT_id"] == "456-1", "Urgente"].iloc[0]
    
    if val_123 == False and val_456 == True:
        print("\nSUCCESS: Override applied correctly!")
    else:
        print(f"\nFAILURE: Expected False/True, got {val_123}/{val_456}")

if __name__ == "__main__":
    test_override_logic()
