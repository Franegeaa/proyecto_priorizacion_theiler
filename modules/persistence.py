import streamlit as st
import pandas as pd
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
        try:
            with self.engine.connect() as conn:
                conn.execute(text(create_table_query))
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
            df_save["scheduled_date"] = df_save["fecha_inicio"].dt.date
            df_save["last_updated"] = datetime.now()

            # Clean data types
            df_save["ot_id"] = df_save["ot_id"].astype(str)
            df_save["proceso"] = df_save["proceso"].astype(str)
            df_save["maquina"] = df_save["maquina"].astype(str)
            
            # Remove virtual machines that shouldn't lock
            virtuals = ["TERCERIZADO", "SALTADO", "POOL_DESCARTONADO"]
            df_save = df_save[~df_save["maquina"].isin(virtuals)]

            # Upsert logic is complex in pandas+alchemy directly.
            # Easiest way: Delete existing entries for these OTs and Insert new.
            # OR iterate and execute UPSERT.
            
            # Since we want to update the plan for these specific OTs, let's use a transaction.
            # Strategy: Temporary table or direct upsert loop.
            # Let's use direct execution with bind parameters for safety and upsert support.
            
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
                conn.execute(text(upsert_sql), records)
                conn.commit()
                
            logger.info(f"Saved {len(records)} assignments to history.")
            
        except Exception as e:
            logger.error(f"Failed to save schedule: {e}")
            st.warning(f"No se pudo guardar el historial: {e}")

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
                val = str(row[2]) # machine
                locked[key] = val
                
            return locked

        except Exception as e:
            logger.error(f"Failed to load history: {e}")
            return {}
