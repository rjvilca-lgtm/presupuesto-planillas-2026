"""
Presupuesto de planillas 2026 — aplicación de entrada.

Reemplaza el formato Excel con macros por un motor único guiado por
configuración (src/config.py). Corre en modo demostración sin base de datos;
al configurar secrets['sql'] pasa a producción sobre Azure SQL sin cambiar
la interfaz.

    streamlit run app.py
"""

import streamlit as st

from src.config import cfg_de
from src.repositorio import crear_repositorio, preparar_filas
from src.validacion import estimar_importe, total_horas, validar
from src.vistas import (grilla, hero, inyectar_estilos, resumen_por_ceco,
                        selector_contexto)


def main():
    st.set_page_config(page_title="Presupuesto de planillas 2026",
                       page_icon="📋", layout="wide")
    inyectar_estilos()

    repo = crear_repositorio()

    st.title("Presupuesto de planillas 2026")
    if repo.modo == "demo":
        st.info("Modo demostración: los datos son de ejemplo y no se guardan en "
                "ninguna base. Para conectar Azure SQL, configura los secrets.",
                icon="🧪")

    origen, hoja = selector_contexto(repo)
    cfg = cfg_de(hoja)
    st.caption(cfg["ayuda"])

    ccos = repo.centros_costo(origen)
    roster = repo.roster(origen) if cfg["usa_roster"] else roster_vacio()
    tarifas = repo.tarifas(hoja) if cfg["tarifa"] == "catalogo" else {}

    if ccos.empty:
        st.warning(f"El departamento {origen} no tiene centros de costo cargados. "
                   "Cárgalos en el catálogo antes de presupuestar.", icon="⚠️")
        return

    editado = grilla(cfg, ccos, roster, tarifas)

    # feedback en vivo
    total = estimar_importe(hoja, editado, tarifas)
    horas = total_horas(editado)
    n = len(editado.dropna(how="all"))
    hero(hoja, total, horas, n)

    # guardado con confirmación
    st.divider()
    ccos_validos = set(ccos["CODIGO_CECO"])
    if st.button("Revisar y guardar", type="primary", use_container_width=True):
        errores = validar(hoja, editado, ccos_validos, tarifas)
        if errores:
            for e in errores:
                st.error(e, icon="⚠️")
            return
        st.session_state["_listo"] = True

    if st.session_state.get("_listo"):
        with st.container(border=True):
            st.subheader("Confirmar carga")
            st.write(f"Planilla **{cfg['etiqueta']}** · Departamento **{origen}**")
            resumen_por_ceco(hoja, editado, tarifas)
            st.caption("Al confirmar se reemplaza la carga anterior de esta "
                       "planilla para este departamento y se ejecuta la valorización.")
            c1, c2 = st.columns(2)
            if c1.button("Confirmar y valorizar", type="primary",
                         use_container_width=True):
                guardar(repo, hoja, origen, editado)
                st.session_state["_listo"] = False
            if c2.button("Cancelar", use_container_width=True):
                st.session_state["_listo"] = False
                st.rerun()


def guardar(repo, hoja, origen, editado):
    cfg = cfg_de(hoja)
    filas, cols = preparar_filas(hoja, origen, editado, repo)
    try:
        if repo.modo == "sql":
            n = repo.guardar(hoja, origen, filas, cols, cfg["sps"])
        else:
            n = repo.guardar(hoja, origen, filas)
        st.success(f"{n} registro(s) cargado(s) y valorizado(s) para "
                   f"{cfg['etiqueta']} en {origen}.", icon="✅")
    except Exception as ex:
        st.error(f"No se guardó nada; se revirtió la operación. Detalle: {ex}",
                 icon="🛑")


def roster_vacio():
    import pandas as pd
    return pd.DataFrame(columns=["DNI", "NOMBRE"])


if __name__ == "__main__":
    main()
