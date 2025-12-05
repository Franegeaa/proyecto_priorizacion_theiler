
import sys
import os
import pandas as pd
from collections import deque

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.schedulers.priorities import _cola_impresora_offset

def log(msg):
    with open("tests/debug_barnizado_unified.txt", "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def test_barnizado_unified():
    with open("tests/debug_barnizado_unified.txt", "w", encoding="utf-8") as f:
        f.write("=== TEST: Unified Offset Queue (Barniz + Print) ===\n")

    # Tasks:
    # 1. Print CMYK (Troquel 1) - Due D1
    # 2. Barniz Client A - Due D1
    # 3. Print Pantone (Color X) - Due D1
    # 4. Barniz Client A - Due D2 (Should group with Task 2?)
    
    tasks = [
        {"OT_id": "P1", "Proceso": "Impresión Offset", "Cliente": "ClientA", "CodigoTroquel": "T1", "Colores": "CMYK", "DueDate": "01/01/2025", "Urgente": "No", "CantidadPliegos": 1000},
        {"OT_id": "B1", "Proceso": "Barnizado", "Cliente": "ClientA", "CodigoTroquel": "T1", "Colores": "CMYK", "DueDate": "01/01/2025", "Urgente": "No", "CantidadPliegos": 1000},
        {"OT_id": "B2", "Proceso": "Barnizado", "Cliente": "ClientA", "CodigoTroquel": "T2", "Colores": "CMYK", "DueDate": "02/01/2025", "Urgente": "No", "CantidadPliegos": 1000},
        {"OT_id": "P2", "Proceso": "Impresión Offset", "Cliente": "ClientB", "CodigoTroquel": "T2", "Colores": "Pantone 123", "DueDate": "01/01/2025", "Urgente": "No", "CantidadPliegos": 1000},
    ]
    df = pd.DataFrame(tasks)
    
    log("Running _cola_impresora_offset...")
    q = _cola_impresora_offset(df)
    
    ordered_ids = [t["OT_id"] for t in q]
    log(f"Ordered IDs: {ordered_ids}")
    
    # Logic:
    # Barniz (ClientA) -> Group Key (0, clienta, barniz)
    # Print (ClientA) -> Group Key (1, clienta, T1)
    # Print (ClientB) -> Group Key (2, clientb, p123)
    
    # Sort order: Type 0 (Barniz) -> Type 1 (CMYK) -> Type 2 (Pantone)
    # So Barniz ClientA should come FIRST (B1, B2).
    # Then Print ClientA (P1).
    # Then Print ClientB (P2).
    
    # Expected: [B1, B2, P1, P2] (roughly).
    # B1 (Due D1), B2 (Due D2).
    
    # Verification: Check if B1 and B2 are contiguous.
    b_indices = [i for i, x in enumerate(ordered_ids) if x.startswith("B")]
    log(f"Barniz Indices: {b_indices}")
    
    assert b_indices == [0, 1] or b_indices == [1, 2] or b_indices == [2, 3] # They must be together
    log("Barnizado tasks are grouped together!")

if __name__ == "__main__":
    try:
        test_barnizado_unified()
    except Exception as e:
        log(f"FAIL: {e}")
        raise
