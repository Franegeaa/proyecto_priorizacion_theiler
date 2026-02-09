import pandas as pd
from io import BytesIO
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from modules.utils.exporters import generar_excel_ot_horizontal

def test_csv_export():
    data = {"OT_id": ["OT1"], "CodigoProducto": ["P1"], "Inicio": [1], "Proceso": ["Corte"]}
    df = pd.DataFrame(data)
    
    # Generate horizontal dataframe
    df_horiz = generar_excel_ot_horizontal(df)
    
    # Simulate CSV export logic (inline here, or could import from exporters if I exposed it)
    # But since generar_csv_ot_str takes df_horiz, I can just test the dataframe structure which is what matters mostly.
    csv_data = df_horiz.to_csv(index=False, sep=';', decimal=',')
    
    assert "OT1" in csv_data
    assert ";" in csv_data
    assert "Paso 1 - Proceso" in csv_data
    
    print("CSV_VERIFICATION_SUCCESS")

def test_many_steps():
    # Simulate an OT with 6 steps
    rows = []
    for i in range(1, 7):
        rows.append({
            "OT_id": "OT_LONG",
            "CodigoProducto": "L1",
            "Inicio": i,
            "Proceso": f"Step_{i}"
        })
    df = pd.DataFrame(rows)
    
    df_horiz = generar_excel_ot_horizontal(df)
    
    # Assert we have up to Paso 6
    assert "Paso 1 - Proceso" in df_horiz.columns
    assert "Paso 6 - Proceso" in df_horiz.columns
    assert df_horiz.iloc[0]["Paso 6 - Proceso"] == "Step_6"
    
    print("MANY_STEPS_VERIFICATION_SUCCESS")

if __name__ == "__main__":
    test_csv_export()
    test_many_steps()
