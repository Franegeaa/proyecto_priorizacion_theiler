# Proyecto de Priorización y Planificación de Producción (Theiler)

Este proyecto es una herramienta avanzada de planificación y programación de la producción (APS) diseñada para optimizar el flujo de trabajo en planta. Desarrollada con **Python** y **Streamlit**, permite a los planificadores gestionar órdenes, configurar disponibilidad de máquinas y generar cronogramas detallados de producción.

## 🚀 Funcionalidades Principales

*   **Carga de Datos:** Importación de órdenes de producción desde archivos Excel (exportados de Access/ERP).
*   **Configuración Dinámica:**
    *   Ajuste de velocidades de máquinas promedio en tiempo real.
    *   Definición de días laborales, horarios, feriados y horas extra por máquina.
    *   Gestión de paradas programadas (mantenimiento) o imprevistas.
*   **Motor de Planificación (Scheduler):** Algoritmo inteligente que prioriza órdenes basándose en fechas de entrega, disponibilidad de materiales y restricciones de secuencia de procesos.
*   **Visualización:**
    *   Gantt interactivos de la producción.
    *   Análisis de carga vs. capacidad para detectar cuellos de botella.
    *   Métricas de atrasos y ocupación.
*   **Asignación Manual Controlada:**
    *   Capacidad para reservar órdenes específicas a máquinas manuales (Troqueladoras manuales, Descartonadoras).
    *   Filtrado inteligente de órdenes elegibles basado en:
        *   Proceso pendiente (Troquelado/Descartonado).
        *   Disponibilidad de materia prima en planta.
        *   Llegada de troqueles físicos.
*   **Reportes:** Exportación de resultados en múltiples formatos de Excel (Plan por Máquina, Plan por OT, Resumen General).

## 🛠️ Requisitos del Sistema

*   Python 3.8+
*   Librerías listadas en `requirements.txt`

## 📦 Instalación

1.  **Clonar el repositorio:**
    ```bash
    git clone <url-del-repositorio>
    cd proyecto_priorizacion_theiler
    ```

2.  **Crear y activar un entorno virtual (recomendado):**
    ```bash
    # En macOS/Linux
    python3 -m venv venv
    source venv/bin/activate

    # En Windows
    python -m venv venv
    venv\Scripts\activate
    ```

3.  **Instalar dependencias:**
    ```bash
    pip install -r requirements.txt
    ```

## ▶️ Ejecución

Para iniciar la aplicación web localmente:

```bash
streamlit run app.py
```

La aplicación se abrirá automáticamente en tu navegador predeterminado (usualmente en `http://localhost:8501`).

## 📂 Estructura del Proyecto

*   **`app.py`**: Punto de entrada de la aplicación Streamlit. Maneja la navegación y el estado global.
*   **`modules/`**: Contiene la lógica central del negocio:
    *   `scheduler.py`: Motor principal de planificación.
    *   `schedulers/`: Lógica específica de colas y priorización por tipo de máquina.
    *   `ui_components.py`: Componentes visuales reutilizables de la interfaz.
    *   `config_loader.py`: Gestión de configuraciones desde Excel.
    *   `exporters.py`: Generación de archivos de salida.
    *   `visualizations.py`: Gráficos de Plotly para análisis de datos.
*   **`config/`**: Archivos de configuración estática (ej. `Config_Priorizacion_Theiler.xlsx`).
*   **`tests/`**: Tests unitarios para validar la lógica de agrupación y planificación.

## ⚙️ Configuración

La aplicación utiliza un archivo de configuración base ubicado en `config/Config_Priorizacion_Theiler.xlsx` para definir los parámetros iniciales de las máquinas y procesos. Sin embargo, la mayoría de estos parámetros pueden ser ajustados temporalmente desde la interfaz de usuario durante la sesión de planificación.
