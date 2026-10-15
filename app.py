"""
Presupuesto de planillas 2026 — aplicación de entrada.

Reemplaza el formato Excel con macros por un motor único guiado por
configuración (src/config.py). Corre en modo demostración sin base de datos;
al configurar secrets['sql'] pasa a producción sobre Azure SQL sin cambiar
la interfaz.

Flujo (ver src/flujo.py): cada planilla se guarda como borrador las veces que
se quiera; el departamento valoriza todo junto desde "Resumen y valorización".

    streamlit run app.py
"""

import streamlit as st

from src.auth import barra_usuario, exigir_login
from src.borrador import (aviso_al_salir, autoguardar, firma, marcar_guardado,
                          mostrar_indicador, indicador, pendiente, toca_autoguardar)
from src.carga_academica import consulta_carga_academica, registro_carga_academica
from src.config import MESES, cfg_de, dims_fila
from src.flujo import (aviso_departamento, leer_flujo, marcar, ahora, panel_flujo,
                       vista_admin, vista_resumen)
from src.reporte import vista_reporte
from src.rrhh import vista_desarrollo_humano
from src.repositorio import crear_repositorio, preparar_filas
from src.validacion import conteo, estimar_importe, total_horas, validar
from src.vistas import (TC_HOJAS, ficha_docente, grilla, hero,
                        inyectar_estilos, selector_contexto)


def main():
    st.set_page_config(page_title="Presupuesto de planillas 2026",
                       page_icon="📋", layout="wide")
    inyectar_estilos()

    repo = crear_repositorio()
    usuario = exigir_login(repo)
    fl = leer_flujo(repo)

    barra_usuario(usuario)
    st.title("Presupuesto de planillas 2026")
    if repo.modo == "demo":
        st.info("Modo demostración: los datos son de ejemplo y no se guardan en "
                "ninguna base. Para conectar Azure SQL, configura los secrets.",
                icon="🧪")

    # Cada rol ve solo sus pestañas; la consulta de carga académica, todos
    pestañas = []
    if usuario.presupuesto or usuario.departamentos:
        pestañas.append(("Presupuesto por departamento",
                         lambda: vista_departamentos(repo, fl, usuario)))
    if usuario.presupuesto or usuario.dga:
        pestañas.append(("Carga académica · registro (DGA)",
                         lambda: registro_carga_academica(repo, fl)))
    if usuario.rrhh:
        pestañas.append(("Desarrollo Humano",
                         lambda: vista_desarrollo_humano(repo, usuario, repo.departamentos())))
    pestañas.append(("Carga académica · consulta", lambda: consulta_carga_academica(repo, fl)))
    pestañas.append(("Resumen de valorización",
                     lambda: vista_reporte(repo, fl, usuario, repo.departamentos())))
    if usuario.presupuesto:
        pestañas.append(("Presupuesto · administración",
                         lambda: vista_admin(repo, fl, repo.departamentos(), usuario)))
    # Solo se ejecuta la pestaña abierta: las demás no consultan la base ni
    # dibujan nada hasta que se abren (lo editado y no guardado sigue en la sesión)
    tabs = st.tabs([t for t, _ in pestañas], on_change="rerun", key="nav_principal")
    for tab, (_, vista) in zip(tabs, pestañas):
        if tab.open:
            with tab:
                vista()
    aviso_al_salir()


def vista_departamentos(repo, fl, usuario):
    # Presupuesto ve todos los departamentos; los demás, solo los suyos
    permitidos = None if usuario.presupuesto else usuario.departamentos
    origen, seleccion = selector_contexto(repo, permitidos)
    panel_flujo(fl)
    solo_lectura = aviso_departamento(fl, origen)

    ccos = repo.centros_costo(origen)
    if ccos.empty:
        st.warning(f"El departamento {origen} no tiene centros de costo cargados. "
                   "Cárgalos en el catálogo antes de presupuestar.", icon="⚠️")
        return

    # Lo ya guardado del departamento: las planillas arrancan desde ahí
    entrada = repo.entrada(origen)

    if seleccion == "RESUMEN":
        vista_resumen(repo, fl, origen, ccos, repo.roster(origen), repo.estructura_tc(origen))
        return

    if seleccion == "TC":
        st.caption(cfg_de(TC_HOJAS[0])["ayuda"])
        roster = repo.roster(origen)
        estructura = repo.estructura_tc(origen)
        pestañas = st.tabs(["I semestre (Ene-Jun)", "II semestre (Jul-Dic)"],
                           on_change="rerun", key=f"tabs_tc_{origen}")
        for hoja, tab in zip(TC_HOJAS, pestañas):
            if not tab.open:
                continue
            with tab:
                _renderizar_ficha_tc(repo, fl, hoja, ccos, roster, estructura, origen,
                                     entrada[entrada["HOJA_ORIGEN"] == hoja], solo_lectura)
        return

    cfg = cfg_de(seleccion)
    st.caption(cfg["ayuda"])
    roster = repo.roster(origen) if cfg["usa_roster"] else roster_vacio()
    tarifas = repo.tarifas(seleccion) if cfg["tarifa"] == "catalogo" else {}
    _renderizar_grilla(repo, fl, seleccion, cfg, ccos, roster, tarifas, origen,
                       entrada[entrada["HOJA_ORIGEN"] == seleccion], solo_lectura)


def _mostrar_resultado(hoja):
    resultado = st.session_state.pop(f"_resultado_{hoja}", None)
    if resultado:
        ok, mensaje = resultado
        (st.success if ok else st.error)(mensaje, icon="✅" if ok else "🛑")


