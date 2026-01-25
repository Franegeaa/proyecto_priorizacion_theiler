import pandas as pd
from modules.config_loader import es_si 
from .machines import elegir_maquina
from .priorities import _clave_prioridad_maquina


def _procesos_pendientes_de_orden(orden: pd.Series, orden_std=None):
    flujo = orden_std or [
        "Cortadora Bobina", "Guillotina", "Impresión Flexo", "Impresión Offset", "Barnizado",
        "OPP", "Stamping", "Plastificado", "Encapado", "Cuño","Troquelado", 
        "Descartonado", "Ventana", "Pegado"
    ]
    flujo = [p.strip() for p in flujo] 
    orden_idx = {p: i for i, p in enumerate(flujo)}
    pendientes = []
    
    # --- LÓGICA DE BLOQUEO POR FALTA DE FECHAS ---
    # Si PeliculaArt es Si, pero NO hay fecha llegada, se bloquea.
    # Si hay fecha, NO se bloquea (se agenda a futuro).
    tiene_pelicula = es_si(orden.get("PeliculaArt"))
    fecha_chapas = orden.get("FechaLlegadaChapas")
    # Es NaT o nulo/vacío?
    bloqueado_por_pelicula = tiene_pelicula and (pd.isna(fecha_chapas) or str(fecha_chapas).strip() == "")

    tiene_troquel = es_si(orden.get("TroquelArt"))
    fecha_troquel = orden.get("FechaLlegadaTroquel")
    bloqueado_por_troquel = tiene_troquel and (pd.isna(fecha_troquel) or str(fecha_troquel).strip() == "")

    if es_si(orden.get("CorteSNDdp")): pendientes.append("Cortadora Bobina")
    
    if es_si(orden.get("_PEN_Guillotina")): pendientes.append("Guillotina")
    # Impresión y posteriores bloqueados por Pelicula si falta fecha
    if es_si(orden.get("_PEN_ImpresionFlexo")) and not bloqueado_por_pelicula: pendientes.append("Impresión Flexo")
    if es_si(orden.get("_PEN_ImpresionOffset")) and not bloqueado_por_pelicula: pendientes.append("Impresión Offset") 
    if es_si(orden.get("_PEN_Barnizado")) and not bloqueado_por_pelicula: pendientes.append("Barnizado")
    if es_si(orden.get("_PEN_Stamping")) and not bloqueado_por_pelicula: pendientes.append("Stamping") 
    if es_si(orden.get("_PEN_Plastificado")) and not bloqueado_por_pelicula: pendientes.append("Plastificado")
    if es_si(orden.get("_PEN_Encapado")) and not bloqueado_por_pelicula: pendientes.append("Encapado")
    if es_si(orden.get("_PEN_Cuño")) and not bloqueado_por_pelicula: pendientes.append("Cuño")
    
    # Troquelado: Bloqueado por Pelicula (si falta fecha) O Troquel (si falta fecha)
    if es_si(orden.get("_PEN_Troquelado")) and not bloqueado_por_pelicula and not bloqueado_por_troquel: pendientes.append("Troquelado")
    
    # Posteriores a Troquel: Bloqueados por ambos
    if es_si(orden.get("_PEN_Descartonado")) and not bloqueado_por_pelicula and not bloqueado_por_troquel: pendientes.append("Descartonado")
    if es_si(orden.get("_PEN_Ventana")) and not bloqueado_por_pelicula and not bloqueado_por_troquel: pendientes.append("Ventana")
    if es_si(orden.get("_PEN_Pegado")) and not bloqueado_por_pelicula and not bloqueado_por_troquel: pendientes.append("Pegado")
    
    pendientes_limpios = [p.strip() for p in pendientes]
    pendientes_limpios = list(dict.fromkeys(pendientes))
    pendientes_limpios.sort(key=lambda p: orden_idx.get(p, 999))

    # --- REORDENAMIENTO POR FLAG '_TroqAntes' ---
    if es_si(orden.get("_TroqAntes")):
        # Mover Troquelado antes de Impresion (Flexo/Offset)
        # Estrategia: Buscar indices y mover elemento
        try:
            # Identificar items
            troq = next((p for p in pendientes_limpios if "Troquelado" in p), None)
            impres = [p for p in pendientes_limpios if "Impresi" in p] # Flexo u Offset
            
            if troq and impres:
                # Si existen ambos, poner Troquelado antes del primero de impresion
                idx_imp = min(pendientes_limpios.index(i) for i in impres)
                idx_troq = pendientes_limpios.index(troq)
                
                # Solo mover si Troquelado está despues de Impresion (lo normal)
                if idx_troq > idx_imp:
                    pendientes_limpios.pop(idx_troq)
                    pendientes_limpios.insert(idx_imp, troq)
        except:
            pass # Si falla algo raro, manter orden std
    
    return pendientes_limpios

