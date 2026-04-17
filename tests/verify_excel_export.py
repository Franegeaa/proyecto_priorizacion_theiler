import pandas as pd
from io import BytesIO
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from modules.utils.exporters import generar_excel_ot_horizontal

# Verification Logic
def test_export():
    # Mock data with valid canonical process names
    data = {
        "OT_id": ["OT1", "OT1", "OT2"],
        "CodigoProducto": ["P1", "P1", "P2"],
        "Subcodigo": ["S1", "S1", "S2"],
        "Cliente": ["C1", "C1", "C2"],
        "CantidadPliegos": [1000, 1000, 2000],
        "DueDate": [pd.Timestamp("2023-01-05"), pd.Timestamp("2023-01-05"), pd.Timestamp("2023-01-06")],
        "Colores": ["4/0", "4/0", "1/0"],
        "CodigoTroquel": ["T1", "T1", "T2"],
        "EnRiesgo": [False, False, False],
        "Atraso_h": [0, 0, 0],
        "Inicio": [pd.Timestamp("2023-01-01 08:00"), pd.Timestamp("2023-01-01 10:00"), pd.Timestamp("2023-01-02 08:00")],
        "Fin": [pd.Timestamp("2023-01-01 09:00"), pd.Timestamp("2023-01-01 11:00"), pd.Timestamp("2023-01-02 12:00")],
        "Proceso": ["Cortadora Bobina", "Impresión Offset", "Troquelado"],
        "Maquina": ["Cortadora", "Offset", "Troqueladora"],
        "Duracion_h": [1, 1, 4]
    }
    df = pd.DataFrame(data)
    
    result = generar_excel_ot_horizontal(df)
    
    # Assertions
    # Check for fixed columns
    assert "Cortadora Bobina - Maquina" in result.columns
    assert "Impresión Offset - Maquina" in result.columns
    assert "Troquelado - Maquina" in result.columns
    
    # Check for unused columns (should exist but be empty/present)
    assert "Barnizado - Maquina" in result.columns
    
    assert len(result) == 2  # 2 unique OTs
    
    # Check OT1 content
    ot1 = result[result["OT_id"] == "OT1"].iloc[0]
    assert ot1["Cortadora Bobina - Maquina"] == "Cortadora", f"Expected Cortadora, got {ot1['Cortadora Bobina - Maquina']}"
    assert ot1["Impresión Offset - Maquina"] == "Offset", f"Expected Offset, got {ot1['Impresión Offset - Maquina']}"
    # Check that unused process is empty
    assert ot1["Barnizado - Maquina"] == "", "Expected empty string for unused process"
    
    print("VERIFICATION_SUCCESS")

if __name__ == "__main__":
    test_export()
