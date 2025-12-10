
import pandas as pd
import sys
import os
from collections import deque

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from modules.schedulers.priorities import _cola_impresora_flexo

def test_flexo_grouping():
    print("--- Test Start: Flexo Grouping ---")
    
    # Hypothesis:
    # Task A: Urgent=Si, Color="---K-" (Promotes Group K)
    # Task B: Urgent=No, Color="K----" (Rides along with Group K)
    # Task C: Urgent=Si, Color="--Y--" (Separate Group Y)
    
    # If Group K is treated as Urgent (due to A), and has earlier DueDate (from A),
    # Then A AND B will run before C.
    
    data = [
        {
            "OT_id": "URGENT-K-1",
            "Cliente": "C1",
            "Colores": "---K-",
            "Urgente": "Si",
            "DueDate": "10/12/2025",
            "CantidadPliegos": 1000
        },
        {
            "OT_id": "NORMAL-K-2",
            "Cliente": "C2",
            "Colores": "K----", # Stripped to 'k', same as above
            "Urgente": "No", 
            "DueDate": "20/12/2025",
            "CantidadPliegos": 1000
        },
        {
             "OT_id": "URGENT-Y-3",
             "Cliente": "C3",
             "Colores": "--Y--", # 'y'
             "Urgente": "Si",
             "DueDate": "12/12/2025",
             "CantidadPliegos": 1000
        }
    ]
    
    df = pd.DataFrame(data)
    
    queue = _cola_impresora_flexo(df)
    
    print("\nQueue Order:")
    for t in queue:
        print(f"ID: {t['OT_id']} | Color: {t['Colores']} | Urg: {t['Urgente']}")
        
    ids = [t['OT_id'] for t in queue]
    
    # Expected: URGENT-K-1, URGENT-Y-3, NORMAL-K-2
    # Strict Urgency means both urgents go first.
    if ids == ["URGENT-K-1", "URGENT-Y-3", "NORMAL-K-2"]:
        print("\nCONFIRMED: Strict Urgency Enforced. Normal tasks are bumped down.")
    else:
        print(f"\nResult: {ids}")

if __name__ == "__main__":
    test_flexo_grouping()
