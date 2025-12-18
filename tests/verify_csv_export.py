import pandas as pd
from io import BytesIO

# Mock logic
def generar_excel_ot_horizontal(schedule_df):
    if schedule_df.empty:
        return pd.DataFrame()
    df_proc = schedule_df.copy()
    df_proc.sort_values(by=["OT_id", "Inicio"], inplace=True)
    data_rows = []
    cols_estaticas = ["OT_id", "CodigoProducto"]
    cols_estaticas = [c for c in cols_estaticas if c in df_proc.columns]

    for ot_id, grupo in df_proc.groupby("OT_id"):
        row_data = grupo.iloc[0][cols_estaticas].to_dict()
        for i, (idx, row) in enumerate(grupo.iterrows()):
            step_num = i + 1
            prefix = f"Paso {step_num}"
            row_data[f"{prefix} - Proceso"] = row.get("Proceso", "")
        data_rows.append(row_data)
    return pd.DataFrame(data_rows)


def test_csv_export():
    data = {"OT_id": ["OT1"], "CodigoProducto": ["P1"], "Inicio": [1], "Proceso": ["Corte"]}
    df = pd.DataFrame(data)
    
    # Generate horizontal dataframe
    df_horiz = generar_excel_ot_horizontal(df)
    
    # Simulate CSV export
    csv_data = df_horiz.to_csv(index=False, sep=';', decimal=',')
    
    # print("CSV Data Preview:")
    # print(csv_data)
    
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
    
    print("Columns found:", df_horiz.columns.tolist())
    
    # Assert we have up to Paso 6
    assert "Paso 1 - Proceso" in df_horiz.columns
    assert "Paso 6 - Proceso" in df_horiz.columns
    assert df_horiz.iloc[0]["Paso 6 - Proceso"] == "Step_6"
    
    print("MANY_STEPS_VERIFICATION_SUCCESS")

if __name__ == "__main__":
    test_csv_export()
    test_many_steps()

