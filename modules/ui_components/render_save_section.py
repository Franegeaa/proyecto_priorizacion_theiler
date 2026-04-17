import streamlit as st


@st.dialog("💾 Guardar Planificación")
def _confirm_save_dialog(pm):
    st.warning("⚠️ **Antes de guardar**, asegurate de haber descargado la planificación en Excel. Una vez guardada, se sobreescribirá la anterior.")
    
    col_yes, col_no = st.columns(2)
    with col_yes:
        if st.button("✅ Ya descargué, guardar", width='stretch', key="confirm_save_yes"):
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
        if st.button("❌ Cancelar", width='stretch', key="confirm_save_no"):
            st.rerun()


def render_save_section(pm):
    """
    Renders the section to save the current schedule and overrides to the database.
    """
    if st.button("💾 Guardar Planificación Actual", help="Guarda la asignación de máquinas actual en la base de datos para que sea respetada mañana.", key="save_current_plan_btn"):
        _confirm_save_dialog(pm)
