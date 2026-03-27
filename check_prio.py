import pandas as pd
df = pd.read_excel('FormIAConsulta1a (7).xlsx')
for idx, r in df.iterrows():
    articulo = str(r.get('Cliente-articulo', '')).upper()
    if 'MANJARES' in articulo or 'PORTEÑA' in articulo:
        print(f"Art: {articulo[:30]} | ManualPriority: {r.get('ManualPriority')} | PrioriImp: {r.get('PrioriImp')} | EstadoDdp: {r.get('EstadoDdp')}")
