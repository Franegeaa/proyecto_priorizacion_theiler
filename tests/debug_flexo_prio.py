
import pandas as pd
import sys
import os
from collections import deque

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from modules.schedulers.priorities import _cola_impresora_flexo

def test_flexo_prio():
    print("--- Test Start: Flexo Prioritization ---")
    
    # Mock Data:
    # Group 1: Urgent="Si", Color="Red", Due="2025-12-30" (Late Urgent)
    # Group 2: Urgent="Si", Color="Blue", Due="2025-12-10" (Early Urgent)
    # Group 3: Urgent="No", Color="Green", Due="2025-12-05" (Late Non-Urgent)
    
    data = [
        {
            "OT_id": "LATE-URGENT",
            "Cliente": "C1",
            "Colores": "Red",
            "Urgente": "Si",
            "DueDate": "30/12/2025",
            "CantidadPliegos": 1000
        },
        {
            "OT_id": "EARLY-URGENT",
            "Cliente": "C2",
            "Colores": "Blue",
            "Urgente": "Si",
            "DueDate": "10/12/2025",
            "CantidadPliegos": 1000
        },
        {
             "OT_id": "EARLY-NON-URGENT",
             "Cliente": "C3",
             "Colores": "Green",
             "Urgente": "No",
             "DueDate": "05/12/2025",
             "CantidadPliegos": 1000
        }
    ]
    
    df = pd.DataFrame(data)
    
    # Run Priority Logic
    queue = _cola_impresora_flexo(df)
    
    print("\nSorted Queue:")
    for t in queue:
        print(f"ID: {t['OT_id']} | Color: {t['Colores']} | Due: {t['DueDate']} | Urg: {t['Urgente']}")
        
    # Analysis
    first = queue[0]
    second = queue[1]
    third = queue[2]
    
    # Expectation: 
    # 1. Early Urgent (Blue) because Group Urgent=True and Date=Dec 10
    # 2. Late Urgent (Red) because Group Urgent=True and Date=Dec 30
    # 3. Early Non-Urgent (Green) because Group Urgent=False
    
    if first["OT_id"] == "EARLY-URGENT" and second["OT_id"] == "LATE-URGENT":
        print("\nCONFIRMED: Urgent groups are sorted by date. Late urgent tasks come after early urgent tasks.")
        print("This explains why the user's order is 'late' if there are many earlier urgent tasks.")
    else:
        print("\nUNEXPECTED ORDER.")

if __name__ == "__main__":
    test_flexo_prio()
