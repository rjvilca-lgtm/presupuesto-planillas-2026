"""
Desarrollo Humano: lista de docentes TC con sus horas, tarifas y salarios 2027.

Docentes y salarios se actualizan SOLO subiendo el Excel de la plantilla
(src/plantillas.py): el archivo es la lista completa, la app valida y muestra
altas, bajas y cambios antes de guardar. Las tarifas (4 valores) se editan en
pantalla.

Salarios (Remuneraciones_2027) son confidenciales:
  - solo los ve el rol DESARROLLO_HUMANO (ni siquiera Presupuesto);
  - se leen directo de la base, sin caché compartida, y nunca se imprimen en logs;
  - los montos están ocultos hasta que el usuario pide mostrarlos;
  - la plantilla se descarga sin montos y el archivo subido no se guarda;
  - cada carga queda en AUDITORIA_DESARROLLO_HUMANO con quién, cuándo y qué
    campos cambiaron por docente (nunca los montos).
Opcional: con [sql_rrhh] en los secrets, los salarios se leen y escriben con un
login de base de datos propio (el único con permisos sobre Remuneraciones_2027).
"""

import pandas as pd
import streamlit as st

from .plantillas import (ETIQUETAS_SALARIO, diferencias, leer_docentes, leer_salarios,
                         plantilla_docentes, plantilla_salarios, unificar_dni)
from .repositorio import COLS_REMUNERACION, DATOS_REMUNERACION

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def vista_desarrollo_humano(repo, usuario, deptos):
    t_doc, t_sal, t_tar, t_aud = st.tabs(
        ["Docentes y horas", "🔒 Salarios", "Tarifas", "Registro de cambios"])
    with t_doc:
        _docentes(repo, usuario, deptos)
    with t_sal:
        _salarios(repo, usuario)
    with t_tar:
        _tarifas(repo, usuario)
    with t_aud:
        st.caption("Últimos cambios de Desarrollo Humano. En salarios solo se registra qué "
                   "campos cambiaron, nunca los montos.")
        st.dataframe(repo.auditoria_dh(), hide_index=True, width="stretch")


def _mostrar_resultado(clave):
    res = st.session_state.pop(clave, None)
    if res:
        (st.success if res[0] else st.error)(res[1], icon="✅" if res[0] else "🛑")


def _resumen_movimientos(mov: pd.DataFrame) -> dict:
    return {m: int((mov["Movimiento"] == m).sum())
            for m in ("Alta", "Baja", "Cambio", "Sin cambios")}


def _confirmar_carga(clave: str, mov: pd.DataFrame, que: str) -> bool:
    """Muestra las diferencias y el botón de confirmar. Las bajas exigen marcar
    una casilla aparte."""
    r = _resumen_movimientos(mov)
    c = st.columns(4)
    for col, (k, v) in zip(c, r.items()):
        col.metric(k + ("s" if k != "Sin cambios" else ""), v)
    st.dataframe(mov[mov["Movimiento"] != "Sin cambios"], hide_index=True, width="stretch")
    acepta_bajas = True
    if r["Baja"]:
        acepta_bajas = st.checkbox(
            f"Confirmo que los {r['Baja']} docente(s) que no están en el archivo se dan de "
            f"baja de {que}.", key=f"bajas_{clave}")
    sin_cambios = r["Alta"] + r["Baja"] + r["Cambio"] == 0
    if sin_cambios:
        st.info("El archivo no trae cambios.", icon="ℹ️")
    return st.button("Confirmar y guardar", type="primary", key=f"conf_{clave}",
                     disabled=sin_cambios or not acepta_bajas)


# ------------------------------------------------------------ docentes

def _docentes(repo, usuario, deptos):
    st.caption("Docentes a tiempo completo por departamento y sus horas cronológicas "
               "(40, o menos si tienen carga parcial). Es el padrón que ven los "
               "departamentos en el Plan de trabajo TC. Se actualiza solo con el Excel.")
    _mostrar_resultado("_res_docentes")
    codigos = [d for d, _ in deptos]
    actual, _ = unificar_dni(repo.horas_docentes_todos())

    c1, c2 = st.columns([1, 2], vertical_alignment="bottom")
    c1.download_button("⬇ Descargar plantilla (lista actual)",
                       plantilla_docentes(actual, codigos),
                       file_name="docentes_horas_2027.xlsx", mime=XLSX, width="stretch")
    archivo = c2.file_uploader("Subir Excel de docentes y horas", type=["xlsx"],
                               key=f"up_docentes_{st.session_state.get('_ver_docentes', 0)}")

    if archivo is None:
        st.dataframe(actual.rename(columns={"DPTO": "Departamento", "NOMBRE": "Docente",
                                            "HORAS": "Horas"}),
                     hide_index=True, width="stretch")
        st.caption(f"{len(actual)} docente(s).")
        return

    nuevo, errores = leer_docentes(archivo, set(codigos))
    if errores:
        st.error("El archivo tiene errores; corrígelos y vuelve a subirlo:", icon="⚠️")
        for e in errores:
            st.markdown(f"- {e}")
        return
    mov = diferencias(actual, nuevo, ["DPTO", "NOMBRE", "HORAS"], "NOMBRE")
    st.subheader("Revisa los cambios")
    if _confirmar_carga("docentes", mov, "la lista de docentes TC"):
        filas = [[r.DPTO, r.DNI, r.NOMBRE, float(r.HORAS)] for r in nuevo.itertuples(index=False)]
        try:
            n = repo.guardar_horas_docentes(filas, usuario.email, mov)
            st.session_state["_res_docentes"] = (True, f"Lista actualizada: {n} docente(s).")
        except Exception as ex:
            st.session_state["_res_docentes"] = (False, f"No se guardó nada. Detalle: {ex}")
        st.session_state["_ver_docentes"] = st.session_state.get("_ver_docentes", 0) + 1
        st.rerun()


