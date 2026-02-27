import streamlit as st
from datetime import timedelta

def render_overtime_section(maquinas_activas, fecha_inicio_plan, persistence=None):
    """Manages overtime inputs and returns the dict of overtimes."""
    st.subheader("⏳ Horas Extras")
    
    # Initialize session state if not present (should be loaded in app.py, but safe guard here)
    if "overtime_config" not in st.session_state:
        st.session_state.overtime_config = {}

    start_of_week_plan = fecha_inicio_plan 
    dias_semana = []
    lista_dias_str = []
    map_str_date = {}
    
    for i in range(7):
        dia_actual = start_of_week_plan + timedelta(days=i)
        # Ensure date object for consistent keys
        dia_date = dia_actual.date() if hasattr(dia_actual, 'date') else dia_actual
        
        nombre = dia_actual.strftime('%A')
        label = f"{nombre} {dia_actual.strftime('%d/%m')}"
        dias_semana.append(dia_actual)
        lista_dias_str.append(label)
        map_str_date[label] = dia_date 

    # Helper function to save changes
    def save_changes():
        if persistence and persistence.connected:
            print(f"DEBUG: Saving Overtime Config: {st.session_state.overtime_config}")
            persistence.save_overtime(st.session_state.overtime_config)

    with st.expander("Planificar Horas Extras (por máquina)"):
        # Pre-select machines that already have overtime configured
        default_machines = [m for m in maquinas_activas if m in st.session_state.overtime_config and st.session_state.overtime_config[m]]
        
        maquinas_con_extras = st.multiselect(
            "Seleccioná las máquinas que harán horas extras:",
            options=maquinas_activas, 
            default=default_machines
        )
        
        if maquinas_con_extras:
            st.markdown("---")
            for maq in maquinas_con_extras:
                st.markdown(f"#### 🏭 {maq}")
                
                # Ensure dict exists for machine
                if maq not in st.session_state.overtime_config:
                     st.session_state.overtime_config[maq] = {}
                
                # Pre-select days that have overtime
                current_config = st.session_state.overtime_config[maq]
                default_days = [
                    label for label, d_obj in map_str_date.items() 
                    if d_obj in current_config and current_config[d_obj] > 0
                ]
                
                dias_sel_maq = st.multiselect(
                    f"Días de horas extras para {maq}:",
                    options=lista_dias_str,
                    default=default_days,
                    key=f"dias_he_{maq}"
                )
                
                # SYNC: Ensure config only has selected days
                selected_dates = {map_str_date[label] for label in dias_sel_maq}
                
                # 1. Remove days that were deselected
                current_keys = list(st.session_state.overtime_config[maq].keys())
                for d in current_keys:
                    if d not in selected_dates:
                        del st.session_state.overtime_config[maq][d]
                
                if dias_sel_maq:
                    cols_he = st.columns(len(dias_sel_maq)) if len(dias_sel_maq) <= 4 else st.columns(4)
                    
                    for idx, dia_label in enumerate(dias_sel_maq):
                        col_obj = cols_he[idx % 4]
                        fecha_obj = map_str_date[dia_label]
                        
                        # Get current value or default to 2.0
                        val = current_config.get(fecha_obj, 2.0)
                        
                        with col_obj:
                            new_horas = st.number_input(
                                f"{dia_label} ({maq})",
                                min_value=0.0, 
                                max_value=24.0, 
                                value=float(val), 
                                step=0.5,
                                label_visibility="collapsed",
                                key=f"he_{maq}_{fecha_obj}"
                            )
                            st.caption(f"{dia_label}")
                            
                            # Always update state (fixes bug where default 2.0 was never written)
                            st.session_state.overtime_config[maq][fecha_obj] = new_horas

                            
                            # Cleanup: If hours became 0 but user keeps day selected? 
                            # Logic here assumes >0 is meaningful. 
                            # If user sets to 0, we effectively "unset" it for logic, but keep in config if selected.
                
                else:
                    # If no days selected, clear config for this machine?
                    if st.session_state.overtime_config[maq]:
                         st.session_state.overtime_config[maq] = {}

                st.markdown("---")

        # Cleanup: Remove machines not in selection from config?
        for m in list(st.session_state.overtime_config.keys()):
            if m not in maquinas_con_extras and m in maquinas_activas: 
                 st.session_state.overtime_config[m] = {}

        if st.button("💾 Guardar Horas Extras"):
            save_changes()
            st.success("Configuración de horas extras guardada.")
            st.rerun()

        # --- Mostrar configuración guardada en la BD ---
        saved_config = st.session_state.overtime_config
        has_saved = any(
            d_dict and any(h > 0 for h in d_dict.values())
            for d_dict in saved_config.values()
        )
        
        if has_saved:
            st.markdown("##### 📋 Configuración Actual (cargada de BD)")
            
            # Build display rows
            rows_display = []
            for maq_name, dates_dict in sorted(saved_config.items()):
                for d_obj, hours in sorted(dates_dict.items()):
                    if hours > 0:
                        d_str = d_obj.strftime("%A %d/%m") if hasattr(d_obj, "strftime") else str(d_obj)
                        rows_display.append({
                            "Máquina": maq_name,
                            "Día": d_str,
                            "Horas Extra": hours
                        })
            
            if rows_display:
                import pandas as pd
                st.dataframe(
                    pd.DataFrame(rows_display),
                    hide_index=True,
                    use_container_width=True
                )
            
            if st.button("🗑️ Limpiar TODAS las horas extras guardadas", type="secondary"):
                st.session_state.overtime_config = {}
                if persistence and persistence.connected:
                    persistence.save_overtime({})
                st.success("Se eliminaron todas las horas extras.")
                st.rerun()


    # Filter out empty entries for return
    final_overtime = {
        m: {d: h for d, h in config.items() if h > 0} 
        for m, config in st.session_state.overtime_config.items()
        if config and any(h > 0 for h in config.values())
    }
    
    if final_overtime:
         st.info(f"Se han configurado horas extras para {len(final_overtime)} máquinas.")

    return final_overtime
