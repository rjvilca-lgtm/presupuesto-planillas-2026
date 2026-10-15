"""
Desarrollo Humano: lista de docentes TC con sus horas, tarifas y salarios 2027.

Salarios (Remuneraciones_2027) son confidenciales:
  - solo los ve el rol DESARROLLO_HUMANO (ni siquiera Presupuesto);
  - se leen directo de la base, sin caché compartida, y nunca se imprimen en logs;
  - los montos están ocultos hasta que el usuario pide mostrarlos;
  - no hay descarga;
  - cada alta, cambio o baja queda en AUDITORIA_DESARROLLO_HUMANO con quién y
    cuándo, y solo los NOMBRES de los campos (no los montos).
Opcional: con [sql_rrhh] en los secrets, los salarios se leen y escriben con un
login de base de datos propio (el único con permisos sobre Remuneraciones_2027).
"""

import re

import pandas as pd
import streamlit as st

from .repositorio import COLS_REMUNERACION

_DOC = re.compile(r"\d{8}|[0-9A-Za-z]{9,12}")


def _etiqueta(col: str) -> str:
    return col.replace("_", " ").replace("Bonificacion", "Bonificación").replace(
        "Basico", "Básico").replace("Asignacion", "Asignación")


def vista_desarrollo_humano(repo, usuario, deptos):
    t_doc, t_tar, t_sal, t_aud = st.tabs(
        ["Docentes y horas", "Tarifas", "🔒 Salarios", "Registro de cambios"])
    with t_doc:
        _docentes(repo, usuario, deptos)
    with t_tar:
        _tarifas(repo, usuario)
    with t_sal:
        _salarios(repo, usuario, deptos)
    with t_aud:
        st.caption("Últimos cambios de Desarrollo Humano. En salarios solo se registra qué "
                   "campos cambiaron, nunca los montos.")
        st.dataframe(repo.auditoria_dh(), hide_index=True, width="stretch")


def _mostrar_resultado(clave):
    res = st.session_state.pop(clave, None)
    if res:
        (st.success if res[0] else st.error)(res[1], icon="✅" if res[0] else "🛑")


# ------------------------------------------------------------ docentes

def _docentes(repo, usuario, deptos):
    st.caption("Docentes a tiempo completo por departamento y sus horas cronológicas "
               "(40, o menos si tienen carga parcial). Es el padrón que ven los "
               "departamentos en el Plan de trabajo TC y el total que debe sumar cada "
               "docente.")
    _mostrar_resultado("_res_docentes")
    codigos = [d for d, _ in deptos]
    if "_base_docentes" not in st.session_state:
        st.session_state["_base_docentes"] = repo.horas_docentes_todos()
    editado = st.data_editor(
        st.session_state["_base_docentes"], num_rows="dynamic", hide_index=True,
        width="stretch", key=f"ed_docentes_{st.session_state.get('_ver_docentes', 0)}",
        column_config={
            "DPTO": st.column_config.SelectboxColumn("Departamento", options=codigos,
                                                     required=True),
            "DNI": st.column_config.TextColumn("DNI", required=True),
            "NOMBRE": st.column_config.TextColumn("Docente", width="large", required=True),
            "HORAS": st.column_config.NumberColumn("Horas", min_value=1, max_value=40,
                                                   step=0.5, required=True),
        })
    st.caption(f"{len(editado)} docente(s). Los cambios llegan a los departamentos la "
               "próxima vez que abran su Plan de trabajo TC.")
    if st.button("Guardar docentes y horas", type="primary", key="btn_guardar_docentes"):
        errores = _validar_docentes(editado, set(codigos))
        if errores:
            for e in errores:
                st.error(e, icon="⚠️")
            return
        filas = [[r.DPTO, str(r.DNI).strip(), str(r.NOMBRE).strip(), float(r.HORAS)]
                 for r in editado.itertuples(index=False)]
        try:
            n = repo.guardar_horas_docentes(filas, usuario.email)
            st.session_state["_res_docentes"] = (True, f"{n} docente(s) guardados.")
            st.session_state.pop("_base_docentes", None)
            st.session_state["_ver_docentes"] = st.session_state.get("_ver_docentes", 0) + 1
        except Exception as ex:
            st.session_state["_res_docentes"] = (False, f"No se guardó nada. Detalle: {ex}")
        st.rerun()


