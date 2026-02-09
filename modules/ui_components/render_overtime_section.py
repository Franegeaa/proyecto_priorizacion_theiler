import streamlit as st
from datetime import timedelta

def render_overtime_section(maquinas_activas, fecha_inicio_plan):
    """Manages overtime inputs and returns the dict of overtimes."""
    st.subheader("⏳ Horas Extras")
    
    start_of_week_plan = fecha_inicio_plan 
    dias_semana = []
    lista_dias_str = []
    map_str_date = {}
    
    for i in range(7):
        dia_actual = start_of_week_plan + timedelta(days=i)
        nombre = dia_actual.strftime('%A')
        label = f"{nombre} {dia_actual.strftime('%d/%m')}"
        dias_semana.append(dia_actual)
        lista_dias_str.append(label)
        map_str_date[label] = dia_actual # Key object for dictionary

    horas_extras_general = {}
    
    with st.expander("Planificar Horas Extras (por máquina)"):
        maquinas_con_extras = st.multiselect(
            "Seleccioná las máquinas que harán horas extras:",
            options=maquinas_activas, 
            default=[]
        )
        
        if maquinas_con_extras:
            st.markdown("---")
            for maq in maquinas_con_extras:
                st.markdown(f"#### 🏭 {maq}")
                
                dias_sel_maq = st.multiselect(
                    f"Días de horas extras para {maq}:",
                    options=lista_dias_str,
                    default=[],
                    key=f"dias_he_{maq}"
                )
                
                horas_extras_maq = {}
                if dias_sel_maq:
                    cols_he = st.columns(len(dias_sel_maq)) if len(dias_sel_maq) <= 4 else st.columns(4)
                    
                    for idx, dia_label in enumerate(dias_sel_maq):
                        col_obj = cols_he[idx % 4]
                        fecha_obj = map_str_date[dia_label]
                        
                        with col_obj:
                            horas = st.number_input(
                                f"{dia_label} ({maq})",
                                min_value=0.0, 
                                max_value=24.0, 
                                value=2.0, 
                                step=0.5,
                                label_visibility="collapsed",
                                key=f"he_{maq}_{fecha_obj}"
                            )
                            st.caption(f"{dia_label}")
                            
                            if horas > 0:
                                horas_extras_maq[fecha_obj] = horas
                
                if horas_extras_maq:
                    horas_extras_general[maq] = horas_extras_maq
                st.markdown("---")

        if horas_extras_general:
             st.info(f"Se han configurado horas extras para {len(horas_extras_general)} máquinas.")

    return horas_extras_general
