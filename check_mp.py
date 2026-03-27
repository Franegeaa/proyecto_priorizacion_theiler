import pandas as pd
df = pd.read_excel('FormIAConsulta1a (7).xlsx')
for idx, r in df.iterrows():
    articulo = str(r.get('ART/DDP', '')).upper()
    if 'PORTA HUEVO' in articulo or 'PANCHE' in articulo:
        print(f"Art: {articulo[:30]} | MP: {r.get('Mat/Prim1')} | MPPlanta: {r.get('MPPlanta')}")
