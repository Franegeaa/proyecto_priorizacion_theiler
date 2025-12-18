import pandas as pd
from io import BytesIO

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
    # Ajustá estas columnas según lo que quieras mostrar fijo a la izquierda
    cols_estaticas = [
        "OT_id", "CodigoProducto", "Subcodigo", "Cliente", 
        "Cliente-articulo", "CantidadPliegos", "DueDate", 
        "Colores", "CodigoTroquel", "EnRiesgo", "Atraso_h"
    ]
    
    # Filtramos para que no explote si falta alguna columna
    cols_estaticas = [c for c in cols_estaticas if c in df_proc.columns]

    for ot_id, grupo in df_proc.groupby("OT_id"):
        # Datos base de la fila
        row_data = grupo.iloc[0][cols_estaticas].to_dict()
        
        # Iteramos los procesos (pasos)
        # paso 1, paso 2, paso 3...
        for i, (idx, row) in enumerate(grupo.iterrows()):
            step_num = i + 1
            prefix = f"Paso {step_num}"
            
            # Agregamos info del proceso
            row_data[f"{prefix} - Proceso"] = row.get("Proceso", "")
            row_data[f"{prefix} - Maquina"] = row.get("Maquina", "")
            row_data[f"{prefix} - Inicio"]  = row.get("Inicio", "")
            row_data[f"{prefix} - Fin"]     = row.get("Fin", "")
            row_data[f"{prefix} - Duracion"] = row.get("Duracion_h", 0)
        
        data_rows.append(row_data)

    # 3. Creamos el DF final
    df_horizontal = pd.DataFrame(data_rows)
    return df_horizontal

def generar_excel_bytes(schedule, resumen_ot, carga_md):
    """Genera el archivo Excel completo en memoria."""
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        # 1. Plan por Máquina
        if not schedule.empty:
            plan_por_maquina = schedule.copy()
            plan_por_maquina.sort_values(by=["Maquina", "Inicio"], inplace=True)
            
            cols_export = [
                "ID Maquina", "Maquina", "Inicio", "Fin", "Duracion_h", 
                "OT_id", "Cliente", "Cliente-articulo", "CodigoProducto", 
                "Proceso", "CantidadPliegos", "Colores", "CodigoTroquel", "DueDate"
            ]
            cols_final = [c for c in cols_export if c in plan_por_maquina.columns]
            
            plan_por_maquina[cols_final].to_excel(w, index=False, sheet_name="Plan por Máquina")
            
        # 2. Otras hojas
        schedule.to_excel(w, index=False, sheet_name="Datos Crudos (Schedule)") 
        if not resumen_ot.empty:
            resumen_ot.to_excel(w, index=False, sheet_name="Resumen por OT")
        if not carga_md.empty:
            carga_md.to_excel(w, index=False, sheet_name="Carga Máquina-Día")
            
    buf.seek(0)
    return buf

def generar_excel_ot_bytes(schedule):
    """Genera el archivo Excel solo con la hoja 'Plan por OT'."""
    buf_ot = BytesIO()
    with pd.ExcelWriter(buf_ot, engine="openpyxl") as w_ot:
        try:
            df_ot_horiz = generar_excel_ot_horizontal(schedule)
            if not df_ot_horiz.empty:
                df_ot_horiz.to_excel(w_ot, index=False, sheet_name="Plan por OT")
            else:
                pd.DataFrame({"Info": ["No hay datos"]}).to_excel(w_ot, sheet_name="Vacio")
        except Exception as e:
                pd.DataFrame({"Error": [str(e)]}).to_excel(w_ot, sheet_name="Error")
    
    buf_ot.seek(0)
    return buf_ot, df_ot_horiz # Retornamos también el DF para el CSV

def generar_csv_maquina_str(schedule):
    """Genera el CSV por máquina."""
    if schedule.empty:
        return ""
    
    plan_csv = schedule.copy()
    plan_csv.sort_values(by=["Maquina", "Inicio"], inplace=True)
    
    cols_export = [
        "ID Maquina", "Maquina", "CodigoProducto", "Subcodigo","Cliente", "Cliente-articulo", "Inicio", "Fin", "Duracion_h", 
        "Proceso", "CantidadPliegos", "Colores", "CodigoTroquel", "DueDate"
    ]
    cols_final = [c for c in cols_export if c in plan_csv.columns]
    
    return plan_csv[cols_final].to_csv(index=False, sep=';', decimal=',', encoding='utf-8-sig')

def generar_csv_ot_str(df_ot_horiz):
    """Genera el CSV por OT."""
    if df_ot_horiz.empty:
        return ""
    return df_ot_horiz.to_csv(index=False, sep=';', decimal=',', encoding='utf-8-sig')
