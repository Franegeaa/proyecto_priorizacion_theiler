import sys, os
import pandas as pd
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from modules.schedulers.tasks import _procesos_pendientes_de_orden

cfg = {
    "orden_std": ["Guillotinado", "Impresión Offset", "Troquelado", "Barnizado", "Descartonado", "Pegado"]
}

row_flamenco = pd.Series({
    "OT_id": "FLAMENCO",
    "_PEN_Guillotina": True,
    "_PEN_ImpresionOffset": True,
    "_PEN_Barnizado": False,
    "_PEN_Troquelado": True,
    "ProcesoDpd": ""
})

print(_procesos_pendientes_de_orden(row_flamenco, cfg))