def _validar_docentes(df, codigos) -> list[str]:
    errores = []
    df = df.dropna(how="all")
    if df[["DPTO", "DNI", "NOMBRE", "HORAS"]].isna().any().any() or \
            (df["NOMBRE"].astype(str).str.strip() == "").any():
        errores.append("Hay filas incompletas: departamento, DNI, nombre y horas son obligatorios.")
    dni = df["DNI"].dropna().astype(str).str.strip()
    malos = sorted(d for d in dni if not _DOC.fullmatch(d))
    if malos:
        errores.append("DNI inválidos (8 dígitos, o 9 a 12 caracteres si es carné de "
                       "extranjería): " + ", ".join(malos[:10]))
    repetidos = sorted(set(dni[dni.duplicated()]))
    if repetidos:
        errores.append("DNI repetidos: " + ", ".join(repetidos[:10]))
    fuera = set(df["DPTO"].dropna()) - codigos
    if fuera:
        errores.append("Departamentos que no existen: " + ", ".join(sorted(fuera)))
    horas = pd.to_numeric(df["HORAS"], errors="coerce")
    if ((horas < 1) | (horas > 40)).any():
        errores.append("Las horas deben estar entre 1 y 40.")
    return errores


# ------------------------------------------------------------- tarifas

def _tarifas(repo, usuario):
    st.caption("Tarifas por hora 2027. Las usan Horas adicionales (como valor por defecto "
               "de la tarifa), Ayudantías y la Carga académica. Un cambio se aplica a "
               "partir de la próxima valorización.")
    _mostrar_resultado("_res_tarifas")
    base = repo.tarifas_todas()
    editado = st.data_editor(
        base, hide_index=True, width="stretch", num_rows="fixed",
        key=f"ed_tarifas_{st.session_state.get('_ver_tarifas', 0)}",
        column_config={
            "HOJA_ORIGEN": st.column_config.TextColumn("Planilla", disabled=True),
            "TIPO": st.column_config.TextColumn("Tipo", disabled=True),
            "TARIFA": st.column_config.NumberColumn("Tarifa (S/)", min_value=0.01,
                                                    format="%.2f", required=True),
        })
    cambios = [(b.HOJA_ORIGEN, b.TIPO, b.TARIFA, e.TARIFA)
               for b, e in zip(base.itertuples(), editado.itertuples())
               if pd.notna(e.TARIFA) and abs(float(e.TARIFA) - float(b.TARIFA)) > 1e-9]
    if st.button("Guardar tarifas", type="primary", disabled=not cambios,
                 key="btn_guardar_tarifas"):
        try:
            repo.guardar_tarifas(cambios, usuario.email)
            st.session_state["_res_tarifas"] = (True, f"{len(cambios)} tarifa(s) actualizadas.")
            st.session_state["_ver_tarifas"] = st.session_state.get("_ver_tarifas", 0) + 1
        except Exception as ex:
            st.session_state["_res_tarifas"] = (False, f"No se guardó nada. Detalle: {ex}")
        st.rerun()


# ------------------------------------------------------------ salarios

