import streamlit as st
import pandas as pd

from modules.utils.config_loader import calculate_business_hours

def render_delayed_orders_section(resumen_ot, schedule, cfg):
    """
    Renders a table of delayed orders (where Estimated Completion > Due Date).
    """
    st.subheader("⚠️ Órdenes Atrasadas")
    
    if resumen_ot.empty:
        st.info("No hay datos de planificación disponibles.")
        return

    # Filter delayed orders
    # "EnRiesgo" is already calculated in scheduler.py as (Fin_OT > DueDate + 18h buffer)
    # or strictly Fin_OT > DueDate?
    # In scheduler.py: resumen_ot["EnRiesgo"] = resumen_ot["Atraso_h"] > 0
    
    delayed_df = resumen_ot[resumen_ot["EnRiesgo"]].copy()
    
    if delayed_df.empty:
        st.success("🎉 ¡No hay órdenes atrasadas planificadas!")
        return
    
    # Select and format columns
    # Available in resumen_ot: OT_id, Cliente, Producto, Fin_OT, DueDate, Atraso_h, EnRiesgo
    cols_to_show = ["OT_id", "Producto", "DueDate", "Fin_OT", "Atraso_h"]
    display_df = delayed_df[cols_to_show].copy()
    display_df["Atraso_d"] = display_df["Atraso_h"] / 24.0
    
    # Rename for clearer display
    display_df = display_df[["OT_id", "Producto", "DueDate", "Fin_OT", "Atraso_d"]].rename(columns={
        "Producto": "Cliente - Artículo",
        "Fin_OT": "Fecha Estimada Entrega",
        "Atraso_d": "Días de Atraso",
        "DueDate": "Fecha Prometida"
    })
    
    # Sort by amount of delay (descending)
    display_df = display_df.sort_values("Días de Atraso", ascending=False)
    
    st.markdown(f"**Total de órdenes atrasadas:** {len(display_df)}")
    
    event = st.dataframe(
        display_df,
        column_config={
            "Fecha Prometida": st.column_config.DatetimeColumn(format="D/M HH:mm"),
            "Fecha Estimada Entrega": st.column_config.DatetimeColumn(format="D/M HH:mm"),
            "Días de Atraso": st.column_config.NumberColumn(format="%.1f d"),
        },
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row"
    )

    # --- BOTTLENECK ANALYSIS ---
    if event.selection and event.selection["rows"]:
        idx = event.selection["rows"][0]
        selected_row = display_df.iloc[idx]
        ot_id = selected_row["OT_id"]
        
        st.markdown(f"### 🕵️ Análisis de Cuellos de Botella: **{ot_id}**")
        
        # Filter schedule for this OT
        tasks = schedule[schedule["OT_id"] == ot_id].copy()
        
        if tasks.empty:
            st.warning("No se encontraron tareas planificadas para esta orden.")
            return

        # Sort by actual start time
        tasks = tasks.sort_values("Inicio")
        
        # Calculate Wait Times
        # We need to know when the previous task ended to calculate wait for current task.
        bottlenecks = []
        prev_end = None
        
        # Also need 'Plan Start' to calculate wait for first task? 
        # Usually first task wait is TimeNow -> Start.
        
        for i, row in tasks.iterrows():
            proc = row["Proceso"]
            start = row["Inicio"]
            end = row["Fin"]
            maq = row["Maquina"]
            
            wait_h = 0.0
            if prev_end:
                # Usar cálculo de horas hábiles para descontar noches y findes
                wait_h = calculate_business_hours(prev_end, start, cfg, machine_name=maq)
            else:
                # First task. Wait is Start - (Plan Start / Material Arrival)?
                # Difficult to know exact 'Ready Date' without more inputs.
                # Let's assume 0 for first task or check if materials were late?
                # For now simplify: 0.
                wait_h = 0.0
            
            bottlenecks.append({
                "Proceso": proc,
                "Máquina": maq,
                "Inicio": start,
                "Fin": end,
                "Tiempo Espera (h)": wait_h,
                "Duración (h)": row["Duracion_h"]
            })
            
            prev_end = end
            
        bn_df = pd.DataFrame(bottlenecks)
        
        # Highlight longest wait
        if not bn_df.empty:
            max_wait_idx = bn_df["Tiempo Espera (h)"].idxmax()
            
            # Show Table
            st.dataframe(
                bn_df,
                column_config={
                    "Inicio": st.column_config.DatetimeColumn(format="D/M HH:mm"),
                    "Fin": st.column_config.DatetimeColumn(format="D/M HH:mm"),
                    "Tiempo Espera (h)": st.column_config.ProgressColumn(
                        format="%.1f h", 
                        min_value=0, 
                        max_value=max(bn_df["Tiempo Espera (h)"].max(), 1.0)
                    ),
                    "Duración (h)": st.column_config.NumberColumn(format="%.1f h")
                },
                use_container_width=True,
                hide_index=True
            )
            
            if bn_df.loc[max_wait_idx, "Tiempo Espera (h)"] > 0.1:
                worst_proc = bn_df.loc[max_wait_idx, "Proceso"]
                worst_maq = bn_df.loc[max_wait_idx, "Máquina"]
                wait_val = bn_df.loc[max_wait_idx, "Tiempo Espera (h)"]
                st.error(f"🚨 **Cuello de Botella Principal:** {worst_proc} ({worst_maq}) demoró **{wait_val:.1f} horas** en arrancar después del proceso anterior.")
            else:
                st.success("✅ Flujo continuo (sin esperas significativas entre procesos).")
