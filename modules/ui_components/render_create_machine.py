import streamlit as st
import pandas as pd


def render_create_machine(cfg, persistence=None):
    """
    Renders a UI section to create new custom machines at runtime.
    Custom machines are injected into cfg['maquinas'] and optionally persisted in the DB.
    """

    st.subheader("🏗️ Gestión de Máquinas Personalizadas")

    # --------------------------------------------------------------------
    # LOAD & DISPLAY existing custom machines
    # --------------------------------------------------------------------
    if "custom_machines" not in st.session_state:
        st.session_state.custom_machines = []

    custom_machines: list = st.session_state.custom_machines

    # Show existing custom machines in a compact table + delete buttons
    if custom_machines:
        st.markdown("**Máquinas personalizadas activas:**")
        for i, cm in enumerate(custom_machines):
            col_info, col_del = st.columns([5, 1])
            with col_info:
                extra = ""
                if cm.get("es_troqueladora"):
                    extra = (
                        f" | Pliego max: {cm['pli_max_anc']}×{cm['pli_max_lar']} cm"
                        f" | Pliego min: {cm['pli_min_anc']}×{cm['pli_min_lar']} cm"
                    )
                tag = f"⚙️ **{cm['nombre']}** — {cm['proceso']} | {cm['velocidad']} pl/h{extra} | {cm['planta']}"
                st.markdown(tag)
            with col_del:
                if st.button("🗑️", key=f"del_cm_{i}", help=f"Eliminar {cm['nombre']}"):
                    st.session_state.custom_machines.pop(i)
                    _save_if_connected(persistence, st.session_state.custom_machines)
                    st.rerun()
    else:
        st.info("No hay máquinas personalizadas creadas aún.")

    # --------------------------------------------------------------------
    # FORM: Create new machine
    # --------------------------------------------------------------------
    with st.expander("➕ Crear nueva máquina", expanded=False):
        # --- Proceso (from existing ones) ---
        procesos_existentes = sorted(cfg["maquinas"]["Proceso"].dropna().unique().tolist())
        proceso = st.selectbox(
            "Proceso",
            options=procesos_existentes,
            key="cm_proceso",
            help="Debe ser un proceso ya existente en la configuración.",
        )

        es_troqueladora = "troquel" in str(proceso).lower()

        col1, col2 = st.columns(2)
        with col1:
            nombre = st.text_input(
                "Nombre de la máquina",
                key="cm_nombre",
                placeholder="Ej: Troq Nº 4 Planta 2",
            )
        with col2:
            planta = st.selectbox(
                "Planta",
                options=["Planta 1", "Planta 2"],
                key="cm_planta",
            )

        col3, col4, col5 = st.columns(3)
        with col3:
            velocidad = st.number_input(
                "Velocidad (pliegos/hora)",
                min_value=1,
                value=1000,
                step=50,
                key="cm_velocidad",
            )
        with col4:
            setup_base = st.number_input(
                "Setup base (min)",
                min_value=0,
                value=30,
                step=5,
                key="cm_setup_base",
            )
        with col5:
            setup_menor = st.number_input(
                "Setup menor (min)",
                min_value=0,
                value=15,
                step=5,
                key="cm_setup_menor",
            )

        activa_por_defecto = st.checkbox(
            "Activa por defecto al seleccionar máquinas",
            value=True,
            key="cm_activa",
        )

        # --- Troqueladora-specific fields ---
        pli_max_anc = pli_max_lar = pli_min_anc = pli_min_lar = None
        tipo_troquel = None

        if es_troqueladora:
            st.markdown("---")
            st.markdown("**⚙️ Configuración de Troquelado**")

            tipo_troquel = st.selectbox(
                "Tipo de troqueladora",
                options=["Manual", "Automática", "Ibérica"],
                key="cm_tipo_troquel",
                help="Afecta las reglas de balanceo (bocas, cantidad de pliegos).",
            )

            st.markdown("📐 **Pliego Máximo** (tamaño mayor que puede entrar)")
            c1, c2 = st.columns(2)
            with c1:
                pli_max_anc = st.number_input(
                    "Ancho máx. (cm)", min_value=0.0, value=80.0, step=1.0, key="cm_pli_max_anc"
                )
            with c2:
                pli_max_lar = st.number_input(
                    "Largo máx. (cm)", min_value=0.0, value=105.0, step=1.0, key="cm_pli_max_lar"
                )

            st.markdown("📐 **Pliego Mínimo** (tamaño menor que puede entrar, obligatorio para Automáticas)")
            c3, c4 = st.columns(2)
            with c3:
                pli_min_anc = st.number_input(
                    "Ancho mín. (cm)", min_value=0.0, value=0.0, step=1.0, key="cm_pli_min_anc"
                )
            with c4:
                pli_min_lar = st.number_input(
                    "Largo mín. (cm)", min_value=0.0, value=0.0, step=1.0, key="cm_pli_min_lar"
                )

            if tipo_troquel == "Automática" and (pli_min_anc == 0 or pli_min_lar == 0):
                st.warning("⚠️ Las troqueladoras automáticas requieren un pliego mínimo mayor a 0.")

        # --- Submit ---
        if st.button("✅ Crear máquina", key="cm_submit", type="primary"):
            # Validations
            nombre_clean = nombre.strip()
            nombres_existentes = cfg["maquinas"]["Maquina"].str.lower().tolist()
            nombres_custom = [c["nombre"].lower() for c in custom_machines]

            if not nombre_clean:
                st.error("❌ El nombre de la máquina no puede estar vacío.")
            elif nombre_clean.lower() in nombres_existentes or nombre_clean.lower() in nombres_custom:
                st.error(f"❌ Ya existe una máquina con el nombre «{nombre_clean}». Usá un nombre diferente.")
            elif es_troqueladora and tipo_troquel == "Automática" and (pli_min_anc == 0 or pli_min_lar == 0):
                st.error("❌ Completá el pliego mínimo para la troqueladora automática.")
            else:
                new_machine = {
                    "nombre": nombre_clean,
                    "proceso": proceso,
                    "velocidad": int(velocidad),
                    "setup_base": int(setup_base),
                    "setup_menor": int(setup_menor),
                    "planta": planta,
                    "activa_por_defecto": activa_por_defecto,
                    "es_troqueladora": es_troqueladora,
                    "tipo_troquel": tipo_troquel,
                    "pli_max_anc": float(pli_max_anc) if pli_max_anc is not None else None,
                    "pli_max_lar": float(pli_max_lar) if pli_max_lar is not None else None,
                    "pli_min_anc": float(pli_min_anc) if pli_min_anc is not None else None,
                    "pli_min_lar": float(pli_min_lar) if pli_min_lar is not None else None,
                }
                st.session_state.custom_machines.append(new_machine)
                _save_if_connected(persistence, st.session_state.custom_machines)
                st.success(f"✅ Máquina «{nombre_clean}» creada correctamente.")
                st.rerun()

    # --------------------------------------------------------------------
    # INJECT custom machines into cfg
    # --------------------------------------------------------------------
    from modules.utils.config_loader import apply_custom_machines
    apply_custom_machines(cfg, custom_machines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _save_if_connected(persistence, machines_list):
    if persistence is not None and persistence.connected:
        persistence.save_custom_machines(machines_list)
