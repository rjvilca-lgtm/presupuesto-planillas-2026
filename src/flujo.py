"""
Flujo del presupuesto: borradores, valorización, cierre y bloqueos.

  1. Cada departamento guarda borradores de sus planillas las veces que quiera
     (no se valoriza al guardar).
  2. Cuando termina, valoriza todo su departamento desde "Resumen y
     valorización"; puede volver a modificar y valorizar las veces que quiera.
  3. DHUM, DMAT y DCN (DEPTOS_PRIMERO) además deben CERRAR: solo cuando los tres
     cerraron, la DGA puede valorizar la carga académica.
  4. Presupuesto fija una fecha de bloqueo; desde esa fecha los departamentos
     quedan bloqueados y Presupuesto los desbloquea o bloquea uno por uno.
     También reabre a los que cerraron.

El estado vive en ESTADO_DEPARTAMENTO y CONFIG_PRESUPUESTO
(sql/crear_estado_presupuesto.sql). Si esas tablas aún no existen, la app
funciona sin bloqueos y lo avisa en la pestaña de administración.
"""

import hmac
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from html import escape

import pandas as pd
import streamlit as st

from .config import CARGA_ACADEMICA, DEPTOS_PRIMERO, PLANILLAS, cfg_de
from .repositorio import matriz_desde_entrada, sps_departamento
from .validacion import estimar_importe, formato_soles, total_horas, validar

# Perú no tiene horario de verano: UTC-5 fijo, sin depender de tzdata
LIMA = timezone(timedelta(hours=-5))
DGA = CARGA_ACADEMICA["origen"]


def ahora() -> datetime:
    return datetime.now(LIMA).replace(tzinfo=None, microsecond=0)


