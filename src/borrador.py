"""
Cambios sin guardar y guardado automático del borrador.

Cada planilla calcula una "firma" de lo que hay en pantalla (solo las celdas
con valor). La primera firma de la sesión es lo que se cargó de la base; si
la de ahora es distinta, hay cambios sin guardar: se muestra un indicador y
el navegador pide confirmación antes de cerrar o recargar la página.

Guardado automático: si hay cambios sin guardar desde hace AUTOGUARDADO_SEG,
en la siguiente edición se guarda el borrador solo (si pasa las validaciones
de guardado). Es seguro porque guardar no valoriza.

Guardados simultáneos: al abrir una planilla se anota su versión guardada
(GUARDADOS_2027). Si otra persona la guarda mientras tanto, el guardado de
esta sesión se rechaza (ConflictoGuardado): se avisa quién y cuándo, se
detiene el guardado automático y se ofrece recargar la planilla.
"""

import hashlib
import time

import pandas as pd
import streamlit as st

# Con un corte de red largo Streamlit puede perder la sesión: así se pierde como
# máximo un minuto de trabajo
AUTOGUARDADO_SEG = 60


def firma(df: pd.DataFrame, ids: list[str], valores: list[str]) -> str:
    """Huella de las celdas con valor (> 0), sin importar el orden de las filas."""
    ids = [c for c in ids if c in df.columns]
    valores = [c for c in valores if c in df.columns]
    if df.empty or not valores:
        return ""
    largo = df[ids + valores].melt(id_vars=ids, value_vars=valores, var_name="_c",
                                   value_name="_v")
    largo["_v"] = pd.to_numeric(largo["_v"], errors="coerce").round(2)
    largo = largo[largo["_v"] > 0]
    for c in ids:
        v = largo[c]
        largo[c] = (pd.to_numeric(v, errors="coerce").round(2).astype(str)
                    if c == "TARIFA" else v.fillna("").astype(str).str.strip())
    filas = sorted(map(tuple, largo.astype(str).values.tolist()))
    return hashlib.sha1(repr(filas).encode()).hexdigest()


def _k(clave: str, que: str) -> str:
    return f"_borrador_{que}_{clave}"


def pendiente(clave: str, firma_actual: str) -> bool:
    """¿Hay cambios sin guardar? La primera firma de la sesión es la base."""
    base = st.session_state.setdefault(_k(clave, "firma"), firma_actual)
    hay = firma_actual != base
    desde = _k(clave, "desde")
    if hay:
        st.session_state.setdefault(desde, time.time())
    else:
        st.session_state.pop(desde, None)
    st.session_state.setdefault("_borrador_pendientes", {})[clave] = hay
    return hay


def marcar_guardado(clave: str, firma_actual: str):
    st.session_state[_k(clave, "firma")] = firma_actual
    st.session_state.pop(_k(clave, "desde"), None)
    st.session_state[_k(clave, "hora")] = time.strftime("%H:%M")
    st.session_state.setdefault("_borrador_pendientes", {})[clave] = False


def olvidar(clave: str):
    """Para cuando la pantalla se recarga desde la base."""
    for que in ("firma", "desde", "hora"):
        st.session_state.pop(_k(clave, que), None)
    st.session_state.get("_borrador_pendientes", {}).pop(clave, None)


def toca_autoguardar(clave: str) -> bool:
    if st.session_state.get(_k(clave, "conflicto")):
        return False
    desde = st.session_state.get(_k(clave, "desde"))
    return desde is not None and time.time() - desde >= AUTOGUARDADO_SEG


# ----------------------------------------------------- guardados simultáneos

def registrar_version(repo, hoja: str, origen: str):
    """Anota la versión guardada al abrir la planilla (una vez por sesión)."""
    clave = f"{hoja}|{origen}"
    if _k(clave, "version") not in st.session_state:
        st.session_state[_k(clave, "version")] = repo.version_planilla(hoja, origen)


