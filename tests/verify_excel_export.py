import pandas as pd
from io import BytesIO

# Mock function from app.py
def generar_excel_ot_horizontal(schedule_df):
    """
    Genera un DataFrame donde cada fila es una OT y los procesos se listan horizontalmente.
    """
    if schedule_df.empty:
        return pd.DataFrame()

    # 1. Copiamos y ordenamos cronológicamente por OT
    df_proc = schedule_df.copy()
    df_proc.sort_values(by=["OT_id", "Inicio"], inplace=True)

    # 2. Agrupamos por OT
    data_rows = []
    
    # Columnas fijas de la OT (tomamos la primera aparición)
    cols_estaticas = [
        "OT_id", "CodigoProducto", "Subcodigo", "Cliente", 
        "Cliente-articulo", "CantidadPliegos", "DueDate", 
        "Colores", "CodigoTroquel", "EnRiesgo", "Atraso_h"
    ]
    
    cols_estaticas = [c for c in cols_estaticas if c in df_proc.columns]

    for ot_id, grupo in df_proc.groupby("OT_id"):
        # Datos base de la fila
        row_data = grupo.iloc[0][cols_estaticas].to_dict()
        
        # Iteramos los procesos (pasos)
        for i, (idx, row) in enumerate(grupo.iterrows()):
            step_num = i + 1
            prefix = f"Paso {step_num}"
            
            row_data[f"{prefix} - Proceso"] = row.get("Proceso", "")
            row_data[f"{prefix} - Maquina"] = row.get("Maquina", "")
            row_data[f"{prefix} - Inicio"]  = row.get("Inicio", "")
            row_data[f"{prefix} - Fin"]     = row.get("Fin", "")
            row_data[f"{prefix} - Duracion"] = row.get("Duracion_h", 0)
        
        data_rows.append(row_data)

    # 3. Creamos el DF final
    df_horizontal = pd.DataFrame(data_rows)
    return df_horizontal

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
    
    # print("Testing with dataframe:")
    # print(df)
    
    result = generar_excel_ot_horizontal(df)
    
    # print("\nResult DataFrame:")
    # print(result)
    
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
