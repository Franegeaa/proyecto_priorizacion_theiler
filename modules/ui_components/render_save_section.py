import streamlit as st

def render_save_section(pm):
    """
    Renders the section to save the current schedule and overrides to the database.
    """
    if st.button("💾 Guardar Planificación Actual", help="Guarda la asignación de máquinas actual en la base de datos para que sea respetada mañana."):
        if "last_schedule" in st.session_state and not st.session_state.last_schedule.empty:
             if pm.connected:
                 pm.save_schedule(st.session_state.last_schedule)
                 # SAVE OVERRIDES ALSO
                 # Inject manual_assignments into overrides dict for saving
                 if "manual_overrides" in st.session_state:
                     st.session_state.manual_overrides["manual_assignments"] = st.session_state.get("manual_assignments", {})
                 
                 pm.save_manual_overrides(st.session_state.manual_overrides)
                 st.success("✅ Planificación y configuraciones guardadas exitosamente!")
             else:
                 st.error("Error: conexión a BD no disponible.")
        else:
             st.warning("⚠️ No hay una planificación generada para guardar.")
