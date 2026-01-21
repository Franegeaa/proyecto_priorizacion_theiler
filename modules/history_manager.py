import json
import pandas as pd
import os
import streamlit as st
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

HISTORY_FILE = "config/schedule_history.json"

def _get_gsheets_connection():
    """
    Returns the GSheets connection object if secrets are configured.
    Otherwise returns None.
    """
    try:
        # Check if secrets exist (rudimentary check)
        if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
            return st.connection("gsheets", type=GSheetsConnection)
    except Exception:
        pass
    return None

def save_history(schedule_df):
    """
    Saves the generated schedule.
    Priority: Google Sheets (if configured) -> Local JSON (fallback).
    """
    if schedule_df.empty:
        return

    # Convert dates to string for serialization compliance
    df_save = schedule_df.copy()
    for col in ["Inicio", "Fin", "DueDate"]:
        if col in df_save.columns:
            df_save[col] = df_save[col].astype(str)

    # 1. Try Google Sheets
    conn = _get_gsheets_connection()
    if conn:
        try:
            # Update the sheet (works like overwriting usually)
            conn.update(data=df_save)
            print("History saved to Google Sheets.")
            return
        except Exception as e:
            print(f"Error saving to Google Sheets: {e}")
            # Fallback to local
    
    # 2. Local JSON Fallback
    records = df_save.to_dict("records")
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
        print("History saved to local JSON.")
    except Exception as e:
        print(f"Error saving history locally: {e}")

def load_history():
    """
    Loads schedule history.
    Priority: Google Sheets -> Local JSON.
    Returns: DataFrame with parsed dates.
    """
    df = pd.DataFrame()
    
    # 1. Try Google Sheets
    conn = _get_gsheets_connection()
    if conn:
        try:
            # Read from sheet (TTL 0 ensures fresh data)
            df = conn.read(ttl=0)
            print("History loaded from Google Sheets.")
        except Exception as e:
            print(f"Error loading from Google Sheets: {e}")
            df = pd.DataFrame()

    # 2. Fallback to Local JSON if Sheet failed or returned empty (and we expected data?) 
    # Actually, if Sheet exists but is empty, it returns empty DF. 
    # Only fallback if conn was None or Error occurred.
    if df.empty and not conn: 
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data:
                    df = pd.DataFrame(data)
                print("History loaded from local JSON.")
            except Exception as e:
                print(f"Error loading local history: {e}")

    if df.empty:
        return pd.DataFrame()

    # Parse Dates
    for col in ["Inicio", "Fin", "DueDate"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
            
    return df

def get_frozen_tasks(current_date):
    """
    Analyzes history and returns:
    - strict_tasks: DataFrame of tasks scheduled for 'current_date' (Today).
                    Must be locked EXACTLY.
    - soft_tasks: DataFrame of tasks scheduled for 'current_date + 1' (Tomorrow).
                  Should be prioritized but movable by Urgent.
    
    Returns tuple (strict_df, soft_df, history_full_df)
    """
    history = load_history()
    if history.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    
    # Ensure current_date is a Date object
    if isinstance(current_date, datetime):
        current_date = current_date.date()
        
    next_day = current_date + pd.Timedelta(days=1)
    
    # Filter Strict (Today)
    # Tasks strictly intersecting Today (Starts Today OR Starts Before and Ends Today/After)
    # Basically: Ends >= Today AND Starts <= Today
    mask_strict = (history["Fin"].dt.date >= current_date) & (history["Inicio"].dt.date <= current_date)
    strict_df = history[mask_strict].copy()
    
    # Soft: Starts on next_day
    mask_soft = history["Inicio"].dt.date == next_day
    soft_df = history[mask_soft].copy()
    
    return strict_df, soft_df, history
