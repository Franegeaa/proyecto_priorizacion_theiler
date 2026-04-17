import pandas as pd
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from modules.utils.data_processor import process_uploaded_dataframe

def test_it():
    df = pd.read_excel('FormIAConsulta1a (6).xlsx', engine='openpyxl')
    df = process_uploaded_dataframe(df)
    
    # Buscar TEPPANYAKI
    teps = df[df["Cliente-articulo"].astype(str).str.contains("TEPPANYAKI", case=False, na=False)]
    if teps.empty:
        print("No se encontro NINGUN TEPPANYAKI")
        return
        
    print(f"Me trajo {len(teps)} TEPPANYAKIs.")
    
    for i, tep in teps.iterrows():
        nombre = tep["Cliente-articulo"]
        if "TAPA" in nombre and "2 CARRILES" in nombre:
            print("=======================")
            print("Found EXACT TEPPANYAKI!")
            print("Nombre:", nombre)
            print("Materia Prima / Tipo:", tep["MateriaPrima"])
            print("PEN_Stamping:", tep["_PEN_Stamping"])
            print("PEN_Plastificado:", tep["_PEN_Plastificado"])
            print("PEN_Barnizado:", tep["_PEN_Barnizado"])
            print("PEN_Encapado:", tep["_PEN_Encapado"])
            print("PEN_Troquelado:", tep["_PEN_Troquelado"])
            print("Prioridad Imp:", tep.get("PrioriImp", "N/A"))
            print("Prioridad Troq:", tep.get("PrioriTr", "N/A"))
            print("Manual Priority:", tep.get("ManualPriority", "N/A"))
            
if __name__ == '__main__':
    test_it()