def _salarios(repo, usuario, deptos):
    st.warning("**Información confidencial.** Solo Desarrollo Humano ve esta sección. "
               "Cada cambio queda registrado con tu correo y la fecha (sin los montos). "
               "No compartas capturas de esta pantalla.", icon="🔒")
    _mostrar_resultado("_res_salarios")
    try:
        sal = repo.remuneraciones()
    except Exception as ex:
        st.error(f"No se pudieron leer los salarios 2027. ¿Ya se ejecutó "
                 f"`sql/crear_rol_desarrollo_humano.sql`? Detalle: {type(ex).__name__}")
        return
    sal["TOTAL"] = sal[COLS_REMUNERACION].fillna(0.0).sum(axis=1)

    # Coherencia con el padrón: sin salario, el sueldo TC del docente sale en 0
    padron = repo.horas_docentes_todos()
    sin_salario = padron[~padron["DNI"].isin(sal["DNI"])]
    if not sin_salario.empty:
        st.error(f"{len(sin_salario)} docente(s) del padrón TC no tienen salario 2027 "
                 "(su sueldo saldría en 0 al valorizar): "
                 + ", ".join(f"{r.NOMBRE} ({r.DPTO})" for r in sin_salario.itertuples()),
                 icon="⚠️")
    sin_padron = sal[~sal["DNI"].isin(padron["DNI"])]
    if not sin_padron.empty:
        with st.expander(f"{len(sin_padron)} salario(s) de personas que no están en el "
                         "padrón TC (no se usan al valorizar)"):
            st.dataframe(sin_padron[["DNI", "Nombre", "DPTO"]], hide_index=True,
                         width="stretch")

    mostrar = st.toggle("Mostrar montos", value=False, key="mostrar_montos")
    vista = sal[["DNI", "Nombre", "Categoria", "DPTO", "TOTAL"]].copy()
    if not mostrar:
        vista["TOTAL"] = "••••••"
    st.dataframe(vista.rename(columns={"Nombre": "Docente", "Categoria": "Categoría",
                                       "DPTO": "Departamento", "TOTAL": "Total mensual"}),
                 hide_index=True, width="stretch",
                 column_config={"Total mensual": st.column_config.NumberColumn(
                     format="localized")} if mostrar else None)

    st.divider()
    modo = st.segmented_control("Acción", ["Modificar", "Agregar docente", "Quitar docente"],
                                default="Modificar", key="modo_salarios") or "Modificar"
    if modo == "Modificar":
        dni = st.selectbox("Docente", sal["DNI"].tolist(), index=None,
                           placeholder="Busca por nombre o DNI",
                           format_func=lambda d: f"{sal.loc[sal.DNI == d, 'Nombre'].iloc[0]} · {d}")
        if dni:
            _form_salario(repo, usuario, sal[sal["DNI"] == dni].iloc[0].to_dict(), nuevo=False)
    elif modo == "Agregar docente":
        _form_salario(repo, usuario, {"DNI": ""}, nuevo=True,
                      existentes=set(sal["DNI"]))
    else:
        dni = st.selectbox("Docente a quitar", sal["DNI"].tolist(), index=None,
                           format_func=lambda d: f"{sal.loc[sal.DNI == d, 'Nombre'].iloc[0]} · {d}")
        if dni and st.button("Quitar su salario 2027", type="primary"):
            repo.eliminar_remuneracion(dni, usuario.email)
            st.session_state["_res_salarios"] = (True, "Salario quitado.")
            st.rerun()


def _form_salario(repo, usuario, fila: dict, nuevo: bool, existentes=frozenset()):
    with st.form(f"form_salario_{fila.get('DNI') or 'nuevo'}"):
        c1, c2, c3, c4 = st.columns(4)
        dni = c1.text_input("DNI", value=fila.get("DNI") or "", disabled=not nuevo)
        nombre = c2.text_input("Nombre", value=fila.get("Nombre") or "")
        categoria = c3.text_input("Categoría", value=fila.get("Categoria") or "")
        dpto = c4.text_input("Departamento", value=fila.get("DPTO") or "")
        valores = {}
        cols = st.columns(4)
        for i, c in enumerate(COLS_REMUNERACION):
            actual = fila.get(c)
            valores[c] = cols[i % 4].number_input(
                _etiqueta(c), min_value=0.0, step=10.0, format="%.2f",
                value=float(actual) if actual is not None and pd.notna(actual) else 0.0)
        st.caption(f"Total mensual: S/ {sum(valores.values()):,.2f}")
        if not st.form_submit_button("Guardar", type="primary"):
            return
    dni = dni.strip()
    if nuevo and (not _DOC.fullmatch(dni) or dni in existentes):
        st.error("DNI inválido o ya registrado.")
        return
    if not nombre.strip():
        st.error("El nombre es obligatorio.")
        return
    datos = {"Nombre": nombre.strip(), "Categoria": categoria.strip() or None,
             "DPTO": dpto.strip() or None}
    if nuevo:
        datos.update(valores)
    else:
        # Solo los campos que cambiaron (es lo que se audita)
        for c, v in valores.items():
            antes = fila.get(c)
            antes = float(antes) if antes is not None and pd.notna(antes) else 0.0
            if abs(v - antes) > 1e-9:
                datos[c] = v
        for c in ("Nombre", "Categoria", "DPTO"):
            if (datos[c] or None) == (fila.get(c) or None):
                datos.pop(c)
        if not datos:
            st.info("No hay cambios.")
            return
    try:
        repo.guardar_remuneracion(dni, datos, usuario.email, nuevo)
        st.session_state["_res_salarios"] = (True, "Salario guardado.")
    except Exception as ex:
        st.session_state["_res_salarios"] = (False, f"No se guardó. Detalle: {type(ex).__name__}")
    st.rerun()
