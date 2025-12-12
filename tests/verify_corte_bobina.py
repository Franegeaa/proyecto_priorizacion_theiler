
import pandas as pd
from modules.schedulers.tasks import _procesos_pendientes_de_orden, _expandir_tareas
from modules.config_loader import es_si

# Mock Config
cfg = {
    "orden_std": [
        "Corte de Bobina", "Guillotina", "Impresión Flexo", "Impresión Offset", "Barnizado",
        "OPP", "Stamping", "Plastificado", "Encapado", "Cuño","Troquelado", 
        "Descartonado", "Ventana", "Pegado"
    ],
    "maquinas": pd.DataFrame({
        "Maquina": ["Corte1"],
        "Proceso": ["Corte de Bobina"],
        "Capacidad_pliegos_hora": [1000],
        "Setup_base_min": [10],
        "Setup_menor_min": [5]
    }),
    "reglas": pd.DataFrame(),
    "feriados": set()
}

def test_corte_bobina_detection():
    print("--- Test: Corte de Bobina Detection ---")
    
    # Case 1: CorteSNDdp = 'Si'
    row_si = pd.Series({
        "CodigoProducto": "TEST", "Subcodigo": "01",
        "CorteSNDdp": "Si",
        "_PEN_Guillotina": "Si"
    })
    pendientes_si = _procesos_pendientes_de_orden(row_si, cfg["orden_std"])
    print(f"Input: CorteSNDdp='Si' -> Result: {pendientes_si}")
    assert "Corte de Bobina" in pendientes_si
    assert pendientes_si[0] == "Corte de Bobina", "Corte de Bobina should be first"

    # Case 2: CorteSNDdp = 'VERDADERO'
    row_verdadero = pd.Series({
        "CodigoProducto": "TEST", "Subcodigo": "02",
        "CorteSNDdp": "VERDADERO",
        "_PEN_Guillotina": "Si"
    })
    pendientes_verdadero = _procesos_pendientes_de_orden(row_verdadero, cfg["orden_std"])
    print(f"Input: CorteSNDdp='VERDADERO' -> Result: {pendientes_verdadero}")
    assert "Corte de Bobina" in pendientes_verdadero
    
    # Case 3: CorteSNDdp = 'No'
    row_no = pd.Series({
        "CodigoProducto": "TEST", "Subcodigo": "03",
        "CorteSNDdp": "No",
        "_PEN_Guillotina": "Si"
    })
    pendientes_no = _procesos_pendientes_de_orden(row_no, cfg["orden_std"])
    print(f"Input: CorteSNDdp='No' -> Result: {pendientes_no}")
    assert "Corte de Bobina" not in pendientes_no
    
    # Case 4: CorteSNDdp = 'FALSO'
    row_falso = pd.Series({
        "CodigoProducto": "TEST", "Subcodigo": "04",
        "CorteSNDdp": "FALSO",
        "_PEN_Guillotina": "Si"
    })
    pendientes_falso = _procesos_pendientes_de_orden(row_falso, cfg["orden_std"])
    print(f"Input: CorteSNDdp='FALSO' -> Result: {pendientes_falso}")
    assert "Corte de Bobina" not in pendientes_falso

    print("ALL TESTS PASSED")

if __name__ == "__main__":
    try:
        test_corte_bobina_detection()
    except AssertionError as e:
        print(f"TEST FAILED: {e}")
    except Exception as e:
        print(f"ERROR: {e}")
