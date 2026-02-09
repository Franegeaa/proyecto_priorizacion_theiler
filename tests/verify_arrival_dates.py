
import pandas as pd
import sys
import os
from datetime import datetime, time

# Add root to pythonpath
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.scheduler import programar
from modules.utils.config_loader import cargar_config

def test_arrival_dates():
    print("--- Test Start: Arrival Dates Verification ---")
    
    # 1. Mock Data
    # Caso 1: Impresión bloqueada por FechaLlegadaChapas (PeliculaArt=Si)
    # Caso 2: Troquelado bloqueado por FechaLlegadaTroquel (TroquelArt=Si)
    
    data = [
        {
            "CodigoProducto": "TEST1", "Subcodigo": "01", "Cliente": "C1", "FechaEntrega": "20/12/2025",
            "CantidadPliegos": 5000, "MateriaPrimaPlanta": "No", "MPPlanta": "No",
            "MateriaPrima": "Cartulina", # Offset
            "_PEN_ImpresionOffset": "Si", # Internal flag needed
            "_PEN_Troquelado": "No",
            "PeliculaArt": "Si", 
            "FechaChaDpv": "12-dic-25",
        },
        {
            "CodigoProducto": "TEST2", "Subcodigo": "01", "Cliente": "C2", "FechaEntrega": "20/12/2025",
            "CantidadPliegos": 5000, "MateriaPrimaPlanta": "No", "MPPlanta": "No",
            "ImpresionSND": "No", 
            "TroqueladoSND": "Si", # Pending Troquelado
            "TroquelArt": "Si",    # Has constraint
            "FechaTroDpv": "15-dic-25", # Arrives Dec 15
             "MateriaPrima": "Cartulina",
             "_PEN_Troquelado": "Si", # Internal flag
             "_PEN_ImpresionOffset": "No"
        }
    ]
    
    df = pd.DataFrame(data)
    
    # 2. Simulate App preprocessing (renaming + parsing)
    # Copied logic from app.py modification
    df.rename(columns={
        "FechaChaDpv": "FechaLlegadaChapas",
        "FechaTroDpv": "FechaLlegadaTroquel"
    }, inplace=True)
    
    def parse_spanish_date(date_str):
        if pd.isna(date_str) or str(date_str).strip() == "": return pd.NaT
        s = str(date_str).lower().strip()
        meses = {"ene": "01", "feb": "02", "mar": "03", "abr": "04", "may": "05", "jun": "06",
                 "jul": "07", "ago": "08", "sep": "09", "oct": "10", "nov": "11", "dic": "12"}
        for mes_name, mes_num in meses.items():
            if mes_name in s:
                s = s.replace(mes_name, mes_num); break
        s = s.replace("-", "/").replace(".", "/")
        return pd.to_datetime(s, dayfirst=True)

    df["FechaLlegadaChapas"] = df["FechaLlegadaChapas"].apply(parse_spanish_date)
    df["FechaLlegadaTroquel"] = df["FechaLlegadaTroquel"].apply(parse_spanish_date)
    
    if "TroquelArt" in df.columns:
        df["TroquelArt"] = df["TroquelArt"].fillna("").astype(str)

    
    # 3. Validation of parsing
    print("\nParsed Data:")
    print(df[["CodigoProducto", "FechaLlegadaChapas", "FechaLlegadaTroquel"]])
    with open("df_dump.txt", "w") as f:
        f.write(df.to_string())
    
    if "TroquelArt" in df.columns:
        print("TroquelArt Column:\n", df["TroquelArt"])
    else:
        print("TroquelArt Missing!")
    
    d1 = df.iloc[0]["FechaLlegadaChapas"]
    assert d1.day == 12 and d1.month == 12, "Parsing Failed for Chapas"
    d2 = df.iloc[1]["FechaLlegadaTroquel"]
    assert d2.day == 15 and d2.month == 12, "Parsing Failed for Troquel"

    # 4. Run Scheduler
    # Start date BEFORE arrival dates (e.g., Dec 10)
    start_date = datetime(2025, 12, 10).date()
    cfg = cargar_config("config/Config_Priorizacion_Theiler.xlsx")
    
    schedule, _, _, _ = programar(df, cfg, start=start_date, start_time=time(7,0)) # Pass start_time explicitly
    
    # 5. Verify Schedule
    print("\nGenerated Schedule:")
    # Filter only our test tasks
    res = schedule[schedule["OT_id"].str.contains("TEST")]
    print(res[["OT_id", "Proceso", "Inicio", "Fin", "Maquina"]])
    
    # Check TEST1 (Impresion) starts >= Dec 12
    t1 = res[res["OT_id"] == "TEST1-01"]
    if t1.empty:
        print("FAIL: TEST1 not scheduled!")
    else:
        start_t1 = t1.iloc[0]["Inicio"]
        print(f"TEST1 Start: {start_t1} (Should be >= 2025-12-12)")
        if start_t1 >= datetime(2025, 12, 12, 7, 0):
            print("PASS: TEST1 scheduled after arrival.")
        else:
            print("FAIL: TEST1 scheduled too early!")

    # Check TEST2 (Troquelado) starts >= Dec 15
    t2 = res[res["OT_id"] == "TEST2-01"]
    if t2.empty:
        print("FAIL: TEST2 not scheduled!")
    else:
        start_t2 = t2.iloc[0]["Inicio"]
        print(f"TEST2 Start: {start_t2} (Should be >= 2025-12-15)")
        if start_t2 >= datetime(2025, 12, 15, 7, 0):
            print("PASS: TEST2 scheduled after arrival.")
        else:
            print("FAIL: TEST2 scheduled too early!")

if __name__ == "__main__":
    test_arrival_dates()
