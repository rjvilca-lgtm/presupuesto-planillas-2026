"""
Centros de costo 2027 (Presupuesto · administración › Centros de costo).

Para saber qué centros existen en cada facultad y dirección, quién puede
presupuestarlos, y agregarlos o corregirlos sin escribir SQL:

  - Consultar: el catálogo CENTROS_COSTOS_2027 con los departamentos que
    pueden presupuestar cada centro (CECOS_DEPARTAMENTO_2027), los que lo
    tienen en la ficha TC (CECO_CONCEPTO_TC) y las filas guardadas en 2027.
  - Verificar: lo que impide presupuestar o no cuadra.
  - Actualizar: pegar centros desde Excel, asignarlos a departamentos y
    agregarlos a la ficha TC.
  - Cambios: el registro de quién cambió qué (AUDITORIA_CECOS_2027).

Escribir requiere sql/crear_gestion_cecos_2027.sql. Nunca borra centros del
catálogo ni quita un centro en el que un departamento ya tiene datos 2027.
"""

import re

import pandas as pd
import streamlit as st

from .config import CONCEPTO_ACADEMICAS, CONCEPTO_CRONOLOGICAS

CODIGO = re.compile(r"\d{2}(\.\d{2}){4}")
CONCEPTOS_ESCUELA = [CONCEPTO_ACADEMICAS, CONCEPTO_CRONOLOGICAS, "Otras Actividades Pregrado"]
_RES = "_res_cecos"


def _resultado():
    res = st.session_state.pop(_RES, None)
    if res:
        (st.success if res[0] else st.error)(res[1], icon="✅" if res[0] else "🛑")


def _hecho(ok: bool, mensaje: str):
    st.session_state[_RES] = (ok, mensaje)
    st.rerun()


def vista_cecos(repo, deptos: list[tuple], usuario):
    st.caption("Qué centros de costo existen en cada facultad y dirección, quién puede "
               "presupuestarlos y cómo agregarlos. Un centro aparece en las planillas de un "
               "departamento cuando está **asignado** a ese departamento; en la ficha TC, "
               "cuando además está en su **estructura TC**.")
    _resultado()
    try:
        catalogo = repo.catalogo_cecos()
    except Exception as ex:
        st.warning(f"No se pudo leer el catálogo ({type(ex).__name__}: {ex}).", icon="⚠️")
        return
    puede_escribir = repo.gestion_cecos_disponible()
    parte = st.segmented_control(
        "Sección", ["🔎 Consultar", "✅ Verificar", "✏️ Actualizar", "🕘 Cambios"],
        default="🔎 Consultar", key="cecos_parte", label_visibility="collapsed")
    if parte == "✅ Verificar":
        _verificar(repo)
    elif parte == "✏️ Actualizar":
        if not puede_escribir:
            st.warning("Para actualizar desde aquí, ejecuta `sql/crear_gestion_cecos_2027.sql` en "
                       "Azure y pulsa «Actualizar datos ahora» en ⏱ Rendimiento.", icon="⚠️")
            return
        _actualizar(repo, catalogo, deptos, usuario)
    elif parte == "🕘 Cambios":
        if puede_escribir:
            st.dataframe(repo.auditoria_cecos(), hide_index=True, width="stretch",
                         column_config={"FECHA": st.column_config.DatetimeColumn(
                             "Fecha (Lima)", format="DD/MM/YYYY HH:mm"), "EMAIL": "Por",
                             "ACCION": "Acción", "DETALLE": "Detalle"})
        else:
            st.info("El registro de cambios empieza cuando se ejecute "
                    "`sql/crear_gestion_cecos_2027.sql`.", icon="ℹ️")
    else:
        _consultar(catalogo)


def _direcciones(catalogo) -> list[str]:
    dirs = sorted(d for d in catalogo["DIRECCION"].dropna().unique())
    return [d for d in dirs if d.upper().startswith("FACULTAD")] + \
           [d for d in dirs if not d.upper().startswith("FACULTAD")]