def _expandir_tareas(df: pd.DataFrame, cfg):
    """Expande OTs en tareas individuales (una fila por proceso pendiente)."""
    tareas = []
    orden_std_limpio = [p.strip() for p in cfg.get("orden_std", [])]

    # --- MANUAL OVERRIDES ---
    overrides = cfg.get("manual_overrides", {})
    blacklist = overrides.get("blacklist_ots", set())
    priorities = overrides.get("manual_priorities", {})
    outsourced = overrides.get("outsourced_processes", set())
    skipped = overrides.get("skipped_processes", set())

    for idx, row in df.iterrows():
        ot = f"{row['CodigoProducto']}-{row['Subcodigo']}"
        
        # 1. Blacklist Check
        if ot in blacklist:
            continue
            
        pendientes = _procesos_pendientes_de_orden(row, orden_std_limpio)

        if not pendientes:
            continue

        for proceso in pendientes:
            maquina = elegir_maquina(proceso, row, cfg, None) # Asignación inicial simple
            
            # --- Check Outsourced/Skipped/Priority ---
            str_ot = str(ot)
            str_proc = str(proceso)
            str_maq = str(maquina)
            
            key_proc = (str_ot, str_proc)
            
            is_outsourced = key_proc in outsourced
            is_skipped = key_proc in skipped
            
            # Override Machine Name if Outsourced/Skipped to allow special handling
            if is_skipped:
                maquina = "SALTADO"
            elif is_outsourced:
                maquina = "TERCERIZADO"
            
            # Manual Priority (check with ORIGINAL machine name or new one? Original makes sense for user input)
            # User selected "Imp. Offset 1" in UI. If we change it to TERCERIZADO, we lose that key.
            # But priority only matters if it stays internal. 
            # If Internal, check priority.
            manual_prio = 9999
            if not (is_outsourced or is_skipped):
                # Check for (OT, Machine)
                # We use the assigned machine 'maquina'
                # Note: 'elegir_maquina' might return generic; need to match what User sees (Specific Machine).
                # The user selects from valid machines. `elegir_maquina` returns one of those.
                key_prio = (str_ot, str_maq)
                manual_prio = priorities.get(key_prio, 9999)

            # Cálculo de pliegos
            cant_prod = float(row.get("CantidadProductos", row.get("CantidadPliegos", 0)) or 0)
            poses = float(row.get("Poses", 1) or 1)
            bocas = float(row.get("BocasTroquel", row.get("Boca1_ddp", 1)) or 1)
            if proceso.lower().startswith("impres")or proceso.lower().startswith("barniz"):
                # Impresión: usa poses
                pliegos = cant_prod / poses if poses > 0 else cant_prod

            elif "troquel" in proceso.lower():
                # TROQUELADO: SIEMPRE dividir cantidad por bocas
                pliegos = cant_prod / bocas if bocas > 0 else cant_prod
            else:
                # Procesos restantes
                pliegos = float(row.get("CantidadPliegos", cant_prod))

            tareas.append({
                "idx": idx, "OT_id": ot, "CodigoProducto": row["CodigoProducto"], "Subcodigo": row["Subcodigo"],
                "Cliente": row["Cliente"], "Cliente-articulo": row.get("Cliente-articulo", ""),
                "Proceso": proceso, "Maquina": maquina,
                "DueDate": row["FechaEntrega"], "GroupKey": _clave_prioridad_maquina(proceso, row),
                "MateriaPrimaPlanta": row.get("MateriaPrimaPlanta", row.get("MPPlanta")),
                "MateriaPrima": row.get("MateriaPrima", ""), # Fix for priorities.py
                "CodigoTroquel": row.get("CodigoTroquel") or row.get("CodTroTapa") or row.get("CodTroCuerpo") or "",
                "Colores": row.get("Colores", ""), 
                "CantidadPliegos": pliegos,
                "CantidadPliegosNetos": row.get("CantidadPliegos"), 
                "Bocas": bocas, "Poses": poses,
                "TroquelArt": row.get("TroquelArt", ""),
                "PeliculaArt": row.get("PeliculaArt", ""),
                "FechaLlegadaChapas": row.get("FechaLlegadaChapas"), # Fecha disponiblidad Impresión
                "FechaLlegadaTroquel": row.get("FechaLlegadaTroquel"), # Fecha disponiblidad Troquel
                "PliAnc": row.get("PliAnc", 0),
                "PliLar": row.get("PliLar", 0),
                "Gramaje": row.get("Grs./Nº", 0), # Nuevo campo para agrupamiento Bobina
                "Urgente": es_si(row.get("Urgente", False)), # Nueva bandera de urgencia
                "_TroqAntes": es_si(row.get("_TroqAntes", False)), # <--- NUEVO FLAG
                "_PEN_ImpresionFlexo": row.get("_PEN_ImpresionFlexo"),
                "_PEN_ImpresionOffset": row.get("_PEN_ImpresionOffset"),
                "ProcesoDpd": row.get("ProcesoDpd", ""), # ProcesoDpd para reordenamiento dinámico
                
                # Manual Override Params
                "ManualPriority": manual_prio,
                "IsOutsourced": is_outsourced,
                "IsSkipped": is_skipped
            })  

    tasks = pd.DataFrame(tareas)
    tasks.drop_duplicates(subset=["OT_id", "Proceso"], inplace=True)
    
    if not tasks.empty:
        tasks["DueDate"] = pd.to_datetime(tasks["DueDate"], dayfirst=True, errors="coerce")
        if "orden_std" in cfg:
            orden_map = {p: i for i, p in enumerate(orden_std_limpio, start=1)}
            tasks["_orden_proceso"] = tasks["Proceso"].map(orden_map).fillna(9999)
            tasks.sort_values(["OT_id", "_orden_proceso"], inplace=True)

    return tasks
