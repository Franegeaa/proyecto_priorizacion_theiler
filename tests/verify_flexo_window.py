
import pandas as pd
import unittest
from datetime import datetime, timedelta
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from modules.schedulers.priorities import _cola_impresora_flexo

class TestFlexoWindow(unittest.TestCase):
    def test_window_logic(self):
        """
        Verify that orders are grouped by color IF within 1 day window.
        """
        # Case 1: Within Window (should group)
        # A: Day 1, Red
        # B: Day 2, Red (Day 1 + 1 day = Day 2. Included? "Ventana de 1 dia". Usually inclusive or < 24h. Let's assume <= 1 day difference)
        # C: Day 1.5, Blue
        
        # If strict date: A, C, B.
        # If window: A, B, C.
        
        print("\n--- Test Case 1: Within Window ---")
        data1 = [
            {"Cliente": "C1", "Colores": "Red", "DueDate": "01/01/2025", "Urgente": "No", "CantidadPliegos": 1000, "OT_id": "A"},
            {"Cliente": "C1", "Colores": "Red", "DueDate": "02/01/2025", "Urgente": "No", "CantidadPliegos": 1000, "OT_id": "B"},
            {"Cliente": "C1", "Colores": "Blue", "DueDate": "02/01/2025 12:00", "Urgente": "No", "CantidadPliegos": 1000, "OT_id": "C"},
        ]
        df1 = pd.DataFrame(data1)
        q1 = _cola_impresora_flexo(df1)
        res1 = [item["OT_id"] for item in q1]
        print(f"Result 1: {res1}")
        
        self.assertEqual(res1[0], "A")
        self.assertEqual(res1[1], "B", "B should be pulled up because it matches A's color and is within 1 day.")
        self.assertEqual(res1[2], "C")

    def test_outside_window_logic(self):
        # Case 2: Outside Window (should NOT group)
        # A: Day 1, Red
        # B: Day 3, Red (Diff = 2 days)
        # C: Day 2, Blue
        
        # Expected: A, C, B.
        
        print("\n--- Test Case 2: Outside Window ---")
        data2 = [
            {"Cliente": "C1", "Colores": "Red", "DueDate": "01/01/2025", "Urgente": "No", "CantidadPliegos": 1000, "OT_id": "A"},
            {"Cliente": "C1", "Colores": "Red", "DueDate": "03/01/2025", "Urgente": "No", "CantidadPliegos": 1000, "OT_id": "B"},
            {"Cliente": "C1", "Colores": "Blue", "DueDate": "02/01/2025", "Urgente": "No", "CantidadPliegos": 1000, "OT_id": "C"},
        ]
        df2 = pd.DataFrame(data2)
        q2 = _cola_impresora_flexo(df2)
        res2 = [item["OT_id"] for item in q2]
        print(f"Result 2: {res2}")
        
        self.assertEqual(res2[0], "A")
        self.assertEqual(res2[1], "C", "C shoud come second because B is too far to be grouped.")
        self.assertEqual(res2[2], "B")

if __name__ == '__main__':
    unittest.main()
