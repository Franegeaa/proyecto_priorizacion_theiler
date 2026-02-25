import streamlit as st
import pandas as pd
from modules.utils.config_loader import horas_por_dia

def render_metrics_section(schedule, resumen_ot, carga_md, cfg):
    """
    Renderiza una sección de métricas y KPIs interactiva.
    """
    st.subheader("📊 Tablero de Métricas y KPIs")
    
    if schedule.empty or resumen_ot.empty:
        st.info("No hay datos suficientes para calcular métricas.")
        return

    # Básicas
    total_ots = resumen_ot["OT_id"].nunique()
    atrasadas = int(resumen_ot["EnRiesgo"].sum())
    horas_extra_total = float(carga_md["HorasExtra"].sum()) if not carga_md.empty else 0.0
    jornada = horas_por_dia(cfg)

    # 1. Eficiencia y Capacidad (Top Cuellos de Botella)
    if not carga_md.empty:
        # Agrupar por máquina para ver carga total vs disponible
        carga_maq = carga_md.groupby("Maquina")[["HsAsig", "HsDisp"]].sum().reset_index()
        # Evitar división por cero
        carga_maq["Ocupacion_Pct"] = (carga_maq["HsAsig"] / carga_maq["HsDisp"].replace(0, 1)) * 100
        
        # Ocupación Promedio Global
        total_asig = carga_maq["HsAsig"].sum()
        total_disp = carga_maq["HsDisp"].sum()
        ocupacion_promedio = (total_asig / total_disp * 100) if total_disp > 0 else 0
        
        # Top 3 Cuellos de botella
        top_cuellos = carga_maq.sort_values(by="Ocupacion_Pct", ascending=False).head(3)
    else:
        ocupacion_promedio = 0
        top_cuellos = pd.DataFrame()

    # 2. Volumen y Cumplimiento
    tasa_cumplimiento = ((total_ots - atrasadas) / total_ots * 100) if total_ots > 0 else 100
    
    # Total de pliegos: tomar el maximo de pliegos por OT
    if "CantidadPliegos" in schedule.columns:
        pliegos_por_ot = schedule.groupby("OT_id")["CantidadPliegos"].max()
        total_pliegos = pliegos_por_ot.sum()
    else:
        total_pliegos = 0
    
    # Promedio de retraso
    retrasos = []
    if "EnRiesgo" in resumen_ot.columns and "Fin" in resumen_ot.columns and "DueDate" in resumen_ot.columns:
        for _, row in resumen_ot[resumen_ot["EnRiesgo"]].iterrows():
            try:
                 fin_dt = pd.to_datetime(row["Fin"])
                 due_dt = pd.to_datetime(row["DueDate"])
                 if pd.notna(fin_dt) and pd.notna(due_dt) and fin_dt > due_dt:
                     diff_h = (fin_dt - due_dt).total_seconds() / 3600.0
                     retrasos.append(diff_h)
            except:
                 pass
    promedio_retraso_h = (sum(retrasos) / len(retrasos)) if retrasos else 0
    promedio_retraso_dias = promedio_retraso_h / 24.0

    # 3. Alertas
    if "Urgente" in schedule.columns:
        urgentes_count = schedule[schedule["Urgente"] == True]["OT_id"].nunique()
    else:
        urgentes_count = 0
    pct_urgentes = (urgentes_count / total_ots * 100) if total_ots > 0 else 0
    
    tercerizados_count = len(schedule[schedule["IsOutsourced"] == True]) if "IsOutsourced" in schedule.columns else 0
    saltados_count = len(schedule[schedule["IsSkipped"] == True]) if "IsSkipped" in schedule.columns else 0
    
    # --- RENDERIZADO VISUAL ---
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Órdenes Planificadas", total_ots)
    c2.metric("Tasa de Cumplimiento a Tiempo", f"{tasa_cumplimiento:.1f}%")
    c3.metric("Ocupación Promedio (Planta)", f"{ocupacion_promedio:.1f}%")
    c4.metric("Total Pliegos a Procesar", f"{total_pliegos:,.0f}".replace(",", "."))

    st.markdown("---")
    
    tab1, tab2, tab3 = st.tabs(["🚀 Rendimiento", "⚠️ Alertas y Retrasos", "🏭 Cuellos de Botella"])
    
    with tab1:
        st.write("**Resumen Operativo**")
        cc1, cc2, cc3 = st.columns(3)
        cc1.metric("Horas Extra (totales)", f"{horas_extra_total:.1f} h")
        cc2.metric("Jornada Estándar", f"{jornada:.1f} hs/día")
        cc3.metric("Procesos Saltados/Tercerizados", f"{saltados_count} / {tercerizados_count}")
        
    with tab2:
        st.write("**Estado del Plan**")
        ca1, ca2, ca3 = st.columns(3)
        ca1.metric("Órdenes Atrasadas", atrasadas, delta_color="inverse", delta=f"-{atrasadas}" if atrasadas > 0 else "0")
        ca2.metric("Retraso Promedio (Órdenes en riesgo)", f"{promedio_retraso_dias:.1f} días" if promedio_retraso_dias > 0 else "Sin atrasos")
        ca3.metric("Trabajos Urgentes", urgentes_count, f"{pct_urgentes:.1f}% del total", delta_color="off")
    
    with tab3:
        st.write("**Top 3 Máquinas con Mayor Carga de Trabajo**")
        st.caption("Muestra qué porcentaje del tiempo disponible está ocupado por tareas agendadas.")
        if not top_cuellos.empty:
            for idx, row in top_cuellos.iterrows():
                maq = row['Maquina']
                pct = row['Ocupacion_Pct']
                st.write(f"**{maq}**: {pct:.1f}% de ocupación")
                st.progress(min(max(pct / 100.0, 0.0), 1.0))
        else:
            st.info("No se pudieron calcular los cuellos de botella por falta de datos.")
            
    st.markdown("<br>", unsafe_allow_html=True)
