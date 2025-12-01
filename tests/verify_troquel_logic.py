import sys
import os
import pandas as pd
from datetime import datetime, time

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mocking config and helper functions to isolate logic
# We need to test the logic inside the loop in scheduler.py
# Since the logic is embedded in a large function, we will simulate the decision making process
# by replicating the logic we just modified.

def test_troquel_logic():
    print("Testing Troquelado Logic...")

    # Mock Data
    manuales = ["Manual 1", "Manual 2"]
    auto_name = "Automatica"
    
    # Mock Helper: _validar_medidas_troquel
    def _validar_medidas_troquel(maquina, anc, lar):
        m = maquina.lower()
        if "autom" in m: return anc >= 38 and lar >= 38
        if "manual 1" in m: return anc <= 80 and lar <= 105
        if "manual 2" in m: return anc <= 66 and lar <= 90
        return True

    # Logic under test
    def select_candidates(total_pliegos, bocas, anc, lar):
        posibles = manuales + [auto_name]
        candidatos_tamano = [m for m in posibles if _validar_medidas_troquel(m, anc, lar)]
        
        if not candidatos_tamano: return []

        candidatas = []
        
        # 2. REGLA DE BOCAS (> 6) -> Automática Obligatoria (si entra)
        if bocas > 6:
            if auto_name in candidatos_tamano:
                candidatas = [auto_name]
            else:
                candidatas = [m for m in candidatos_tamano if m != auto_name]
        
        # 3. REGLA DE CANTIDAD (> 3000) -> Automática Obligatoria (si entra)
        elif total_pliegos > 3000:
            if auto_name in candidatos_tamano:
                candidatas = [auto_name]
            else:
                candidatas = [m for m in candidatos_tamano if m != auto_name]
        
        # 4. DEFAULT (<= 3000 y <= 6 Bocas) -> Preferencia Manual (NEW LOGIC)
        else:
            # Intentar filtrar solo manuales (excluir Auto)
            manuales_compatibles = [m for m in candidatos_tamano if m != auto_name]
            
            if manuales_compatibles:
                candidatas = manuales_compatibles
            else:
                # Si no entra en ninguna manual (por tamaño), permitimos Auto
                candidatas = candidatos_tamano
        
        return candidatas

    # Case 1: Small order (1000), fits Manual and Auto
    # Should prefer Manual
    res1 = select_candidates(1000, 2, 50, 50)
    assert "Automatica" not in res1, f"Case 1 Failed: Should exclude Automatica. Got {res1}"
    assert any("Manual" in m for m in res1), f"Case 1 Failed: Should include Manuals. Got {res1}"
    print("Case 1 Passed: Small order prefers Manual.")

    # Case 2: Small order (1000), too big for Manual (e.g., 90x100 - Manual 2 max 66x90, Manual 1 max 80x105)
    # Let's try 85x110 (Too big for Manual 1 and 2) -> Should go to Auto
    # Manual 1: 80x105. 85 > 80.
    res2 = select_candidates(1000, 2, 85, 110)
    assert res2 == ["Automatica"], f"Case 2 Failed: Should be Automatica only. Got {res2}"
    print("Case 2 Passed: Small order too big for Manuals goes to Auto.")

    # Case 3: Large order (5000) -> Should go to Auto
    res3 = select_candidates(5000, 2, 50, 50)
    assert res3 == ["Automatica"], f"Case 3 Failed: Should be Automatica. Got {res3}"
    print("Case 3 Passed: Large order goes to Auto.")

    # Case 4: High bocas (8) -> Should go to Auto
    res4 = select_candidates(1000, 8, 50, 50)
    assert res4 == ["Automatica"], f"Case 4 Failed: Should be Automatica. Got {res4}"
    print("Case 4 Passed: High bocas goes to Auto.")

if __name__ == "__main__":
    test_troquel_logic()
