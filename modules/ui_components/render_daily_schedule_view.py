import streamlit as st
import pandas as pd
from datetime import date, timedelta
from modules.utils.config_loader import es_dia_habil, es_feriado

def render_daily_schedule_view(schedule, cfg):
    """
    Renders a calendar view showing tasks assigned per day.
    """
    if schedule.empty:
        return

    st.subheader("🗓️ Vista Calendario (Tareas por Día)")
    st.write("Visualizá las tareas programadas organizadas en un calendario semanal.")

    # Filtro de fecha para navegar
    col1, col2 = st.columns([1, 3])
    with col1:
        start_date = st.date_input("Fecha Inicio Calendario:", value=date.today(), key="cal_start_date")
    
    # Mostramos 2 semanas por defecto desde la fecha elegida
    end_date = start_date + timedelta(days=7)
    
    with col2:
        # Filtros adicionales
        unique_maqs = sorted(schedule["Maquina"].dropna().unique().tolist())
        selected_maqs = st.multiselect("Filtrar Máquinas:", unique_maqs, default=[], placeholder="(Todas)", key="cal_maq_filter")
        
    # Preparar el dataframe expandiendo las tareas que cruzan multiples dias
    cal_start = start_date - timedelta(days=start_date.weekday())
    cal_end = end_date + timedelta(days=6 - end_date.weekday())
    
    tasks_per_day = {cal_start + timedelta(days=i): [] for i in range((cal_end - cal_start).days + 1)}
    
    for _, row in schedule.iterrows():
        # Aplicar filtro de máquina si corresponde
        if selected_maqs and row["Maquina"] not in selected_maqs:
            continue
            
        t_start = row["Inicio"].date() if pd.notna(row["Inicio"]) else None
        t_end = row["Fin"].date() if pd.notna(row["Fin"]) else None
        
        if not t_start or not t_end:
            continue
            
        # Solo procesar si se intersecta con nuestro rango de visualización
        if t_end < cal_start or t_start > cal_end:
            continue
            
        # Generar entrada para cada día que abarca la tarea dentro del rango extendido
        current_d = max(t_start, cal_start)
        clip_end = min(t_end, cal_end)
        
        while current_d <= clip_end:
            if current_d in tasks_per_day:
                # Solo agregamos la tarea a ese día si la máquina efectivamente está programada para trabajar 
                # (es decir, es día hábil para esa máquina y no feriado)
                if es_dia_habil(current_d, cfg, maquina=row["Maquina"]):
                    tasks_per_day[current_d].append({
                        "ot": str(row['OT_id']),
                        "maquina": str(row['Maquina']),
                        "cliente": str(row['Cliente']),
                        "producto": str(row.get('Cliente-articulo', ''))
                    })
            current_d += timedelta(days=1)
            
    # Chequear si hay tareas en rango estricto del visualizador para info box
    tasks_in_range = any(len(tasks_per_day[d]) > 0 for d in tasks_per_day if start_date <= d <= end_date)
    if not tasks_in_range:
        maq_text = "las máquinas seleccionadas" if selected_maqs else "ninguna máquina"
        st.info(f"No hay tareas asignadas para {maq_text} en el periodo {start_date.strftime('%d/%m')} al {end_date.strftime('%d/%m')}.")

    # Detectar si hay que ocultar los fines de semana enteros
    # (Si sabado y domingo no tienen NINGUNA tarea en TODA la vista, ocultamos las columnas)
    show_saturday = any(d.weekday() == 5 and (d in tasks_per_day and len(tasks_per_day[d]) > 0) for d in range((cal_end - cal_start).days + 1) for d in [cal_start + timedelta(days=d)])
    show_sunday = any(d.weekday() == 6 and (d in tasks_per_day and len(tasks_per_day[d]) > 0) for d in range((cal_end - cal_start).days + 1) for d in [cal_start + timedelta(days=d)])
    
    total_cols = 5 + (1 if show_saturday else 0) + (1 if show_sunday else 0)

    # Generar layout HTML / CSS Grid para el Calendario
    # Usamos RGBA para que se adapte al modo oscuro (fondo transparente, blanco auto-adoptado)
    st.markdown(f"""
    <style>
        .calendar-grid {{
            display: grid;
            grid-template-columns: repeat({total_cols}, 1fr);
            gap: 8px;
            margin-top: 15px;
            margin-bottom: 30px;
        }}
        .calendar-header {{
            text-align: center;
            font-weight: bold;
            padding: 10px;
            background-color: rgba(128, 128, 128, 0.1);
            border-radius: 6px;
            font-size: 0.95em;
        }}
        .calendar-day {{
            border: 1px solid rgba(128, 128, 128, 0.2);
            border-radius: 6px;
            min-height: 130px;
            padding: 8px;
            display: flex;
            flex-direction: column;
            background-color: rgba(128, 128, 128, 0.02);
            transition: all 0.2s ease;
        }}
        .calendar-day:hover {{
            border-color: rgba(128, 128, 128, 0.4);
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        }}
        .calendar-day.out-of-range {{
            opacity: 0.4;
            background-color: rgba(128, 128, 128, 0.05);
        }}
        .calendar-day.holiday-day .day-number {{
            color: #d32f2f;
        }}
        .day-number {{
            font-weight: bold;
            margin-bottom: 8px;
            border-bottom: 1px solid rgba(128, 128, 128, 0.2);
            padding-bottom: 4px;
            font-size: 0.9em;
            text-align: right;
            color: rgba(128, 128, 128, 0.9);
        }}
        .task-item {{
            font-size: 0.8em;
            background-color: rgba(25, 118, 210, 0.1);
            border-left: 3px solid #1976d2;
            margin-bottom: 4px;
            padding: 4px;
            border-radius: 4px;
            line-height: 1.1;
            word-wrap: break-word;
        }}
        .task-ot {{
            font-weight: bold;
            color: #1976d2;
            display: block;
            margin-bottom: 1px;
            padding-bottom: 1px;
            font-size: 0.9em;
        }}
        .task-maq {{
            font-size: 0.95em;
            font-weight: 500;
            padding-bottom: 1px;
        }}
        .task-prod {{
            font-size: 0.85em;
            color: rgba(128, 128, 128, 0.95);
            display: block;
            margin-bottom: 1px;
            padding-bottom: 1px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .task-cli {{
            font-style: italic;
            opacity: 0.8;
            font-size: 0.85em;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            padding-bottom: 1px;
        }}
    </style>
    """, unsafe_allow_html=True)

    html_content = '<div class="calendar-grid">'
    
    dias_semana = [
        ("Lunes", 0), ("Martes", 1), ("Miércoles", 2), 
        ("Jueves", 3), ("Viernes", 4), ("Sábado", 5), ("Domingo", 6)
    ]
    
    for d_name, d_idx in dias_semana:
        if d_idx == 5 and not show_saturday: continue
        if d_idx == 6 and not show_sunday: continue
        html_content += f'<div class="calendar-header">{d_name}</div>'
        
    curr_d = cal_start
    while curr_d <= cal_end:
        # Skip completly if column is disabled
        if curr_d.weekday() == 5 and not show_saturday:
            curr_d += timedelta(days=1)
            continue
        if curr_d.weekday() == 6 and not show_sunday:
            curr_d += timedelta(days=1)
            continue
            
        is_in_range = start_date <= curr_d <= end_date
        
        # Determinar si el día tiene tareas asignadas (posibles extras)
        has_tasks = curr_d in tasks_per_day and len(tasks_per_day[curr_d]) > 0
        
        # Evaluar si el día es hábil general (o feriado)
        is_habil = es_dia_habil(curr_d, cfg)
        is_holiday = es_feriado(curr_d, cfg)
        
        # Si NO es hábil y NO tiene tareas, lo vaciamos visualmente usando block invisible
        # para mantener la estructura de la grilla (ya que la columna existe)
        if not is_habil and not has_tasks:
            html_content += '<div class="calendar-day" style="border: none; background: transparent; box-shadow: none;"></div>'
            curr_d += timedelta(days=1)
            continue
            
        out_class = "" if is_in_range else " out-of-range"
        holiday_class = " holiday-day" if is_holiday else ""
        
        # Resaltado del día de HOY
        today_style = ""
        if curr_d == date.today():
             today_style = "border-color: #1976d2; border-width: 2px; background-color: rgba(25,118,210,0.03);"
             
        html_content += f'<div class="calendar-day{out_class}{holiday_class}" style="{today_style}">'
        html_content += f'<div class="day-number">{curr_d.strftime("%d/%m")}</div>'
        
        if has_tasks:
            seen = set()
            unique_tasks = []
            for t in tasks_per_day[curr_d]:
                t_key = f"{t['ot']}-{t['maquina']}"
                if t_key not in seen:
                    seen.add(t_key)
                    unique_tasks.append(t)
            
            # Ordenar las tareas del día por máquina alfabéticamente
            unique_tasks.sort(key=lambda x: x['maquina'])
            
            for t in unique_tasks:
                cli_name = t["cliente"]
                prod_name = t["producto"]
                
                html_content += f"""<div class="task-item" title="{prod_name} - {cli_name}">
<span class="task-ot">OT: {t["ot"]}</span>
<span class="task-prod">{prod_name}</span>
<span class="task-maq">{t["maquina"]}</span><br/>
</div>"""
                
        html_content += '</div>'
        curr_d += timedelta(days=1)
        
    html_content += '</div>'

    st.markdown(html_content, unsafe_allow_html=True)
