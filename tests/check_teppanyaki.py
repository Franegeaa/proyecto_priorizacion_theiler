import pandas as pd
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from modules.utils.data_processor import process_uploaded_dataframe

def test_it():
    df = pd.read_excel('FormIAConsulta1a (6).xlsx', engine='openpyxl')
    df = process_uploaded_dataframe(df)
    
    # Buscar TEPPANYAKI
    tep = df[df["Cliente-articulo"].astype(str).str.contains("TEPPANYAKI", case=False, na=False)]
    if tep.empty:
        print("No se encontro TEPPANYAKI")
        return
    
    print("Found TEPPANYAKI!")
    print("Materia Prima / Tipo:", tep["MateriaPrima"].iloc[0])
    print("PEN_Stamping:", tep["_PEN_Stamping"].iloc[0])
    print("PEN_Plastificado:", tep["_PEN_Plastificado"].iloc[0])
    print("PEN_Barnizado:", tep["_PEN_Barnizado"].iloc[0])
    print("PEN_Encapado:", tep["_PEN_Encapado"].iloc[0])
    
if __name__ == '__main__':
    test_it()
