import pandas as pd
data = [
    {"Cliente": "ESTANDAR", "_cliente_key": "estandar", "ManualPriority": 9999, "_priori_imp_num": 10.0, "Urgente": "No", "DueDate": pd.to_datetime("18/03/2026", dayfirst=True), "_troq_key": "troq1"},
    {"Cliente": "MOSTACHYS", "_cliente_key": "mostachys", "ManualPriority": 9999, "_priori_imp_num": 8.0, "Urgente": "No", "DueDate": pd.to_datetime("26/03/2026", dayfirst=True), "_troq_key": "troq2"}
]
df = pd.DataFrame(data)

grupos_todos = []
for keys, g in df.groupby(["_cliente_key", "_troq_key", "ManualPriority", "_priori_imp_num"], dropna=False):
    min_prio = g["ManualPriority"].min()
    due_min = g["DueDate"].min()
    es_urgente = False
    priori_imp_min = g["_priori_imp_num"].min()
    
    g_sorted = g.sort_values(["ManualPriority", "_priori_imp_num"], ascending=[True, True])
    grupos_todos.append((min_prio, priori_imp_min, not es_urgente, due_min, 0, keys[0], keys[1], g_sorted.to_dict("records")))

grupos_todos.sort()
print("Order after sort:")
for tup in grupos_todos:
    print(tup[5], "PrioImp:", tup[1], "Due:", tup[3])
