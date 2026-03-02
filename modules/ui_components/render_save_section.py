import streamlit as st

def render_save_section(pm):
    """
    Renders the section to save the current schedule and overrides to the database.
    """
    if st.button("💾 Guardar Planificación Actual", help="Guarda la asignación de máquinas actual en la base de datos para que sea respetada mañana.", key="save_current_plan_btn"):
        st.session_state["_confirm_save"] = True

    if st.session_state.get("_confirm_save", False):
        st.warning("⚠️ **Antes de guardar**, asegurate de haber descargado la planificación en Excel. Una vez guardada, se sobreescribirá la anterior.")
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("✅ Ya descargué, guardar", key="confirm_save_yes"):
                st.session_state["_confirm_save"] = False
                if "last_schedule" in st.session_state and not st.session_state.last_schedule.empty:
                    if pm.connected:
                        pm.save_schedule(st.session_state.last_schedule)
                        if "manual_overrides" in st.session_state:
                            st.session_state.manual_overrides["manual_assignments"] = st.session_state.get("manual_assignments", {})
                        pm.save_manual_overrides(st.session_state.manual_overrides)
                        st.success("✅ Planificación y configuraciones guardadas exitosamente!")
                    else:
                        st.error("Error: conexión a BD no disponible.")
                else:
                    st.warning("⚠️ No hay una planificación generada para guardar.")
        with col_no:
            if st.button("❌ Cancelar", key="confirm_save_no"):
                st.session_state["_confirm_save"] = False
                st.rerun()