def version(hoja: str, origen: str):
    return st.session_state.get(_k(f"{hoja}|{origen}", "version"))


def fijar_version(hoja: str, origen: str, valor):
    st.session_state[_k(f"{hoja}|{origen}", "version")] = valor


def hay_conflicto(hoja: str, origen: str) -> bool:
    return bool(st.session_state.get(_k(f"{hoja}|{origen}", "conflicto")))


def marcar_conflicto(hoja: str, origen: str, mensaje: str):
    st.session_state[_k(f"{hoja}|{origen}", "conflicto")] = mensaje


def mostrar_conflicto(hoja: str, origen: str, claves_estado: list[str],
                      prefijos_estado: tuple = ()) -> bool:
    """Si hubo conflicto, lo muestra con el botón para recargar desde la base.
    claves_estado / prefijos_estado: lo que la pantalla guarda en la sesión
    para esa planilla (se borra al recargar)."""
    clave = f"{hoja}|{origen}"
    mensaje = st.session_state.get(_k(clave, "conflicto"))
    if not mensaje:
        return False
    st.error(mensaje, icon="👥")
    if st.button("Recargar la planilla con lo último guardado", type="primary",
                 key=f"btn_recargar_{clave}"):
        for k in list(st.session_state.keys()):
            if k in claves_estado or (prefijos_estado and str(k).startswith(prefijos_estado)):
                del st.session_state[k]
        for que in ("version", "conflicto", "error"):
            st.session_state.pop(_k(clave, que), None)
        olvidar(clave)
        st.rerun()
    return True


def autoguardar(clave: str, firma_actual: str, errores: list[str], guardar) -> None:
    """Guarda solo si no hay errores; si los hay, lo deja anotado para el indicador.
    guardar() -> (ok, mensaje)."""
    if errores:
        st.session_state[_k(clave, "error")] = True
        st.session_state[_k(clave, "desde")] = time.time()   # reintenta más tarde
        return
    st.session_state.pop(_k(clave, "error"), None)
    ok, _ = guardar()
    if ok:
        marcar_guardado(clave, firma_actual)
        st.toast("Borrador guardado automáticamente.", icon="💾")
    else:
        st.session_state[_k(clave, "desde")] = time.time()


def indicador(clave: str, hay_cambios: bool, solo_lectura: bool = False) -> str:
    """Texto corto para junto al botón Guardar."""
    if solo_lectura:
        return ""
    if hay_cambios:
        if st.session_state.get(_k(clave, "error")):
            return ("⚠️ Cambios sin guardar · el guardado automático se detuvo por "
                    "observaciones: pulsa Guardar para verlas")
        return ("● Cambios sin guardar · se guardan solos cada minuto mientras "
                "editas, o pulsa Guardar")
    hora = st.session_state.get(_k(clave, "hora"))
    return f"✓ Todo guardado{' (' + hora + ')' if hora else ''}"


def mostrar_indicador(clave: str, hay_cambios: bool, solo_lectura: bool = False):
    texto = indicador(clave, hay_cambios, solo_lectura)
    if texto:
        color = "#B54708" if hay_cambios else "#067647"
        st.markdown(f'<div style="color:{color};font-size:.85rem;margin:.2rem 0">{texto}</div>',
                    unsafe_allow_html=True)


def aviso_al_salir():
    """Si alguna planilla tiene cambios sin guardar, el navegador pide
    confirmación antes de cerrar o recargar la pestaña."""
    activo = any(st.session_state.get("_borrador_pendientes", {}).values())
    st.iframe(f"""<script>
      const w = window.parent;
      w.__pptoCambios = {str(activo).lower()};
      if (!w.__pptoAviso) {{
        w.__pptoAviso = true;
        w.addEventListener('beforeunload', e => {{
          if (w.__pptoCambios) {{ e.preventDefault(); e.returnValue = ''; }}
        }});
      }}
    </script>""", height=1)