def _consultar(catalogo):
    c1, c2, c3 = st.columns([3, 3, 2], vertical_alignment="bottom")
    direccion = c1.selectbox("Facultad o dirección", ["Todas"] + _direcciones(catalogo),
                             key="cecos_dir")
    texto = c2.text_input("Buscar", placeholder="Código o descripción", key="cecos_buscar")
    solo = c3.toggle("Solo sin departamento", key="cecos_solo_sin")
    df = catalogo
    if direccion != "Todas":
        df = df[df["DIRECCION"] == direccion]
    if texto.strip():
        t = texto.strip().lower()
        df = df[df["CENTRO_COSTO"].str.lower().str.contains(t, regex=False)
                | df["DESCRIPCION_CC"].fillna("").str.lower().str.contains(t, regex=False)]
    if solo:
        df = df[df["DEPARTAMENTOS"].isna()]
    m = st.columns(4)
    m[0].metric("Centros", len(df))
    m[1].metric("Con departamento", int(df["DEPARTAMENTOS"].notna().sum()))
    m[2].metric("En alguna ficha TC", int(df["FICHA_TC"].notna().sum()))
    m[3].metric("Con datos 2027", int((pd.to_numeric(df["FILAS_2027"]) > 0).sum()))
    st.dataframe(
        df, hide_index=True, width="stretch",
        column_config={
            "CENTRO_COSTO": "Código", "DESCRIPCION_CC": st.column_config.TextColumn(
                "Descripción", width="large"), "DIRECCION": "Facultad o dirección",
            "DEPARTAMENTOS": "Pueden presupuestarlo", "FICHA_TC": "En la ficha TC de",
            "FILAS_2027": st.column_config.NumberColumn("Filas 2027", format="%d")})
    st.caption("Sin departamento: nadie puede presupuestarlo todavía. Asígnalo en "
               "✏️ Actualizar.")


def _verificar(repo):
    try:
        v = repo.verificacion_cecos()
    except Exception as ex:
        st.warning(f"No se pudo verificar ({type(ex).__name__}: {ex}).", icon="⚠️")
        return
    revisiones = [
        ("sin_departamento", "Centros de facultad sin departamento",
         "Nadie puede presupuestarlos. Si deben usarse en 2027, asígnalos en ✏️ Actualizar."),
        ("deptos_sin_cecos", "Departamentos sin centros asignados",
         "Sus planillas no tienen centros para elegir."),
        ("asignados_inexistentes", "Asignaciones a centros que no están en el catálogo",
         "Agrega el centro al catálogo (✏️ Actualizar › pegar desde Excel) o quita la asignación."),
        ("ficha_inexistentes", "Ficha TC con centros que no están en el catálogo",
         "Aparecen en la ficha sin descripción. Agrega el centro al catálogo o quítalo de la ficha."),
        ("datos_fuera", "Datos 2027 guardados con centros que el departamento no tiene",
         "Lo guardado no coincide con sus centros: asigna el centro al departamento o pide que "
         "corrijan la planilla."),
    ]
    problemas = sum(1 for k, _, _ in revisiones if not v[k].empty)
    if not problemas:
        st.success("Todo cuadra: catálogo, asignaciones, ficha TC y datos 2027.", icon="✅")
    for clave, titulo, ayuda in revisiones:
        df = v[clave]
        if df.empty:
            st.markdown(f"✅ **{titulo}:** ninguno.")
            continue
        with st.expander(f"⚠️ {titulo}: {len(df)}", expanded=True):
            st.caption(ayuda)
            st.dataframe(df, hide_index=True, width="stretch")


def leer_pegado(texto: str) -> list[list[str]]:
    """Filas pegadas desde Excel (columnas separadas por tabulador, o por «;»):
    código, descripción y, opcional, facultad o dirección. Se salta una fila de
    encabezados."""
    filas = []
    for linea in (texto or "").splitlines():
        if not linea.strip():
            continue
        partes = [p.strip() for p in (linea.split("\t") if "\t" in linea else linea.split(";"))]
        if not filas and not any(ch.isdigit() for ch in partes[0]):
            continue   # encabezados
        filas.append((partes + ["", "", ""])[:3])
    return filas


def revisar_pegado(filas, catalogo, direccion_defecto) -> pd.DataFrame:
    actual = catalogo.set_index("CENTRO_COSTO")
    vistos, salida = set(), []
    for codigo, desc, direccion in filas:
        direccion = direccion or ""
        if not CODIGO.fullmatch(codigo):
            res = "Error: el código debe ser como 01.01.07.01.02"
        elif codigo in vistos:
            res = "Error: código repetido en lo pegado"
        elif not desc:
            res = "Error: falta la descripción"
        elif codigo not in actual.index:
            direccion = direccion or direccion_defecto or ""
            res = "Nuevo" if direccion else "Error: falta la facultad o dirección"
        else:
            antes = actual.loc[codigo]
            nueva_dir = direccion or antes["DIRECCION"]
            if (antes["DESCRIPCION_CC"], antes["DIRECCION"]) == (desc, nueva_dir):
                res = "Sin cambios"
            else:
                res = f"Cambia (antes: {antes['DESCRIPCION_CC']} · {antes['DIRECCION']})"
        vistos.add(codigo)
        salida.append((codigo, desc, direccion, res))
    return pd.DataFrame(salida, columns=["Código", "Descripción", "Facultad o dirección",
                                         "Resultado"])


