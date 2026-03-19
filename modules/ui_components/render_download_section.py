import streamlit as st
from modules.utils.exporters import (
    generar_excel_bytes,
    generar_excel_ot_bytes,
    generar_csv_maquina_str,
    generar_csv_ot_str
)

def render_download_section(schedule, resumen_ot, carga_md, key_suffix=""):
    """Renders the unified download section."""
    st.subheader("📋 Exportar")

    if schedule.empty:
        st.info("No hay plan para exportar.")
        return

    # Generate buffers
    buf_excel = generar_excel_bytes(schedule, resumen_ot, carga_md)
    buf_ot, df_ot_horiz = generar_excel_ot_bytes(schedule)
    csv_str_maq = generar_csv_maquina_str(schedule)
    csv_str_ot = generar_csv_ot_str(df_ot_horiz)

    st.write("---")
    col_maq, col_ot = st.columns(2)
    
    with col_maq:
        st.markdown("#### 🏭 Por Máquina")
        st.caption("Planificación vertical, ideal para operarios.")
        
        st.download_button(
            "⬇️ Excel (Por Máquina + Datos)",
            data=buf_excel,
            file_name="Plan_Produccion_Theiler.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"btn_excel_maq_{key_suffix}"
        )
        
        # st.download_button(
        #     "⬇️ CSV (Compatible Excel 2010)",
        #     data=csv_str_maq,
        #     file_name="Plan_Produccion_Theiler.csv",
        #     mime="text/csv",
        #     key="btn_csv_maq"
        # )

    with col_ot:
        st.markdown("#### 📦 Por Orden de Trabajo")
        st.caption("Visión de flujo (horizontal).")

        st.download_button(
            "⬇️ Excel 97-2003 (Horizontal por OT)",
            data=buf_ot,
            file_name="Plan_Produccion_Por_OT.xls",
            mime="application/vnd.ms-excel",
            key=f"btn_excel_ot_{key_suffix}"
        )
  