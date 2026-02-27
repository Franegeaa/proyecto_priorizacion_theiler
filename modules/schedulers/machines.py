import pandas as pd

def elegir_maquina(proceso, orden, cfg, plan_actual=None):
    proc_lower = proceso.lower().strip()
    # Filtro basico por nombre de proceso
    # spliteamos para tomar "Impresión" de "Impresión Flexo" o "Troquelado" de "Troquelado"
    candidatos_df = cfg["maquinas"][cfg["maquinas"]["Proceso"].str.lower().str.contains(proc_lower.split()[0])]
    candidatos = candidatos_df["Maquina"].tolist()
    
    if not candidatos:
        return None

    # Lógica Específica por Tipo de Proceso
    
    # 1. Troquelado: Validar dimensiones (CRÍTICO)
    if "troquel" in proc_lower:
        anc = float(orden.get("PliAnc", 0) or 0)
        lar = float(orden.get("PliLar", 0) or 0)
        
        # Buscar primer candidato que soporte las medidas
        for cand in candidatos:
            if validar_medidas_troquel(cand, anc, lar):
                return cand
        
        # Si ninguno soporta, retornamos el primero por defecto (aunque sea inválido)
        # Esto sucede si el usuario desactivó las máquinas válidas o la OT es gigante.
        return candidatos[0]

    # 2. Impresión: Distinguir Flexo vs Offset por material
    if "impresión" in proc_lower or "impresion" in proc_lower:
        mat = str(orden.get("MateriaPrima", "")).lower()
        if "flexo" in proc_lower and ("micro" in mat or "carton" in mat):
            flexos = [m for m in candidatos if "flexo" in m.lower()]
            return flexos[0] if flexos else candidatos[0]
        if "offset" in proc_lower and ("cartulin" in mat or "papel" in mat):
            offsets = [m for m in candidatos if "heidel" in m.lower()]
            return offsets[0] if offsets else candidatos[0]

    # 3. Ventana
    if "ventan" in proc_lower:
        vent = [m for m in candidatos if "ventan" in m.lower()]
        return vent[0] if vent else candidatos[0]

    # 4. Pegado
    if "peg" in proc_lower:
        pegs = [m for m in candidatos if "peg" in m.lower() or "pegad" in m.lower()]
        return pegs[0] if pegs else candidatos[0]

    # 5. Descartonado (Typo fix: "descartonad" simple)
    if "descartonad" in proc_lower:
        descs = [m for m in candidatos if "descartonad" in m.lower()]
        if descs:
            return descs[0]

    # Default fallback
    return candidatos[0]

def validar_medidas_troquel(maquina, anc, lar):
    """Valida si un pliego entra en la máquina de troquelado."""
    # Normalizar nombre
    m = str(maquina).lower().strip()
    # Dimensiones de la tarea (CON ROTACIÓN)
    # Se compara el lado mayor del pliego con el lado mayor de la máquina
    # y el lado menor del pliego con el lado menor de la máquina.
    w_orig = float(anc or 0)
    l_orig = float(lar or 0)
    
    pliego_min = min(w_orig, l_orig)
    pliego_max = max(w_orig, l_orig)

    if "autom" in m or "duyan" in m:
        # Min 38x38 (Ambos lados deben ser >= 38)
        # Como es minimo, ambos lados deben superar 38, asi que da igual la rotación si min(pliego) >= 38
        mq_min, mq_max = 36, 40
        return pliego_min >= mq_min and pliego_max >= mq_max
    
    # Manuales: Maximos definidos (Ancho y Largo)
    
    # Manual 1 (Troq Nº 2 Ema): Max 80 x 105
    if "manual 1" in m or "manual1" in m or "ema" in m:
            # Maquina: 80x105 -> Min: 80, Max: 105
            mq_min, mq_max = 80, 105
            return pliego_min <= mq_min and pliego_max <= mq_max
    
    # Manual 2 (Troq Nº 1 Gus): Max 66 x 90
    # Maquina: 66x90 -> Min: 66, Max: 90
    if "manual 2" in m or "manual2" in m or "gus" in m:
            mq_min, mq_max = 66, 90
            return pliego_min <= mq_min and pliego_max <= mq_max
        
    # Manual 3: Max 70 x 100
    # Maquina: 70x100 -> Min: 70, Max: 100
    if "manual 3" in m or "manual3" in m:
            mq_min, mq_max = 70, 100
            return pliego_min <= mq_min and pliego_max <= mq_max
    
    # Iberica: Max 70 x 100
    #          Min 35 x 50
    # Maquina: 70x100 -> Min: 86, Max: 110
    if "iberica" in m:
        mq_min, mq_max, mq_min2, mq_max2 = 86, 110, 35, 50
        return (pliego_min <= mq_min and pliego_max <= mq_max) and (pliego_min >= mq_min2 and pliego_max >= mq_max2)
    
    return True # Por defecto si no matchea nombre

def get_machine_process_order(maquina, cfg):
    """Devuelve una tupla (orden_proceso, orden_tipo) para ordenar máquinas."""
    proc_name = cfg["maquinas"].loc[cfg["maquinas"]["Maquina"] == maquina, "Proceso"]
    if proc_name.empty: return (999, 0)
    proc = proc_name.iloc[0]
    
    flujo_estandar = [p.strip() for p in cfg.get("orden_std", [])]
    
    base_order = 999
    for i, p in enumerate(flujo_estandar):
        if p.lower() in proc.lower(): 
            base_order = i
            break
    
    # Desempate: Manuales (0) van ANTES que Automáticas (1)
    if "troquel" in proc.lower():
        if "autom" in maquina.lower() or "duyan" in maquina.lower():
            return (base_order, 1)
        else:
            return (base_order, 0)
    
    return (base_order, 0)

def obtener_descripcion_rango(maquina):
    """Devuelve un string describiendo el rango válido de medidas para la máquina."""
    m = str(maquina).lower().strip()
    
    if "autom" in m or "duyan" in m:
         return "Min: 36x40 cm"
    
    if "manual 1" in m or "manual1" in m or "ema" in m:
        return "Max: 80x105 cm"

    if "manual 2" in m or "manual2" in m or "gus" in m:
        return "Max: 66x90 cm"
        
    if "manual 3" in m or "manual3" in m:
        return "Max: 70x100 cm"
    
    if "iberica" in m:
       return "Min: 35x50 cm, Max: 86x110 cm"
       
    return "Sin restricciones de medidas conocidas"