def _renderizar_ficha_tc(repo, fl, hoja, ccos, roster, estructura, origen, guardado,
                         solo_lectura):
    """Ficha TC (maestro-detalle) con guardado de borrador en la barra fija."""
    cfg = cfg_de(hoja)
    _mostrar_resultado(hoja)
    editado = ficha_docente(cfg, ccos, estructura, roster, origen, guardado, solo_lectura)

    # La estructura TC puede traer CECOs de otros departamentos (docentes
    # transversales); son válidos porque vienen del catálogo, no del usuario.
    ccos_validos = set(ccos["CODIGO_CECO"]) | set(estructura["CODIGO_CECO"])
    clave, f_actual = f"{hoja}|{origen}", firma(editado, dims_fila(cfg), MESES)
    hay_cambios = pendiente(clave, f_actual)

    def _errores():
        errores = validar(hoja, editado, ccos_validos, {}, estricto=False)
        invalidos = st.session_state.get(f"_invalidos_{hoja}") or []
        if invalidos:
            errores.insert(0, "Hay horas mal escritas (usa hh:mm, por ejemplo 03:30) en: "
                           + ", ".join(invalidos) + ".")
        return errores

    if hay_cambios and not solo_lectura and toca_autoguardar(clave):
        autoguardar(clave, f_actual, _errores(),
                    lambda: guardar_borrador(repo, hoja, origen, editado))
        hay_cambios = pendiente(clave, f_actual)
    st.markdown('<div style="height:60px"></div>', unsafe_allow_html=True)
    with st.container(key=f"barra_guardar_{hoja}"):
        c_info, c_btn = st.columns([3, 1])
        con_horas = editado.loc[editado[cfg["mes_carga"]] > 0, "DNI"].nunique()
        guardado_en = fl.estado(origen).get("FECHA_GUARDADO")
        from src.flujo import fmt
        c_info.markdown(
            f'<div class="bottom-info">{cfg["etiqueta"]} · '
            f'{con_horas} de {editado["DNI"].nunique()} docente(s) con horas'
            f'{" · último guardado " + fmt(guardado_en) if guardado_en else ""}'
            f'<br><span style="color:{"#B54708" if hay_cambios else "#067647"}">'
            f'{indicador(clave, hay_cambios, solo_lectura)}</span></div>',
            unsafe_allow_html=True)
        clic_guardar = c_btn.button("Guardar", type="primary", width="stretch",
                                    key=f"btn_guardar_{hoja}", disabled=solo_lectura)
    if clic_guardar:
        errores = _errores()
        if errores:
            _dialogo_errores(errores)
        else:
            with st.spinner("Guardando…"):
                ok, mensaje = guardar_borrador(repo, hoja, origen, editado)
            if ok:
                marcar_guardado(clave, f_actual)
                st.session_state[f"_resultado_{hoja}"] = (True, mensaje)
                st.rerun()
            st.error(mensaje, icon="🛑")


@st.dialog("Revisa antes de guardar", width="large")
def _dialogo_errores(errores):
    for e in errores:
        st.error(e, icon="⚠️")
    if st.button("Volver", type="primary", width="stretch"):
        st.rerun()


def _renderizar_grilla(repo, fl, hoja, cfg, ccos, roster, tarifas, origen, guardado,
                       solo_lectura):
    """Grilla matricial + feedback en vivo + guardado de borrador."""
    _mostrar_resultado(hoja)
    editado = grilla(cfg, ccos, roster, tarifas, origen, guardado, solo_lectura)

    total = estimar_importe(hoja, editado, tarifas)
    horas = total_horas(hoja, editado)
    lineas, registros = conteo(editado)
    hero(hoja, total, horas, lineas, registros)

    clave = f"{hoja}|{origen}"
    f_actual = firma(editado, [c for c in editado.columns if c not in MESES], MESES)
    hay_cambios = pendiente(clave, f_actual)
    errores_de = lambda: validar(hoja, editado, set(ccos["CODIGO_CECO"]), tarifas,
                                 estricto=False)
    if hay_cambios and not solo_lectura and toca_autoguardar(clave):
        autoguardar(clave, f_actual, errores_de(),
                    lambda: guardar_borrador(repo, hoja, origen, editado))
        hay_cambios = pendiente(clave, f_actual)

    st.divider()
    mostrar_indicador(clave, hay_cambios, solo_lectura)
    if st.button("Guardar", type="primary", width="stretch",
                 key=f"btn_guardar_{hoja}", disabled=solo_lectura):
        errores = errores_de()
        if errores:
            _dialogo_errores(errores)
        else:
            with st.spinner("Guardando…"):
                resultado = guardar_borrador(repo, hoja, origen, editado)
            if resultado[0]:
                marcar_guardado(clave, f_actual)
            st.session_state[f"_resultado_{hoja}"] = resultado
            st.rerun()


def guardar_borrador(repo, hoja, origen, editado):
    """Guarda la planilla sin valorizar. Devuelve (ok, mensaje)."""
    cfg = cfg_de(hoja)
    filas, cols = preparar_filas(hoja, origen, editado, repo)
    try:
        n = repo.guardar_borrador(hoja, origen, filas, cols)
        marcar(repo, origen, FECHA_GUARDADO=ahora())
        return True, (f"{cfg['etiqueta']}: {n} registro(s) guardado(s). Cuando termines "
                      "todas tus planillas, valoriza desde «Resumen y valorización».")
    except Exception as ex:
        return False, f"No se guardó nada; se revirtió la operación. Detalle: {ex}"


def roster_vacio():
    import pandas as pd
    return pd.DataFrame(columns=["DNI", "NOMBRE"])


if __name__ == "__main__":
    main()
