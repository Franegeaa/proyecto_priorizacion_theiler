import pandas as pd
from io import BytesIO

def generar_excel_ot_horizontal(schedule_df):
    """
    Genera un DataFrame donde cada fila es una OT y los procesos se listan horizontalmente.
    Las columnas de procesos son FIJAS, existan o no en la OT.
    """
    if schedule_df.empty:
        return pd.DataFrame()

    # 1. Copiamos y ordenamos por OT para consistencia
    df_proc = schedule_df.copy()
    df_proc.sort_values(by=["OT_id", "Inicio"], inplace=True)

    # 2. Definimos la lista maestra de procesos en orden lógico
    PROCESS_ORDER = [
        "Cortadora Bobina", 
        "Guillotina", 
        "Impresión Flexo", 
        "Impresión Offset", 
        "Barnizado",
        "OPP",
        "Stamping", 
        "Plastificado", 
        "Encapado", 
        "Cuño",
        "Troquelado", 
        "Descartonado", 
        "Ventana", 
        "Pegado"
    ]
    
    # 3. Columnas fijas de la OT (Metadatos)
    cols_estaticas = [
        "OT_id", "CodigoProducto", "Subcodigo", "Cliente", 
        "Cliente-articulo", "CantidadPliegos", "DueDate", 
        "Colores", "CodigoTroquel", "EnRiesgo", "Atraso_h"
    ]
    cols_estaticas = [c for c in cols_estaticas if c in df_proc.columns]

    data_rows = []

    for ot_id, grupo in df_proc.groupby("OT_id"):
        # Datos base de la fila (de la primera aparición)
        row_data = grupo.iloc[0][cols_estaticas].to_dict()
        
        # Mapa de procesos de esta OT para acceso rápido
        # Usamos el nombre del proceso como clave. 
        # Si hubiera duplicados (mismo proceso 2 veces), tomamos el primero o el último?
        # Asumiremos el primero que aparece cronológicamente (ya que ordenamos por Inicio)
        proc_map = {}
        for idx, row in grupo.iterrows():
            p_name = str(row.get("Proceso", "")).strip()
            if p_name not in proc_map:
                proc_map[p_name] = row
        
        # Iteramos sobre la lista maestra para crear las columnas en orden
        for proc in PROCESS_ORDER:
            # Prefijo para encabezados
            prefix = proc
            
            # Datos del proceso si existe en esta OT
            row = proc_map.get(proc) 
            
            if row is not None:
                row_data[f"{prefix} - Maquina"]   = row.get("ID Maquina", "")
                row_data[f"{prefix} - Inicio"]    = row.get("Inicio", "")
                row_data[f"{prefix} - Fin"]       = row.get("Fin", "")
                row_data[f"{prefix} - Duracion"]  = row.get("Duracion_h", 0)
            else:
                # Celdas vacías si no hay proceso
                row_data[f"{prefix} - Maquina"]   = ""
                row_data[f"{prefix} - Inicio"]    = ""
                row_data[f"{prefix} - Fin"]       = ""
                row_data[f"{prefix} - Duracion"]  = ""
        
        data_rows.append(row_data)

    # 4. Creamos el DF final
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

def dataframe_to_excel_bytes(df, sheet_name="Datos"):
    """Convierte un DataFrame cualquiera a un archivo Excel en memoria."""
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name=sheet_name)
    buf.seek(0)
    return buf
