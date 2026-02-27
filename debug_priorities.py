import json
from sqlalchemy import create_engine, text

import json
import toml
# Read secrets manually to connect to DB
try:
    with open(".streamlit/secrets.toml", "r") as f:
        secrets = toml.load(f)["postgres"]
    
    db_url = f"postgresql://{secrets['user']}:{secrets['password']}@{secrets['host']}:{secrets['port']}/{secrets['dbname']}"
    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        res = conn.execute(text("SELECT data_json FROM manual_overrides WHERE override_key='manual_assignments'")).fetchone()
        if res:
            assignments = json.loads(res[0])
            print("--- MANUAL ASSIGNMENTS ---")
            for maq, ots in assignments.items():
                if "E7493-2025101" in ots:
                    print(f"OT E7493-2025101 is explicitly assigned to {maq} via arrow buttons!")
                if "E7442-3047112" in ots:
                    print(f"OT E7442-3047112 is explicitly assigned to {maq} via arrow buttons!")
            print(f"Total manual assignments: {sum(len(v) for v in assignments.values())}")
        else:
            print("No manual assignments found")
except Exception as e:
    print(f"Error: {e}")
