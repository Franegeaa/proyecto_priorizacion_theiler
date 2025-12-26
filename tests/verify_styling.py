import pandas as pd

def verify_styling():
    df = pd.DataFrame({
        "Maquina": ["M1", "M2"],
        "Horas Necesarias": [10.55, 20.123],
        "Horas Disponibles": [8.0, 24.0],
        "Balance": [-2.55, 3.877]
    })
    
    print("Testing DataFrame styling...")
    try:
        # Replicating the fix
        styler = df[["Maquina", "Horas Necesarias", "Horas Disponibles", "Balance"]].style.format({
            "Horas Necesarias": "{:.1f}", 
            "Horas Disponibles": "{:.1f}", 
            "Balance": "{:.1f}"
        })
        
        # Taking it a step further to ensure it renders (pandas render step)
        html = styler.to_html()
        print("Styling successful! Generated HTML length:", len(html))
        
    except Exception as e:
        print(f"FAILED: {e}")
        exit(1)

if __name__ == "__main__":
    verify_styling()
