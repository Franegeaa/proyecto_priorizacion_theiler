import pandas as pd
df = pd.read_excel('FormIAConsulta1a (7).xlsx')
print("Total rows:", len(df))
targets = df[df['ART/DDP'].astype(str).str.contains('PORTA HUEVO|PANCHE', case=False, na=False)]
print("Found targets:", len(targets))
for idx, r in targets.iterrows():
    print(f"OT: {r['ART/DDP'][:30]} | MP: {r.get('Mat/Prim1')} | Planta: {r.get('MPPlanta')}")
