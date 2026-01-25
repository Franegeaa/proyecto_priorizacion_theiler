import pandas as pd
import os

def generate_demo_dataframe(n_rows=None):
    """
    Loads the static demo data from the configuration folder.
    Ignores n_rows as it loads a fixed file.
    """
    # Path to the static file
    # Assuming the app is run from the root, so config is at 'config/'
    file_path = "config/FormIAConsulta1a 23-01-26.xlsx"
    
    if not os.path.exists(file_path):
        # Fallback if run from different dir, try to find it relative to this file
        base_dir = os.path.dirname(os.path.dirname(__file__))
        file_path = os.path.join(base_dir, "config", "FormIAConsulta1a 23-01-26.xlsx")
        
    if os.path.exists(file_path):
        try:
            df = pd.read_excel(file_path)
            # Ensure it mimics the structure expected by the app if needed, 
            # but usually the file provided is the exact source.
            return df
        except Exception as e:
            print(f"Error loading demo file: {e}")
            return pd.DataFrame()
    else:
        print(f"Demo file not found at: {file_path}")
        return pd.DataFrame()
