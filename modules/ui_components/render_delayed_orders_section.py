import streamlit as st
import pandas as pd

def render_delayed_orders_section(resumen_ot):
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
    
    # Rename for clearer display
    display_df = delayed_df[cols_to_show].rename(columns={
        "Producto": "Cliente - Artículo",
        "Fin_OT": "Fecha Estimada Entrega",
        "Atraso_h": "Horas de Atraso",
        "DueDate": "Fecha Prometida"
    })
    
    # Sort by amount of delay (descending)
    display_df = display_df.sort_values("Horas de Atraso", ascending=False)
    
    st.markdown(f"**Total de órdenes atrasadas:** {len(display_df)}")
    
    st.dataframe(
        display_df,
        column_config={
            "Fecha Prometida": st.column_config.DatetimeColumn(format="D/M HH:mm"),
            "Fecha Estimada Entrega": st.column_config.DatetimeColumn(format="D/M HH:mm"),
            "Horas de Atraso": st.column_config.NumberColumn(format="%.1f h"),
        },
        use_container_width=True,
        hide_index=True
    )
