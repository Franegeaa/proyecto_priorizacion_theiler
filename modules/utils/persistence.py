import streamlit as st
import pandas as pd
import json
from datetime import date, datetime
import sqlalchemy
from sqlalchemy import create_engine, text
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PersistenceManager:
    def __init__(self):
        self.engine = None
        self.connected = False
        self._connect()

    def _connect(self):
        """Attempts to connect to PostgreSQL using st.secrets."""
        try:
            if "postgres" in st.secrets:
                # Construct connection string from secrets
                # Expected format in secrets.toml:
                # [postgres]
                # host = "..."
                # port = 5432
                # dbname = "..."
                # user = "..."
                # password = "..."
                
                # Check if it's a URL string or dict
                secrets = st.secrets["postgres"]
                if isinstance(secrets, str): # URL string
                    db_url = secrets
                elif "url" in secrets:
                    db_url = secrets["url"]
                else:
                    # Construct URL
                    db_url = f"postgresql://{secrets['user']}:{secrets['password']}@{secrets['host']}:{secrets['port']}/{secrets['dbname']}"
                
                self.engine = create_engine(db_url)
                self.connected = True
                logger.info("Connected to PostgreSQL successfully.")
                self.init_db()
            else:
                logger.warning("No 'postgres' secrets found. Persistence disabled.")
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            st.error(f"Error de conexión a Base de Datos de Historial: {e}")
            self.connected = False

    def init_db(self):
        """Creates the necessary table if it doesn't exist."""
        if not self.connected: return

        create_table_query = """
        CREATE TABLE IF NOT EXISTS schedule_history (
            ot_id TEXT,
            proceso TEXT,
            maquina TEXT,
            fecha_inicio TIMESTAMP,
            fecha_fin TIMESTAMP,
            scheduled_date DATE,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ot_id, proceso)
        );
        """

        create_table_overrides = """
        CREATE TABLE IF NOT EXISTS manual_overrides (
            override_key TEXT PRIMARY KEY,
            data_json TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        try:
            with self.engine.connect() as conn:
                conn.execute(text(create_table_query))
                conn.execute(text(create_table_overrides))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to init DB: {e}")
            st.error(f"Error inicializando tabla de historial: {e}")

    def save_schedule(self, df_schedule):
        """
        Saves the current schedule to the database.
        Upserts records based on (ot_id, proceso).
        """
        if not self.connected or df_schedule.empty: return

        try:
            # Prepare DataFrame for insertion
            # We want: ot_id, proceso, maquina, fecha_inicio, fecha_fin, scheduled_date
            
            # Filter valid rows
            df_save = df_schedule[["OT_id", "Proceso", "Maquina", "Inicio", "Fin"]].copy()
            df_save.columns = ["ot_id", "proceso", "maquina", "fecha_inicio", "fecha_fin"]
            
            # Add scheduled_date (the "Day" of the schedule, usually Inicio date)
            # Use 'today' as the scheduled_date because this is WHEN we planned it.
            # Using 'Inicio' might spread it across days, but the locking logic usually matches (OT, Proc).
            # Let's keep using 'Inicio' date as reference for now, or just 'Today'.
            df_save["scheduled_date"] = df_save["fecha_inicio"].dt.date
            df_save["last_updated"] = datetime.now()

            # Clean data types
            df_save["ot_id"] = df_save["ot_id"].astype(str)
            df_save["proceso"] = df_save["proceso"].astype(str)
            df_save["maquina"] = df_save["maquina"].astype(str)
            
            # Remove virtual machines that shouldn't lock
            virtuals = ["TERCERIZADO", "SALTADO", "POOL_DESCARTONADO"]
            df_save = df_save[~df_save["maquina"].isin(virtuals)]

            # Upsert logic
            upsert_sql = """
            INSERT INTO schedule_history (ot_id, proceso, maquina, fecha_inicio, fecha_fin, scheduled_date, last_updated)
            VALUES (:ot_id, :proceso, :maquina, :fecha_inicio, :fecha_fin, :scheduled_date, :last_updated)
            ON CONFLICT (ot_id, proceso) DO UPDATE SET
                maquina = EXCLUDED.maquina,
                fecha_inicio = EXCLUDED.fecha_inicio,
                fecha_fin = EXCLUDED.fecha_fin,
                scheduled_date = EXCLUDED.scheduled_date,
                last_updated = EXCLUDED.last_updated;
            """
            
            records = df_save.to_dict(orient="records")
            
            with self.engine.connect() as conn:
                if records:
                    conn.execute(text(upsert_sql), records)
                    conn.commit()
                
            logger.info(f"Saved {len(records)} assignments to history.")
            
        except Exception as e:
            logger.error(f"Failed to save schedule: {e}")
            st.warning(f"No se pudo guardar el historial: {e}")

    def save_manual_overrides(self, overrides):
        """
        Saves the manual overrides dictionary.
        Requires serialization of sets and tuple keys.
        Structure of overrides:
          - blacklist_ots: set
          - manual_priorities: dict {(ot, maq): int}
          - outsourced_processes: set (ot, proc)
          - skipped_processes: set (ot, proc)
          - manual_assignments: dict {Machine: [OT, OT]}
        """
        if not self.connected or not overrides: return

        try:
            # 1. Blacklist (Set of strings) -> List
            blacklist = list(overrides.get("blacklist_ots", []))
            
            # 2. Priorities (Dict with Tuple keys) -> Dict with String keys "OT|MAQ"
            priorities_raw = overrides.get("manual_priorities", {})
            priorities_clean = {}
            for (ot, maq), val in priorities_raw.items():
                key_str = f"{ot}|{maq}"
                priorities_clean[key_str] = val
            
            # 3. Outsourced (Set of Tuples) -> List of Strings "OT|PROC"
            outsourced_raw = overrides.get("outsourced_processes", set())
            outsourced_clean = [f"{ot}|{proc}" for ot, proc in outsourced_raw]

            # 4. Skipped (Set of Tuples) -> List of Strings "OT|PROC"
            skipped_raw = overrides.get("skipped_processes", set())
            skipped_clean = [f"{ot}|{proc}" for ot, proc in skipped_raw]

            # Prepare for DB
            data_map = {
                "blacklist_ots": json.dumps(blacklist),
                "manual_priorities": json.dumps(priorities_clean),
                "outsourced_processes": json.dumps(outsourced_clean),
                "skipped_processes": json.dumps(skipped_clean),
                "manual_assignments": json.dumps(overrides.get("manual_assignments", {}))
            }

            # Debug Log
            logger.info(f"Saving manual_assignments: {overrides.get('manual_assignments', {})}")

            upsert_query = """
            INSERT INTO manual_overrides (override_key, data_json, last_updated)
            VALUES (:key, :data, :ts)
            ON CONFLICT (override_key) DO UPDATE SET
                data_json = EXCLUDED.data_json,
                last_updated = EXCLUDED.last_updated;
            """
            
            ts = datetime.now()
            with self.engine.connect() as conn:
                for k, v in data_map.items():
                    conn.execute(text(upsert_query), {"key": k, "data": v, "ts": ts})
                conn.commit()
            
            logger.info("Saved manual overrides.")

        except Exception as e:
            logger.error(f"Failed to save overrides: {e}")
            st.warning(f"No se pudieron guardar las configuraciones manuales: {e}")

    def load_manual_overrides(self):
        """
        Loads overrides and deserializes them into the expected python structures.
        Returns: dict (compatible with st.session_state.manual_overrides)
        """
        if not self.connected: 
            return {
                "blacklist_ots": set(),
                "manual_priorities": {},
                "outsourced_processes": set(),
                "skipped_processes": set()
            }

        try:
            query = "SELECT override_key, data_json FROM manual_overrides"
            with self.engine.connect() as conn:
                rows = conn.execute(text(query)).fetchall()
            
            raw_data = {row[0]: row[1] for row in rows}
            
            # Reconstruct
            
            # 1. Blacklist
            res_blacklist = set(json.loads(raw_data.get("blacklist_ots", "[]")))
            
            # 2. Priorities
            res_prio = {}
            prio_dict = json.loads(raw_data.get("manual_priorities", "{}"))
            for k, v in prio_dict.items():
                # k is "OT|MAQ"
                if "|" in k:
                    parts = k.split("|", 1) # Split only on first pipe just in case
                    res_prio[(parts[0], parts[1])] = v
            
            # 3. Outsourced
            res_outsourced = set()
            out_list = json.loads(raw_data.get("outsourced_processes", "[]"))
            for item in out_list:
                if "|" in item:
                    parts = item.split("|", 1)
                    res_outsourced.add((parts[0], parts[1]))

            # 4. Skipped
            res_skipped = set()
            skip_list = json.loads(raw_data.get("skipped_processes", "[]"))
            for item in skip_list:
                if "|" in item:
                    parts = item.split("|", 1)
                    res_skipped.add((parts[0], parts[1]))
            
            # 5. Manual Assignments
            res_assignments = json.loads(raw_data.get("manual_assignments", "{}"))
            
            return {
                "blacklist_ots": res_blacklist,
                "manual_priorities": res_prio,
                "outsourced_processes": res_outsourced,
                "outsourced_processes": res_outsourced,
                "skipped_processes": res_skipped,
                "manual_assignments": res_assignments
            }

        except Exception as e:
            logger.error(f"Failed to load overrides: {e}")
            return {
                "blacklist_ots": set(),
                "manual_priorities": {},
                "outsourced_processes": set(),
                "skipped_processes": set()
            }

    def get_locked_assignments(self, lookahead_days=0):
        """
        Retrieves assignments that should be locked.
        Context: We want to lock assignments that were planned for TODAY (or future) in the PAST.
        
        Actually, the logic is: "What did we say YESTERDAY that we would do TODAY?"
        
        So we allow any record in the DB to be a candidate for locking.
        BUT, maybe we only care about tasks that haven't been completed?
        We assume the DB holds the *latest* plan.
        
        Returns: Dict {(ot_id, proceso): maquina}
        """
        if not self.connected: return {}

        try:
            # Query all history
            # Ideally we could filter by date, but OTs might be late. 
            # If an OT is in the history, it means we planned it.
            # We should respect that plan unless the user explicitly changes it (handled via new inputs?)
            # For now, let's load everything.
            
            query = "SELECT ot_id, proceso, maquina FROM schedule_history"
            
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                rows = result.fetchall()
            
            locked = {}
            for row in rows:
                # row is (ot_id, proceso, maquina)
                key = (str(row[0]), str(row[1])) # (ot, proc)
                locked[key] = str(row[2])
            return locked

        except Exception as e:
            logger.error(f"Failed to load history: {e}")
            return {}

    def save_die_preferences(self, prefs):
        """
        Saves die preferences to the 'manual_overrides' table under key 'troquel_preferences'.
        """
        if not self.connected or not prefs: return

        try:
            ts = datetime.now()
            query = """
            INSERT INTO manual_overrides (override_key, data_json, last_updated)
            VALUES (:key, :data, :ts)
            ON CONFLICT (override_key) DO UPDATE SET
                data_json = EXCLUDED.data_json,
                last_updated = EXCLUDED.last_updated;
            """
            
            with self.engine.connect() as conn:
                conn.execute(
                    text(query), 
                    {"key": "troquel_preferences", "data": json.dumps(prefs), "ts": ts}
                )
                conn.commit()
            
            logger.info("Saved die preferences to DB.")
            return True

        except Exception as e:
            logger.error(f"Failed to save die preferences: {e}")
            st.warning(f"Error guardando preferencias en BD: {e}")
            return False

    def load_die_preferences(self):
        """
        Loads die preferences from DB.
        Returns: dict or None
        """
        if not self.connected: return None

        try:
            query = "SELECT data_json FROM manual_overrides WHERE override_key = 'troquel_preferences'"
            with self.engine.connect() as conn:
                result = conn.execute(text(query)).fetchone()
            
            if result and result[0]:
                return json.loads(result[0])
            return None

        except Exception as e:
            logger.error(f"Failed to load die preferences: {e}")
            return None

    def save_holidays(self, holidays_list):
        """
        Saves the list of holiday dates to 'manual_overrides' table under key 'feriados'.
        Dates are stored as a list of "YYYY-MM-DD" strings.
        """
        if not self.connected: return False

        try:
            # Convert [date(2025,12,25), ...] -> ["2025-12-25", ...]
            data_str_list = [d.strftime("%Y-%m-%d") for d in holidays_list]
            
            ts = datetime.now()
            query = """
            INSERT INTO manual_overrides (override_key, data_json, last_updated)
            VALUES (:key, :data, :ts)
            ON CONFLICT (override_key) DO UPDATE SET
                data_json = EXCLUDED.data_json,
                last_updated = EXCLUDED.last_updated;
            """
            
            with self.engine.connect() as conn:
                conn.execute(
                    text(query), 
                    {"key": "feriados", "data": json.dumps(data_str_list), "ts": ts}
                )
                conn.commit()
            
            logger.info(f"Saved {len(data_str_list)} holidays to DB.")
            return True

        except Exception as e:
            logger.error(f"Failed to save holidays: {e}")
            st.warning(f"Error guardando feriados en BD: {e}")
            return False

    def load_holidays(self):
        """
        Loads holidays from DB.
        Returns: list of datetime.date objects or []
        """
        if not self.connected: return []

        try:
            query = "SELECT data_json FROM manual_overrides WHERE override_key = 'feriados'"
            with self.engine.connect() as conn:
                result = conn.execute(text(query)).fetchone()
            
            if result and result[0]:
                date_strs = json.loads(result[0])
                # Convert ["2025-12-25", ...] -> [date(2025,12,25), ...]
                return [datetime.strptime(s, "%Y-%m-%d").date() for s in date_strs]
            return []

        except Exception as e:
            logger.error(f"Failed to load holidays: {e}")
            return []

    def save_downtimes(self, downtimes_list):
        """
        Saves the list of downtimes to 'manual_overrides' table under key 'downtimes'.
        Structure: List of dicts with 'maquina', 'start' (isoformat), 'end' (isoformat).
        """
        if not self.connected: return False

        try:
            # Serialize datetimes
            data_to_save = []
            for dt in downtimes_list:
                item = dt.copy()
                if isinstance(item.get("start"), datetime):
                    item["start"] = item["start"].isoformat()
                if isinstance(item.get("end"), datetime):
                    item["end"] = item["end"].isoformat()
                data_to_save.append(item)
            
            ts = datetime.now()
            query = """
            INSERT INTO manual_overrides (override_key, data_json, last_updated)
            VALUES (:key, :data, :ts)
            ON CONFLICT (override_key) DO UPDATE SET
                data_json = EXCLUDED.data_json,
                last_updated = EXCLUDED.last_updated;
            """
            
            with self.engine.connect() as conn:
                conn.execute(
                    text(query), 
                    {"key": "downtimes", "data": json.dumps(data_to_save), "ts": ts}
                )
                conn.commit()
            
            logger.info(f"Saved {len(downtimes_list)} downtimes to DB.")
            return True

        except Exception as e:
            logger.error(f"Failed to save downtimes: {e}")
            st.warning(f"Error guardando paros en BD: {e}")
            return False

    def load_downtimes(self):
        """
        Loads downtimes from DB.
        Returns: list of dicts with 'start' and 'end' converted back to datetime objects.
        """
        if not self.connected: return []

        try:
            query = "SELECT data_json FROM manual_overrides WHERE override_key = 'downtimes'"
            with self.engine.connect() as conn:
                result = conn.execute(text(query)).fetchone()
            
            if result and result[0]:
                raw_list = json.loads(result[0])
                # Convert ISO strings back to datetime
                cleaned_list = []
                for item in raw_list:
                    if "start" in item:
                        item["start"] = datetime.fromisoformat(item["start"])
                    if "end" in item:
                        item["end"] = datetime.fromisoformat(item["end"])
                    cleaned_list.append(item)
                return cleaned_list
            return []

        except Exception as e:
            logger.error(f"Failed to load downtimes: {e}")
            return []