def _fecha(valor):
    """datetime/date/str de la base -> datetime (o None)."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    t = pd.to_datetime(valor, errors="coerce")
    return None if pd.isna(t) else t.to_pydatetime()


def fmt(valor, con_hora: bool = True) -> str:
    t = _fecha(valor)
    if t is None:
        return "—"
    return t.strftime("%d/%m/%Y %H:%M" if con_hora else "%d/%m/%Y")


@dataclass
class Flujo:
    estados: dict = field(default_factory=dict)
    fecha_bloqueo: date | None = None
    disponible: bool = False

    def estado(self, depto: str) -> dict:
        return self.estados.get(depto, {})

    def cerrado(self, depto: str) -> bool:
        return bool(self.estado(depto).get("CERRADO"))

    def valorizado(self, depto: str) -> bool:
        return _fecha(self.estado(depto).get("FECHA_VALORIZACION")) is not None

    def cambios_sin_valorizar(self, depto: str) -> bool:
        e = self.estado(depto)
        guardado, valorizado = _fecha(e.get("FECHA_GUARDADO")), _fecha(e.get("FECHA_VALORIZACION"))
        return guardado is not None and (valorizado is None or guardado > valorizado)

    def bloqueo(self, depto: str) -> tuple[bool, str]:
        """(bloqueado, motivo para mostrar al usuario)."""
        if not self.disponible:
            return False, ""
        e = self.estado(depto)
        if e.get("CERRADO"):
            return True, (f"cerrado desde el {fmt(e.get('FECHA_CIERRE'))}. Para modificarlo, "
                          "pide a Presupuesto que lo reabra.")
        if e.get("BLOQUEO") == "BLOQUEADO":
            return True, "bloqueado por Presupuesto."
        if e.get("BLOQUEO") == "ABIERTO":
            return False, ""
        if self.fecha_bloqueo and ahora().date() >= self.fecha_bloqueo:
            return True, (f"bloqueado desde el {self.fecha_bloqueo:%d/%m/%Y} (fecha de cierre "
                          "del presupuesto). Para modificarlo, pide a Presupuesto que lo "
                          "desbloquee.")
        return False, ""

    def pendientes_carga(self) -> list[str]:
        """Departamentos de DEPTOS_PRIMERO que aún no cerraron."""
        return [d for d in DEPTOS_PRIMERO if not self.cerrado(d)]


def leer_flujo(repo) -> Flujo:
    try:
        estados, fecha, disponible = repo.estado_flujo()
    except Exception as ex:
        print(f"[flujo] no se pudo leer el estado: {ex!r}", flush=True)
        return Flujo()
    dic = {}
    if disponible and not estados.empty:
        for fila in estados.to_dict("records"):
            fila["CERRADO"] = bool(fila.get("CERRADO")) if pd.notna(fila.get("CERRADO")) else False
            fila["BLOQUEO"] = fila.get("BLOQUEO") if isinstance(fila.get("BLOQUEO"), str) else None
            dic[fila["DEPARTAMENTO"]] = fila
    f = _fecha(fecha)
    return Flujo(dic, f.date() if f else None, disponible)


def marcar(repo, depto: str, **campos):
    """Actualiza el estado sin interrumpir al usuario si las tablas no existen."""
    try:
        repo.actualizar_estado(depto, **campos)
    except Exception as ex:
        print(f"[flujo] no se pudo actualizar el estado de {depto}: {ex!r}", flush=True)


# ---------------------------------------------------------------- avisos

CSS_FLUJO = """
<style>
  .flujo { display: flex; gap: .6rem; flex-wrap: wrap; margin: .2rem 0 .8rem; }
  .flujo .paso { flex: 1; min-width: 220px; border: 1px solid #E1E5EC; border-radius: 10px;
                 padding: .55rem .8rem; background: #FFFFFF; }
  .flujo .paso.hecho { border-color: #ABEFC6; background: #F6FEF9; }
  .flujo .paso.activo { border-color: #F7B27A; background: #FFFAF5; }
  .flujo .titulo { font-size: .74rem; font-weight: 700; color: #17233B; }
  .flujo .num { display: inline-block; width: 1.2rem; height: 1.2rem; border-radius: 50%;
                background: #17233B; color: #fff; text-align: center; font-size: .7rem;
                line-height: 1.2rem; margin-right: .35rem; }
  .flujo .detalle { font-size: .72rem; color: #475467; margin-top: .25rem; }
  .flujo .chip { display: inline-block; padding: .05rem .45rem; border-radius: 20px;
                 font-size: .68rem; margin: .15rem .2rem 0 0; background: #F2F4F7; color: #344054; }
  .flujo .chip.ok { background: #DCFAE6; color: #067647; }
  .flujo .chip.medio { background: #FEF0C7; color: #93370D; }
</style>
"""


def panel_flujo(fl: Flujo):
    """Los pasos del flujo y en cuál va cada uno, para todos los usuarios."""
    if not fl.disponible:
        return
    chips = []
    for d in DEPTOS_PRIMERO:
        if fl.cerrado(d):
            chips.append(f'<span class="chip ok">{d} ✓ cerrado</span>')
        elif fl.valorizado(d):
            chips.append(f'<span class="chip medio">{d} valorizado, falta cerrar</span>')
        else:
            chips.append(f'<span class="chip">{d} pendiente</span>')
    pendientes = fl.pendientes_carga()
    paso1 = "hecho" if not pendientes else "activo"
    if fl.valorizado(DGA) and not pendientes:
        paso2, det2 = "hecho", f"Valorizada el {fmt(fl.estado(DGA).get('FECHA_VALORIZACION'))}."
    elif not pendientes:
        paso2, det2 = "activo", "Habilitada: la DGA ya puede valorizar."
    else:
        paso2, det2 = "", "Se habilita cuando DHUM, DMAT y DCN cierren."
    if fl.fecha_bloqueo:
        det3 = f"Hasta el {fl.fecha_bloqueo - timedelta(days=1):%d/%m/%Y} se puede modificar " \
               f"y valorizar; desde el {fl.fecha_bloqueo:%d/%m/%Y} Presupuesto bloquea."
    else:
        det3 = "Cada departamento valoriza cuando termina. Presupuesto aún no fijó la fecha de bloqueo."
    st.markdown(CSS_FLUJO + f"""
<div class="flujo">
  <div class="paso {paso1}"><div class="titulo"><span class="num">1</span>DHUM, DMAT y DCN valorizan y cierran</div>
    <div class="detalle">{''.join(chips)}</div></div>
  <div class="paso {paso2}"><div class="titulo"><span class="num">2</span>La DGA valoriza la carga académica</div>
    <div class="detalle">{det2}</div></div>
  <div class="paso"><div class="titulo"><span class="num">3</span>Los demás departamentos valorizan</div>
    <div class="detalle">{escape(det3)}</div></div>
</div>""", unsafe_allow_html=True)


def aviso_departamento(fl: Flujo, depto: str) -> bool:
    """Muestra el aviso que corresponde al departamento. Devuelve si está
    bloqueado (las planillas pasan a solo lectura)."""
    bloqueado, motivo = fl.bloqueo(depto)
    if bloqueado:
        st.warning(f"🔒 {depto} está {motivo} Puedes ver tus datos, pero no modificarlos.")
        return True
    if depto in DEPTOS_PRIMERO and not fl.cerrado(depto):
        st.info(f"**{depto} debe valorizar y cerrar primero.** La carga académica de la "
                "DGA solo se puede valorizar cuando DHUM, DMAT y DCN hayan cerrado. "
                "Cuando termines tus planillas, ve a **Resumen y valorización**, valoriza "
                "y luego cierra tu departamento.", icon="📌")
    elif fl.cambios_sin_valorizar(depto):
        st.info("Tienes cambios guardados sin valorizar. Cuando termines, ve a "
                "**Resumen y valorización**.", icon="ℹ️")
    if fl.fecha_bloqueo and not bloqueado:
        dias = (fl.fecha_bloqueo - ahora().date()).days
        if 0 < dias <= 7:
            st.caption(f"⏳ Quedan {dias} día(s): el {fl.fecha_bloqueo:%d/%m/%Y} Presupuesto "
                       "bloquea las modificaciones.")
    return False


# ---------------------------------------------------------- resumen depto

def _revisar_planilla(repo, hoja, filas, ccos_validos, roster):
    """(errores, resumen) de lo guardado de una planilla, con las
    validaciones completas (las de valorizar)."""
    cfg = cfg_de(hoja)
    m = matriz_desde_entrada(hoja, filas)
    if cfg["usa_roster"]:
        metas = dict(zip(roster["DNI"], roster.get("HORAS_META", pd.Series(dtype=float))))
        m["HORAS_META"] = m["DNI"].map(metas)
    tarifas = repo.tarifas(hoja) if cfg["tarifa"] == "catalogo" else {}
    errores = validar(hoja, m, ccos_validos, tarifas, estricto=True)
    if cfg["usa_roster"]:
        resumen = f"{m['DNI'].nunique()} docente(s)"
    elif cfg["metrica"] == "IMPORTE":
        resumen = formato_soles(estimar_importe(hoja, m, tarifas))
    elif cfg["tarifa"] == "catalogo":
        resumen = f"{formato_soles(estimar_importe(hoja, m, tarifas))} (estimado)"
    else:
        resumen = f"{total_horas(hoja, m):,.1f} h"
    return errores, resumen


def vista_resumen(repo, fl: Flujo, origen: str, ccos, roster, estructura):
    st.caption("Revisa lo que guardaste en cada planilla y valoriza tu departamento. "
               "Puedes volver a modificar y valorizar las veces que necesites.")
    bloqueado, _ = fl.bloqueo(origen)
    resultado = st.session_state.pop(f"_resultado_valorizar_{origen}", None)
    if resultado:
        (st.success if resultado[0] else st.error)(resultado[1],
                                                   icon="✅" if resultado[0] else "🛑")

    entrada = repo.entrada(origen)
    ccos_dep = set(ccos["CODIGO_CECO"])
    filas_tabla, observaciones = [], {}
    for hoja, cfg in PLANILLAS.items():
        filas = entrada[entrada["HOJA_ORIGEN"] == hoja]
        if filas.empty:
            filas_tabla.append((cfg["etiqueta"], 0, "—", "Sin datos"))
            continue
        validos = ccos_dep | (set(estructura["CODIGO_CECO"]) if cfg["usa_roster"] else set())
        errores, resumen = _revisar_planilla(repo, hoja, filas, validos, roster)
        if errores:
            observaciones[cfg["etiqueta"]] = errores
        filas_tabla.append((cfg["etiqueta"], len(filas), resumen,
                            f"⚠️ {len(errores)} observación(es)" if errores else "✅ Lista"))
    st.dataframe(pd.DataFrame(filas_tabla, columns=["Planilla", "Registros guardados",
                                                    "Resumen", "Estado"]),
                 hide_index=True, width="stretch")
    for etiqueta, errores in observaciones.items():
        with st.expander(f"Observaciones · {etiqueta}", expanded=True):
            for e in errores:
                st.error(e, icon="⚠️")

    e = fl.estado(origen)
    c1, c2, c3 = st.columns(3)
    c1.metric("Último guardado", fmt(e.get("FECHA_GUARDADO")))
    c2.metric("Última valorización", fmt(e.get("FECHA_VALORIZACION")))
    c3.metric("Cambios sin valorizar", "Sí" if fl.cambios_sin_valorizar(origen) else "No")

    sin_datos = entrada.empty
    motivo = ("El departamento está bloqueado." if bloqueado else
              "Corrige las observaciones antes de valorizar." if observaciones else
              "Aún no hay planillas guardadas." if sin_datos else "")
    if motivo:
        st.caption(motivo)
    if st.button("Valorizar departamento", type="primary", width="stretch",
                 disabled=bool(motivo), key=f"btn_valorizar_{origen}"):
        _dialogo_valorizar(repo, origen)

    if origen in DEPTOS_PRIMERO:
        st.divider()
        st.markdown("**Cerrar el departamento** · Paso necesario para que la DGA pueda "
                    "valorizar la carga académica.")
        if fl.cerrado(origen):
            st.success(f"{origen} cerró su presupuesto el {fmt(e.get('FECHA_CIERRE'))}.",
                       icon="🔒")
        else:
            falta = ("Primero valoriza el departamento." if not fl.valorizado(origen) else
                     "Hay cambios sin valorizar: valoriza de nuevo antes de cerrar."
                     if fl.cambios_sin_valorizar(origen) else "")
            if falta:
                st.caption(falta)
            if st.button("Cerrar departamento", width="stretch",
                         disabled=bool(falta) or bloqueado, key=f"btn_cerrar_{origen}"):
                _dialogo_cerrar(repo, origen)


@st.dialog("Valorizar departamento", width="large")
def _dialogo_valorizar(repo, origen):
    st.write(f"Se valorizarán todas las planillas guardadas de **{origen}** (planes TC, "
             "horas adicionales, postgrado, investigación y ayudantías). Reemplaza la "
             "valorización anterior del departamento.")
    c1, c2 = st.columns(2)
    if c1.button("Valorizar", type="primary", width="stretch"):
        with st.spinner("Valorizando…"):
            try:
                repo.valorizar(origen, sps_departamento())
                marcar(repo, origen, FECHA_VALORIZACION=ahora())
                res = (True, f"{origen} valorizado.")
            except Exception as ex:
                res = (False, f"No se valorizó nada; se revirtió la operación. Detalle: {ex}")
        st.session_state[f"_resultado_valorizar_{origen}"] = res
        st.rerun()
    if c2.button("Cancelar", width="stretch"):
        st.rerun()


@st.dialog("Cerrar departamento")
def _dialogo_cerrar(repo, origen):
    st.write(f"Al cerrar, **{origen}** ya no podrá modificar ni valorizar sus planillas. "
             "Solo Presupuesto puede reabrirlo. Con el cierre de DHUM, DMAT y DCN se "
             "habilita la valorización de la carga académica.")
    c1, c2 = st.columns(2)
    if c1.button("Cerrar departamento", type="primary", width="stretch"):
        marcar(repo, origen, CERRADO=True, FECHA_CIERRE=ahora())
        st.session_state[f"_resultado_valorizar_{origen}"] = (True, f"{origen} cerrado.")
        st.rerun()
    if c2.button("Cancelar", width="stretch"):
        st.rerun()


# ---------------------------------------------------------- administración

def _clave_admin():
    try:
        return st.secrets["admin"]["clave"]
    except Exception:
        return None


def vista_admin(repo, fl: Flujo, deptos: list[tuple]):
    clave = _clave_admin()
    if not clave:
        st.info("Para usar esta pestaña, agrega en los secrets de Streamlit:\n\n"
                "```toml\n[admin]\nclave = \"...\"\n```", icon="🔑")
        return
    if not st.session_state.get("_admin_ok"):
        with st.form("login_admin"):
            ingreso = st.text_input("Clave de Presupuesto", type="password")
            if st.form_submit_button("Entrar"):
                if hmac.compare_digest(ingreso.encode(), str(clave).encode()):
                    st.session_state["_admin_ok"] = True
                    st.rerun()
                st.error("Clave incorrecta.")
        return
    if not fl.disponible:
        st.warning("Faltan las tablas del flujo. Ejecuta `sql/crear_estado_presupuesto.sql` "
                   "en Azure y recarga la página. Mientras tanto no hay bloqueos.", icon="⚠️")
        return

    panel_flujo(fl)

    st.subheader("Fecha de bloqueo")
    st.caption("Desde esta fecha (hora de Lima) todos los departamentos quedan bloqueados, "
               "salvo los que desbloquees abajo.")
    c1, c2, c3 = st.columns([2, 1, 1], vertical_alignment="bottom")
    nueva = c1.date_input("Fecha de bloqueo", value=fl.fecha_bloqueo, format="DD/MM/YYYY")
    if c2.button("Guardar fecha", width="stretch", disabled=nueva is None):
        repo.fijar_fecha_bloqueo(nueva)
        st.rerun()
    if c3.button("Quitar fecha", width="stretch", disabled=fl.fecha_bloqueo is None):
        repo.fijar_fecha_bloqueo(None)
        st.rerun()

    st.subheader("Departamentos")
    codigos = [d for d, _ in deptos] + [DGA]
    nombres = {**dict(deptos), DGA: "Dirección de Gestión Académica (carga académica)"}
    filas = []
    for d in codigos:
        e = fl.estado(d)
        bloqueado, _ = fl.bloqueo(d)
        filas.append({
            "Departamento": f"{d} · {nombres[d]}",
            "Último guardado": fmt(e.get("FECHA_GUARDADO")),
            "Última valorización": fmt(e.get("FECHA_VALORIZACION")),
            "Cambios sin valorizar": "Sí" if fl.cambios_sin_valorizar(d) else "",
            "Cerrado": "🔒 " + fmt(e.get("FECHA_CIERRE")) if fl.cerrado(d) else "",
            "Decisión de Presupuesto": {"BLOQUEADO": "Bloqueado", "ABIERTO": "Desbloqueado"}
                                       .get(e.get("BLOQUEO"), "Según fecha"),
            "Situación": "🔒 Bloqueado" if bloqueado else "✏️ Puede modificar",
        })
    st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")

    elegidos = st.multiselect("Departamentos", codigos,
                              format_func=lambda d: f"{d} · {nombres[d]}")
    b1, b2, b3, b4 = st.columns(4)
    acciones = [
        (b1, "Bloquear", {"BLOQUEO": "BLOQUEADO"}),
        (b2, "Desbloquear", {"BLOQUEO": "ABIERTO"}),
        (b3, "Usar fecha general", {"BLOQUEO": None}),
        (b4, "Reabrir (quitar cierre)", {"CERRADO": False, "FECHA_CIERRE": None}),
    ]
    for col, etiqueta, campos in acciones:
        if col.button(etiqueta, width="stretch", disabled=not elegidos):
            for d in elegidos:
                repo.actualizar_estado(d, **campos)
            st.rerun()
    st.caption("Desbloquear ignora la fecha de bloqueo para ese departamento. Reabrir "
               "permite que DHUM, DMAT o DCN vuelvan a modificar; mientras no cierren de "
               "nuevo, la carga académica no se puede volver a valorizar.")
