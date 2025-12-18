import pandas as pd
from io import BytesIO
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from modules.exporters import generar_excel_ot_horizontal

# Verification Logic
def test_export():
    # Mock data
    data = {
        "OT_id": ["OT1", "OT1", "OT2"],
        "CodigoProducto": ["P1", "P1", "P2"],
        "Subcodigo": ["S1", "S1", "S2"],
        "Cliente": ["C1", "C1", "C2"],
        "Inicio": [pd.Timestamp("2023-01-01 08:00"), pd.Timestamp("2023-01-01 10:00"), pd.Timestamp("2023-01-02 08:00")],
        "Fin": [pd.Timestamp("2023-01-01 09:00"), pd.Timestamp("2023-01-01 11:00"), pd.Timestamp("2023-01-02 12:00")],
        "Proceso": ["Corte", "Impresion", "Troquel"],
        "Maquina": ["Cortadora", "Offset", "Troqueladora"],
        "Duracion_h": [1, 1, 4]
    }
    df = pd.DataFrame(data)
    
    result = generar_excel_ot_horizontal(df)
    
    # Assertions
    assert "Paso 1 - Proceso" in result.columns
    assert "Paso 2 - Proceso" in result.columns
    assert len(result) == 2  # 2 unique OTs
    
    # Check OT1 content
    ot1 = result[result["OT_id"] == "OT1"].iloc[0]
    assert ot1["Paso 1 - Maquina"] == "Cortadora", f"Expected Cortadora, got {ot1['Paso 1 - Maquina']}"
    assert ot1["Paso 2 - Maquina"] == "Offset", f"Expected Offset, got {ot1['Paso 2 - Maquina']}"
    
    print("VERIFICATION_SUCCESS")

if __name__ == "__main__":
    test_export()
