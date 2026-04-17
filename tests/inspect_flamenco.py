import sys
import os
import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from modules.utils.data_processor import process_unify_data

cfg_mock = {}
try:
    from modules.utils.config_loader import load_config_and_data
    cfg = load_config_and_data()
    df_ordenes = cfg['df_ordenes']
    
    flamenco = df_ordenes[df_ordenes['CodigoProducto'].astype(str).str.contains('FLAMENCO', case=False, na=False)]
    for idx, row in flamenco.iterrows():
        print(f"Producto: {row.get('CodigoProducto')} {row.get('Subcodigo')} - {row.get('Cliente-articulo')}")
        print(f"  PeliculaArt: {row.get('PeliculaArt')}")
        print(f"  FechaLlegadaChapas: {row.get('FechaLlegadaChapas')}")
        print(f"  TroquelArt: {row.get('TroquelArt')}")
        print(f"  FechaLlegadaTroquel: {row.get('FechaLlegadaTroquel')}")
        print(f"  ManualPriority: {row.get('ManualPriority')}")
        print(f"  Prioridad Imp: {row.get('PrioriImp')}")
        print(f"  Materia Prima: {row.get('MateriaPrimaPlanta')}")
        print("---")
except Exception as e:
    print("Error:", e)
    
