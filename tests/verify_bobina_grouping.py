
import pandas as pd
from modules.schedulers.priorities import _cola_cortadora_bobina
from collections import deque

def test_bobina_grouping():
    print("--- Test: Cortadora Bobina Grouping ---")
    
    # Mock Tasks
    # T1: MP_A, 10x20, 100g (Due: 2024-01-05)
    # T2: MP_A, 10x20, 100g (Due: 2024-01-02) -> Same group as T1, but should run BEFORE T1 due to DueDate
    # T3: MP_A, 10x20, 200g (Due: 2024-01-03) -> Diff Gramaje
    # T4: MP_A, 30x40, 100g (Due: 2024-01-01) -> Diff Medida
    # T5: MP_B, 10x20, 100g (Due: 2024-01-01) -> Diff MP
    
    tasks = pd.DataFrame([
        {
            "OT_id": "T1", "MateriaPrima": "MP_A", "PliAnc": 10, "PliLar": 20, "Gramaje": 100,
            "DueDate": "05/01/2024", "Urgente": False, "CantidadPliegos": 1000
        },
        {
            "OT_id": "T2", "MateriaPrima": "MP_A", "PliAnc": 10, "PliLar": 20, "Gramaje": 100,
            "DueDate": "02/01/2024", "Urgente": False, "CantidadPliegos": 1000
        },
        {
            "OT_id": "T3", "MateriaPrima": "MP_A", "PliAnc": 10.0, "PliLar": 20.0, "Gramaje": 200,
            "DueDate": "03/01/2024", "Urgente": False, "CantidadPliegos": 1000
        },
        {
            "OT_id": "T4", "MateriaPrima": "MP_A", "PliAnc": 30, "PliLar": 40, "Gramaje": 100,
            "DueDate": "01/01/2024", "Urgente": False, "CantidadPliegos": 1000
        },
        {
            "OT_id": "T5", "MateriaPrima": "MP_B", "PliAnc": 10, "PliLar": 20, "Gramaje": 100,
            "DueDate": "01/01/2024", "Urgente": False, "CantidadPliegos": 1000
        },
    ])
    
    # Run Grouping
    q = _cola_cortadora_bobina(tasks)
    res = list(q)
    
    print("Result Sequence:")
    for t in res:
        print(f"OT: {t['OT_id']} | MP: {t['MateriaPrima']} | Size: {t['PliAnc']}x{t['PliLar']} | G: {t['Gramaje']} | Due: {t['DueDate']}")

    # Expected Logical Order logic is primarily by GROUP DueDate Min.
    # Group A: {T1, T2} (MP_A, 10x20, 100) -> MinDue: 02/01
    # Group B: {T3} (MP_A, 10x20, 200) -> MinDue: 03/01
    # Group C: {T4} (MP_A, 30x40, 100) -> MinDue: 01/01
    # Group D: {T5} (MP_B, 10x20, 100) -> MinDue: 01/01
    
    # Sort order of groups matches DueDate of the group.
    # 1. Group C (01/01) OR Group D (01/01) -> Tie breaker? Python default sort stability or tuple comparison. 
    # Tuple: (not Urgente, DueMin, MP, Medida, Gramaje)
    # C vs D: 
    # C: (False, 01/01, MP_A, 30x40, 100) 
    # D: (False, 01/01, MP_B, 10x20, 100)
    # "MP_A" < "MP_B" -> C comes before D.
    
    # 2. Group A (02/01)
    # 3. Group B (03/01)
    
    # Inside Group C: T4
    # Inside Group D: T5
    # Inside Group A: T2 (02/01) then T1 (05/01)
    # Inside Group B: T3
    
    # EXPECTED SEQUENCE: T4 -> T5 -> T2 -> T1 -> T3
    
    ids = [t['OT_id'] for t in res]
    expected = ["T4", "T5", "T2", "T1", "T3"]
    
    print(f"IDs: {ids}")
    assert ids == expected, f"Order mismatch! Expected {expected}, got {ids}"
    
    print("TEST PASSED")

if __name__ == "__main__":
    try:
        test_bobina_grouping()
    except AssertionError as e:
        print(f"TEST FAILED: {e}")
    except Exception as e:
        print(f"ERROR: {e}")
