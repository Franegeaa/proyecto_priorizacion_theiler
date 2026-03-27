import pandas as pd
from datetime import datetime

try:
    df = pd.read_excel('input_form.xlsx', )
    for idx, r in df.iterrows():
        cliente = str(r.get('Cliente', '')).upper()
        if 'ESTANDAR' in cliente or 'MOSTACHYS' in cliente:
            print(f"Producto: {r.get('Cliente-articulo', '')[:30]} | Cliente: {cliente} | PrioriImp: {r.get('PrioriImp')} | FechaImDdp: {r.get('FechaImDdp')} | DueDate: {r.get('DueDate')} | Urgente: {r.get('Urgente')} | ManualPriority: {r.get('ManualPriority')}")
except Exception as e:
    print(e)
