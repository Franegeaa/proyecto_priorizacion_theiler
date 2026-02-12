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
                start_dt = pd.to_datetime(row.get("Inicio"))
                end_dt = pd.to_datetime(row.get("Fin"))
                
                row_data[f"{prefix} - Maquina"]       = row.get("ID Maquina", "")
                
                if pd.notna(start_dt):
                    row_data[f"{prefix} - Fecha Inicio"]  = start_dt.date()
                    row_data[f"{prefix} - Hora Inicio"]   = start_dt.strftime("%H:%M")
                else:
                    row_data[f"{prefix} - Fecha Inicio"]  = ""
                    row_data[f"{prefix} - Hora Inicio"]   = ""

                if pd.notna(end_dt):
                    row_data[f"{prefix} - Fecha Fin"]     = end_dt.date()
                    row_data[f"{prefix} - Hora Fin"]      = end_dt.strftime("%H:%M")
                else:
                    row_data[f"{prefix} - Fecha Fin"]     = ""
                    row_data[f"{prefix} - Hora Fin"]      = ""
                
                row_data[f"{prefix} - Duracion"]      = row.get("Duracion_h", 0)
                row_data[f"{prefix} - Prioridad"]     = row.get("ManualPriority", "")
            else:
                # Celdas vacías si no hay proceso
                row_data[f"{prefix} - Maquina"]       = ""
                row_data[f"{prefix} - Fecha Inicio"]  = ""
                row_data[f"{prefix} - Hora Inicio"]   = ""
                row_data[f"{prefix} - Fecha Fin"]     = ""
                row_data[f"{prefix} - Hora Fin"]      = ""
                row_data[f"{prefix} - Duracion"]      = ""
                row_data[f"{prefix} - Prioridad"]     = ""
        
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

import xlwt
from datetime import date, datetime

def generar_excel_ot_bytes(schedule):
    """Genera el archivo Excel solo con la hoja 'Plan por OT' en formato .xls (Excel 97-2003)."""
    
    # Obtenemos el DataFrame horizontal
    df_ot_horiz = generar_excel_ot_horizontal(schedule)
    
    buf_ot = BytesIO()
    
    try:
        # Pandas ya no soporta 'xlwt' como engine nativo en versiones recientes.
        # Usamos xlwt manualmente.
        book = xlwt.Workbook(encoding='utf-8')
        sheet = book.add_sheet("Plan por OT")
        
        if df_ot_horiz.empty:
             sheet.write(0, 0, "No hay datos")
        else:
            # 1. Escribir encabezados
            columns = df_ot_horiz.columns.tolist()
            style_header = xlwt.easyxf('font: bold on; align: horiz center')
            
            for col_idx, col_name in enumerate(columns):
                sheet.write(0, col_idx, col_name, style_header)
                
            # 2. Escribir datos
            # Estilo para fechas
            style_date = xlwt.XFStyle()
            style_date.num_format_str = 'DD/MM/YYYY'
            
            style_time = xlwt.XFStyle()
            style_time.num_format_str = 'HH:MM'
            
            for row_idx, row in df_ot_horiz.iterrows():
                # row_idx es el indice del df, pero para xlwt la fila es row_idx + 1 (header es 0)
                # Pero iterrows index puede no ser secuencial 0..N si filtramos.
                # Mejor usamos un contador manual.
                xls_row = row_idx + 1 if isinstance(row_idx, int) else 1 # Fallback, pero mejor enumerate abajo si iterrows no es confiable en orden.
                
            # Mejor iterar valores
            for r_idx, (index, row) in enumerate(df_ot_horiz.iterrows()):
                xls_r = r_idx + 1
                for c_idx, col_name in enumerate(columns):
                    val = row[col_name]
                    
                    # Manejo de tipos para xlwt
                    if isinstance(val, (date, datetime)):
                        # Si es NaT no escribimos nada o empty
                        if pd.isna(val):
                            sheet.write(xls_r, c_idx, "")
                        else:
                            # Detectar si es hora o fecha?
                            # El nombre de columna puede darnos pista o el tipo
                            if "Hora" in col_name and isinstance(val, (datetime, time)): # A veces string
                                # Si viene como string HH:MM lo dejamos string
                                sheet.write(xls_r, c_idx, val) 
                            else:
                                sheet.write(xls_r, c_idx, val, style_date)
                    elif pd.isna(val):
                        sheet.write(xls_r, c_idx, "")
                    else:
                        # Convertir a string si es necesario, o dejar int/float
                        sheet.write(xls_r, c_idx, val)
                        
        book.save(buf_ot)
        
    except Exception as e:
        # Fallback simple error txt
        # Pero devolvemos bytes
        buf_ot = BytesIO()
        book_err = xlwt.Workbook()
        sh_err = book_err.add_sheet("Error")
        sh_err.write(0, 0, f"Error generando XLS: {str(e)}")
        book_err.save(buf_ot)

    buf_ot.seek(0)
    return buf_ot, df_ot_horiz # Retornamos también el DF para el CSV o Debug

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
