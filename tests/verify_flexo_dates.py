
import pandas as pd
from collections import deque
import unittest
from datetime import datetime

# Import the function to test
# Adjust the path as needed to import safely
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.schedulers.priorities import _cola_impresora_flexo

class TestFlexoPriority(unittest.TestCase):
    def test_date_priority_over_color_blocks(self):
        """
        Verify that orders are prioritized by Date, breaking Color blocks if necessary.
        Current (Bad) Logic:
            A: Date 1, Color Red
            B: Date 10, Color Red
            C: Date 2, Color Blue
            
            Group Red min_date = 1. Group Blue min_date = 2.
            Sort Groups: Red, then Blue.
            Execution: A (1), B (10), C (2). 
            Error: B (10) runs before C (2).
            
        Desired Logic:
            A (1), C (2), B (10).
        """
        data = [
            {"Cliente": "C1", "Colores": "Red", "DueDate": "01/01/2025", "Urgente": "No", "CantidadPliegos": 1000, "OT_id": "A"},
            {"Cliente": "C1", "Colores": "Red", "DueDate": "10/01/2025", "Urgente": "No", "CantidadPliegos": 1000, "OT_id": "B"},
            {"Cliente": "C1", "Colores": "Blue", "DueDate": "02/01/2025", "Urgente": "No", "CantidadPliegos": 1000, "OT_id": "C"},
        ]
        
        df = pd.DataFrame(data)
        
        queue = _cola_impresora_flexo(df)
        
        # Convert to list of OTs
        result_ots = [item["OT_id"] for item in queue]
        
        print(f"Queue Order: {result_ots}")
        
        # We expect [A, C, B]
        # If the bug exists, we might get [A, B, C]
        
        self.assertEqual(result_ots[0], "A")
        self.assertEqual(result_ots[1], "C", "Order C (Date 02/01) should come before Order B (Date 10/01), effectively breaking the Red block.")
        self.assertEqual(result_ots[2], "B")

if __name__ == '__main__':
    unittest.main()
