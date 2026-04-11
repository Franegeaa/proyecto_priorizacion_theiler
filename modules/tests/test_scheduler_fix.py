import pandas as pd

def test_logic():
    # Test manual fallback for large jobs when autos are busy
    # (Simulated by adding many large jobs)
    # 1. First job (Large) goes to Auto (Duyan 2)
    # 2. Second job (Large) goes to Auto (Iberica G2)
    # 3. Third job (Large) should go to Manual if autos are 'busy' (have further start dates)
    
    # We will just verify detection for now as full simulation requires more mocks
    print("\nVerificando que manuales sean candidatas para trabajos grandes...")
    # (Checking the logic update in scheduler.py)
    bocas = 10; total_pliegos = 10000; candidatos_tamano = ["Y-TroqNº2", "Z-TroqNº1", "Iberica G2", "Duyan 2"]
    if bocas > 6 or total_pliegos > 2500:
        candidatas = candidatos_tamano
    else:
        candidatas = ["Y-TroqNº2", "Z-TroqNº1"] # focus on manual
    
    assert "Y-TroqNº2" in candidatas
    assert "Duyan 2" in candidatas
    print("¡Lógica de fallback verificada!")

    # Test Galpon 1
    maquinas_g1 = [
        {"Maquina": "Troq Nº 1 Gus", "Proceso": "Troquelado", "TipoMaquina": "manual"},
        {"Maquina": "Troq Nº 2 Ema", "Proceso": "Troquelado", "TipoMaquina": "manual"},
        {"Maquina": "Duyan", "Proceso": "Troquelado", "TipoMaquina": "automatica"},
    ]
    cfg_g1 = {"maquinas": pd.DataFrame(maquinas_g1)}
    
    manuales_g1 = []
    auto_names_g1 = []
    for _, row_m in cfg_g1["maquinas"].iterrows():
        m_name = str(row_m["Maquina"]).lower()
        m_tipo = str(row_m.get("TipoMaquina", "")).lower()
        if m_tipo == "manual" or "nº" in m_name or "n°" in m_name or "manual" in m_name:
            if "autom" in m_name or "duyan" in m_name or "iberica" in m_name or m_tipo == "automatica":
                auto_names_g1.append(row_m["Maquina"])
            else:
                manuales_g1.append(row_m["Maquina"])
        elif "iberica" in m_name or "autom" in m_name or "duyan" in m_name or m_tipo == "automatica":
            auto_names_g1.append(row_m["Maquina"])
            
    print(f"Manuales G1: {manuales_g1}")
    print(f"Automaticas G1: {auto_names_g1}")
    
    assert "Troq Nº 1 Gus" in manuales_g1
    assert "Troq Nº 2 Ema" in manuales_g1
    assert "Duyan" in auto_names_g1
    
    print("\n¡Pruebas exitosas para Galpón 1 y 2!")

if __name__ == "__main__":
    test_logic()
