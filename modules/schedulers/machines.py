import pandas as pd

def elegir_maquina(proceso, orden, cfg, plan_actual=None):
    proc_lower = proceso.lower().strip()
    candidatos = cfg["maquinas"][cfg["maquinas"]["Proceso"].str.lower().str.contains(proc_lower.split()[0])]["Maquina"].tolist()
    if not candidatos:
        return None
    if "impresión" in proc_lower:
        mat = str(orden.get("MateriaPrima", "")).lower()
        if "flexo" in proc_lower and ("micro" in mat or "carton" in mat):
            flexos = [m for m in candidatos if "flexo" in m.lower()]
            return flexos[0] if flexos else candidatos[0]
        if "offset" in proc_lower and ("cartulin" in mat or "papel" in mat):
            offsets = [m for m in candidatos if "offset" in m.lower()]
            return offsets[0] if offsets else candidatos[0]
    if "ventan" in proc_lower:
        vent = [m for m in candidatos if "ventan" in m.lower()]
        return vent[0] if vent else candidatos[0]
    if "peg" in proc_lower:
        pegs = [m for m in candidatos if "peg" in m.lower() or "pegad" in m.lower()]
        return pegs[0] if pegs else candidatos[0]
    if "descartonad in" in proc_lower:
        descs = [m for m in candidatos if "descartonad" in m.lower()]
        if descs:
            return descs[0]
    return candidatos[0]
