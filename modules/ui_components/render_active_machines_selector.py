import streamlit as st

# Procesos cuyas máquinas del Excel son meros placeholders (outsourced por defecto)
_PROCESOS_TERC_DEFAULT = {"encapado", "stamping", "plastificado", "cuño"}

def render_active_machines_selector(cfg):
    """Returns list of selected machines."""
    st.subheader("🏭 Máquinas Disponibles")
    maquinas_df = cfg["maquinas"]
    maquinas_todas = sorted(maquinas_df["Maquina"].unique().tolist())

    # Procesos que ya tienen al menos una máquina CUSTOM (_IsCustom=True)
    if "_IsCustom" in maquinas_df.columns:
        procs_con_custom = set(
            maquinas_df.loc[maquinas_df["_IsCustom"] == True, "Proceso"]
            .dropna().str.strip().str.lower().unique()
        )
    else:
        procs_con_custom = set()

    def _es_placeholder_reemplazado(nombre_maq):
        """True si la máquina es un placeholder outsourced con custom disponible."""
        fila = maquinas_df[maquinas_df["Maquina"] == nombre_maq]
        if fila.empty:
            return False
        proc = str(fila["Proceso"].iloc[0]).strip().lower()
        es_placeholder = proc in _PROCESOS_TERC_DEFAULT
        es_no_custom = not (
            "_IsCustom" in fila.columns and bool(fila["_IsCustom"].iloc[0]) is True
        )
        return es_placeholder and es_no_custom and (proc in procs_con_custom)

    # Máquinas excluidas del default (siempre excluidas + placeholders reemplazados)
    SIEMPRE_EXCLUIDAS = {"Manual 3", "Descartonadora 3", "Iberica", "Descartonadora 4"}

    default_maquinas = [
        m for m in maquinas_todas
        if m not in SIEMPRE_EXCLUIDAS
        and not any(excl in m for excl in SIEMPRE_EXCLUIDAS)
        and not _es_placeholder_reemplazado(m)
    ]

    maquinas_activas = st.multiselect(
        "Seleccioná las máquinas que se usarán en esta planificación:",
        options=maquinas_todas,
        default=default_maquinas,
        key="maquinas_activas_selector"
    )

    if len(maquinas_activas) < len(maquinas_todas):
        st.warning(f"Planificando solo con {len(maquinas_activas)} de {len(maquinas_todas)} máquinas.")

    return maquinas_activas