def _actualizar(repo, catalogo, deptos, usuario):
    nombres = dict(deptos)
    fmt_depto = lambda d: f"{d} · {nombres.get(d, '')}"
    desc = dict(zip(catalogo["CENTRO_COSTO"], catalogo["DESCRIPCION_CC"]))
    fmt_ceco = lambda c: f"{c} · {desc.get(c, '¿no está en el catálogo?')}"

    with st.expander("📋 Agregar o corregir centros: pegar desde Excel", expanded=True):
        st.caption("Copia en Excel las columnas **código**, **descripción** y, si quieres, "
                   "**facultad o dirección**, y pégalas aquí. Los códigos nuevos se agregan; los "
                   "que ya existen se corrigen. Nunca se borran centros.")
        ver = st.session_state.get("_ver_cecos_pegar", 0)
        texto = st.text_area("Filas copiadas de Excel", key=f"cecos_pegar_{ver}", height=130,
                             placeholder="01.01.07.01.06\tCENTRO NUEVO DE HUMANIDADES\t"
                                         "FACULTAD DE HUMANIDADES, MATEMÁTICA Y CIENCIAS NATURALES")
        c1, c2 = st.columns(2)
        direccion_defecto = c1.selectbox(
            "Facultad o dirección para los nuevos que no la traigan", [None] +
            _direcciones(catalogo), format_func=lambda d: d or "—", key="cecos_dir_defecto")
        asignar_a = c2.multiselect("Asignar todas las filas pegadas a", [d for d, _ in deptos],
                                   format_func=fmt_depto, key=f"cecos_asignar_pegado_{ver}",
                                   help="Para que esos departamentos puedan presupuestarlos ya. "
                                        "Vale para todas las filas, nuevas o corregidas.")
        filas = leer_pegado(texto)
        if filas:
            revision = revisar_pegado(filas, catalogo, direccion_defecto)
            st.dataframe(revision, hide_index=True, width="stretch")
            errores = revision["Resultado"].str.startswith("Error")
            cambios = revision[revision["Resultado"].str.match("Nuevo|Cambia")]
            if errores.any():
                st.error(f"Corrige {int(errores.sum())} fila(s) con error para continuar.",
                         icon="🛑")
            aplicar = [(r["Código"], r["Descripción"], r["Facultad o dirección"] or None)
                       for _, r in revision.iterrows()
                       if r["Resultado"].startswith(("Nuevo", "Cambia")) or asignar_a]
            if st.button(f"Aplicar ({len(cambios)} cambio(s) en el catálogo"
                         + (f", asignar a {len(asignar_a)} departamento(s)" if asignar_a else "")
                         + ")", type="primary", key="btn_cecos_pegar",
                         disabled=bool(errores.any()) or not aplicar):
                try:
                    r = repo.guardar_cecos(aplicar, asignar_a, usuario.email)
                    st.session_state["_ver_cecos_pegar"] = ver + 1
                    _hecho(True, f"Catálogo: {r['nuevos']} nuevo(s), {r['cambiados']} "
                                 f"corregido(s); {r['asignaciones']} asignación(es) nueva(s).")
                except Exception as ex:
                    _hecho(False, f"No se cambió nada; se revirtió la operación. Detalle: {ex}")

    with st.expander("🏢 Asignar o quitar centros a un departamento"):
        depto = st.selectbox("Departamento", [d for d, _ in deptos], format_func=fmt_depto,
                             key="cecos_asig_depto")
        asignados = catalogo[catalogo["DEPARTAMENTOS"].fillna("").str.split(", ")
                             .apply(lambda l: depto in l)]
        st.caption(f"{depto} tiene {len(asignados)} centro(s) asignado(s).")
        # Por defecto se ofrecen los de su facultad (la más común entre sus centros)
        dirs = _direcciones(catalogo)
        comun = asignados["DIRECCION"].mode()
        direccion = st.selectbox("Mostrar centros de", ["Todas"] + dirs, key=f"cecos_asig_dir_{depto}",
                                 index=(dirs.index(comun.iloc[0]) + 1) if len(comun) else 0)
        libres = catalogo[~catalogo["CENTRO_COSTO"].isin(asignados["CENTRO_COSTO"])]
        if direccion != "Todas":
            libres = libres[libres["DIRECCION"] == direccion]
        c1, c2 = st.columns(2)
        poner = c1.multiselect("Centros para asignar", list(libres["CENTRO_COSTO"]),
                               format_func=fmt_ceco, key=f"cecos_poner_{depto}")
        if c1.button("Asignar", type="primary", disabled=not poner, key="btn_cecos_asignar",
                     width="stretch"):
            r = repo.asignar_cecos([depto], poner, False, usuario.email)
            _hecho(True, f"{r['hechos']} centro(s) asignado(s) a {depto}.")
        sacar = c2.multiselect("Centros para quitar", list(asignados["CENTRO_COSTO"]),
                               format_func=fmt_ceco, key=f"cecos_sacar_{depto}")
        if c2.button("Quitar", disabled=not sacar, key="btn_cecos_quitar", width="stretch"):
            r = repo.asignar_cecos([depto], sacar, True, usuario.email)
            msg = f"{r['hechos']} centro(s) quitado(s) de {depto}."
            if r["con_datos"]:
                msg += (" No se quitaron porque ya tienen datos 2027: "
                        + ", ".join(r["con_datos"]) + ".")
            _hecho(not r["con_datos"] or r["hechos"] > 0, msg)

    with st.expander("🧾 Ficha TC: agregar o quitar un centro"):
        st.caption("La ficha TC muestra, por docente, los centros y conceptos de la estructura "
                   "del departamento. Al agregar un centro aquí, también queda asignado al "
                   "departamento.")
        c1, c2 = st.columns(2)
        depto_f = c1.selectbox("Departamento", [d for d, _ in deptos], format_func=fmt_depto,
                               key="cecos_ficha_depto")
        ceco = c2.selectbox("Centro de costo", list(catalogo["CENTRO_COSTO"]),
                            format_func=fmt_ceco, index=None, placeholder="Elige un centro",
                            key="cecos_ficha_ceco")
        plantilla = st.radio(
            "Conceptos", ["Escuela: horas de dictado (académicas y cronológicas) y otras "
                          "actividades", "Un solo concepto de horas (gestión, investigación, "
                          "proyectos, centros…)"], key="cecos_ficha_plantilla")
        concepto = ""
        if plantilla.startswith("Un solo"):
            concepto = st.text_input("Nombre del concepto", key="cecos_ficha_concepto",
                                     value=(desc.get(ceco) or "").capitalize() if ceco else "",
                                     help="Como se verá en la ficha, por ejemplo «Gestión "
                                          "Administrativa Pregrado».")
        conceptos = CONCEPTOS_ESCUELA if plantilla.startswith("Escuela") else (
            [concepto.strip()] if concepto.strip() else [])
        if st.button("Agregar a la ficha TC", type="primary", key="btn_cecos_ficha",
                     disabled=not ceco or not conceptos):
            n = repo.agregar_ceco_ficha(depto_f, ceco, conceptos, usuario.email)
            _hecho(True, f"{ceco} en la ficha TC de {depto_f}: {n} concepto(s) agregado(s). Quien "
                         "tenga la ficha abierta debe recargar la página.")
        en_ficha = catalogo[catalogo["FICHA_TC"].fillna("").str.split(", ")
                            .apply(lambda l: depto_f in l)]["CENTRO_COSTO"]
        quitar = st.selectbox("Quitar de la ficha TC de " + depto_f, list(en_ficha),
                              format_func=fmt_ceco, index=None, placeholder="Elige un centro",
                              key=f"cecos_ficha_quitar_{depto_f}")
        if st.button("Quitar de la ficha", disabled=not quitar, key="btn_cecos_ficha_quitar"):
            n = repo.quitar_ceco_ficha(depto_f, quitar, usuario.email)
            if n < 0:
                _hecho(False, f"No se quitó: el plan TC 2027 de {depto_f} ya tiene horas en "
                              f"{quitar}. Primero que las pasen a otro centro.")
            _hecho(True, f"{quitar} quitado de la ficha TC de {depto_f} ({n} concepto(s)).")