# ------------------------------------------------------------ salarios

def _salarios(repo, usuario):
    st.warning("**Información confidencial.** Solo Desarrollo Humano ve esta sección. "
               "Cada carga queda registrada con tu correo y la fecha (sin los montos). "
               "No compartas capturas ni el Excel con montos.", icon="🔒")
    _mostrar_resultado("_res_salarios")
    try:
        actual = repo.remuneraciones()
    except Exception as ex:
        st.error("No se pudieron leer los salarios 2027. ¿Ya se ejecutó "
                 f"`sql/crear_rol_desarrollo_humano.sql`? Detalle: {type(ex).__name__}")
        return
    actual, duplicados = unificar_dni(actual)
    actual["TOTAL"] = actual[COLS_REMUNERACION].fillna(0.0).sum(axis=1)
    if duplicados:
        st.info(f"Hay {duplicados} salario(s) repetidos con el DNI sin el cero inicial "
                "(p. ej. 1292586 y 01292586). Se muestran una vez; la próxima carga del "
                "Excel deja solo la versión de 8 dígitos.", icon="ℹ️")

    padron = repo.horas_docentes_todos()
    sin_salario = padron[~padron["DNI"].astype(str).str.strip().isin(actual["DNI"])]
    if not sin_salario.empty:
        st.error(f"{len(sin_salario)} docente(s) del padrón TC no tienen salario 2027 "
                 "(su sueldo saldría en 0 al valorizar): "
                 + ", ".join(f"{r.NOMBRE} ({r.DPTO})" for r in sin_salario.itertuples()),
                 icon="⚠️")

    c1, c2 = st.columns([1, 2], vertical_alignment="bottom")
    # La plantilla lleva quiénes tienen salario, sin montos, más los del padrón sin salario
    identidad = pd.concat([
        actual[DATOS_REMUNERACION],
        sin_salario.rename(columns={"NOMBRE": "Nombre"}).assign(Categoria=None)[
            DATOS_REMUNERACION]], ignore_index=True)
    c1.download_button("⬇ Descargar plantilla (sin montos)", plantilla_salarios(identidad),
                       file_name="salarios_2027.xlsx", mime=XLSX, width="stretch")
    archivo = c2.file_uploader("Subir Excel de salarios", type=["xlsx"],
                               key=f"up_salarios_{st.session_state.get('_ver_salarios', 0)}")

    mostrar = st.toggle("Mostrar montos", value=False, key="mostrar_montos")
    if archivo is None:
        vista = actual[["DNI", "Nombre", "Categoria", "DPTO", "TOTAL"]].copy()
        if not mostrar:
            vista["TOTAL"] = "••••••"
        st.dataframe(vista.rename(columns={"Nombre": "Docente", "Categoria": "Categoría",
                                           "DPTO": "Departamento", "TOTAL": "Total mensual"}),
                     hide_index=True, width="stretch",
                     column_config={"Total mensual": st.column_config.NumberColumn(
                         format="localized")} if mostrar else None)
        st.caption(f"{len(actual)} docente(s) con salario 2027.")
        return

    nuevo, errores = leer_salarios(archivo)
    if errores:
        st.error("El archivo tiene errores; corrígelos y vuelve a subirlo:", icon="⚠️")
        for e in errores:
            st.markdown(f"- {e}")
        return
    mov = diferencias(actual, nuevo, ["Nombre", "Categoria", "DPTO"] + COLS_REMUNERACION,
                      "Nombre")
    mov["Campos que cambian"] = mov["Campos que cambian"].map(
        lambda t: ", ".join(ETIQUETAS_SALARIO.get(c, c) for c in t.split(", ")) if t else "")
    if mostrar:
        tot_a = actual.set_index("DNI")["TOTAL"]
        tot_n = nuevo.set_index("DNI")[COLS_REMUNERACION].sum(axis=1)
        mov["Total actual"] = mov["DNI"].map(tot_a)
        mov["Total nuevo"] = mov["DNI"].map(tot_n)
    st.subheader("Revisa los cambios")
    if _confirmar_carga("salarios", mov, "los salarios 2027"):
        filas = [[r.DNI, r.Nombre, r.Categoria, r.DPTO] + [float(getattr(r, c)) for c in
                                                           COLS_REMUNERACION]
                 for r in nuevo.itertuples(index=False)]
        try:
            n = repo.reemplazar_remuneraciones(filas, mov[["DNI", "Docente", "Movimiento",
                                                           "Campos que cambian"]], usuario.email)
            st.session_state["_res_salarios"] = (True, f"Salarios actualizados: {n} docente(s). "
                                                       "Recuerda borrar el archivo de tu equipo.")
        except Exception as ex:
            st.session_state["_res_salarios"] = (False, "No se guardó nada. Detalle: "
                                                        f"{type(ex).__name__}")
        st.session_state["_ver_salarios"] = st.session_state.get("_ver_salarios", 0) + 1
        st.rerun()


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
