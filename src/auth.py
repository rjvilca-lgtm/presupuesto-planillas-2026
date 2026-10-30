"""
Login con la cuenta Google institucional (@ucsp.edu.pe) y permisos por rol.

Usa el login nativo de Streamlit (st.login / st.user), igual que la app de
traslados: requiere la sección [auth] en los secrets (client_id,
client_secret, server_metadata_url, redirect_uri, cookie_secret) y Authlib.

Los permisos salen de USUARIOS_PLANILLAS (sql/crear_usuarios_planillas.sql):
PRESUPUESTO ve todo y administra, DGA registra la carga académica,
DESARROLLO_HUMANO mantiene docentes, horas, tarifas y salarios,
DEPARTAMENTO registra las planillas de sus departamentos, AREA (áreas no
académicas, sql/crear_areas_2027.sql) registra las ayudantías de su área e
INVESTIGACION (gestor de investigación, sql/crear_rol_investigacion.sql)
registra solo la planilla de Investigación de sus departamentos; el
departamento la revisa y la valoriza.

Solo para probar en local, sin [auth]: [auth_dev] email = "..." en los
secrets hace de usuario logueado. Nunca se usa si [auth] está configurado.
"""

from dataclasses import dataclass, field
from pathlib import Path

import streamlit as st

DOMINIO = "ucsp.edu.pe"


@dataclass
class Usuario:
    email: str
    nombre: str
    presupuesto: bool = False
    dga: bool = False
    rrhh: bool = False   # Desarrollo Humano
    departamentos: list = field(default_factory=list)
    areas: list = field(default_factory=list)   # áreas no académicas (ayudantías)
    investigacion: list = field(default_factory=list)   # gestor: planilla Investigación

    @property
    def tiene_acceso(self) -> bool:
        return (self.presupuesto or self.dga or self.rrhh or bool(self.departamentos)
                or bool(self.areas) or bool(self.investigacion))

    @property
    def solo_investigacion(self) -> bool:
        """Gestor de investigación sin otro rol: solo ve esa planilla."""
        return bool(self.investigacion) and not (
            self.presupuesto or self.dga or self.rrhh or self.departamentos or self.areas)

    def planillas_de(self, depto: str) -> list | None:
        """Planillas que puede abrir en el departamento (None = todas)."""
        if self.presupuesto or depto in self.departamentos:
            return None
        return ["Investigacion"] if depto in self.investigacion else []


def _secrets_tiene(seccion: str) -> bool:
    try:
        return seccion in st.secrets
    except Exception:
        return False


def _identidad():
    """(email, nombre) del usuario logueado, o None."""
    if _secrets_tiene("auth"):
        try:
            if st.user.is_logged_in:
                return st.user.email, getattr(st.user, "name", None) or st.user.email
        except Exception:
            return None
        return None
    if _secrets_tiene("auth_dev"):
        email = st.secrets["auth_dev"].get("email")
        return (email, email) if email else None
    return None


def _logo():
    fp = Path(__file__).resolve().parent.parent / "assets" / "logo.png"
    return str(fp) if fp.exists() else None


def pantalla_login():
    st.markdown("""
    <style>
    [data-testid="stAppViewContainer"], .stApp { background:#003a78; }
    [data-testid="stHeader"] { background:transparent; }
    .block-container { padding-top:12vh; }
    .st-key-logincard { background:#ffffff; border-radius:16px; padding:44px 52px;
                        box-shadow:0 20px 55px rgba(0,0,0,.28); }
    .login-title { text-align:center; font-family:Georgia,'Times New Roman',serif;
        font-weight:400; font-size:2.1rem; color:#2b2b2b; margin:0 0 6px; }
    .login-sub { text-align:center; color:#667085; font-size:.9rem; margin-bottom:26px; }
    .st-key-logincard .stButton>button { background:#ffffff; color:#0a3d7c; border:none;
        box-shadow:none; font-weight:600; font-size:1.06rem; text-align:left; padding:0;
        min-height:0; }
    .st-key-logincard .stButton>button:hover { color:#062a5a; background:#ffffff; }
    </style>
    """, unsafe_allow_html=True)
    _, centro, _ = st.columns([1, 2, 1])
    with centro, st.container(key="logincard", border=False):
        st.markdown('<div class="login-title">Presupuesto de planillas</div>'
                    '<div class="login-sub">Accede con tu cuenta institucional</div>',
                    unsafe_allow_html=True)
        c_logo, c_boton = st.columns([5, 6], vertical_alignment="center")
        logo = _logo()
        if logo:
            c_logo.image(logo, width="stretch")
        if _secrets_tiene("auth"):
            if c_boton.button("Ingresa con tu\nSan Pablo Mail　›", width="stretch"):
                st.login()
        else:
            c_boton.error("Falta configurar el login ([auth] en los secrets).")


def _cerrar_sesion():
    try:
        st.logout()
    except Exception:
        st.rerun()


def exigir_login(repo) -> Usuario:
    """Devuelve el usuario con sus permisos o detiene la página (login,
    dominio no permitido o sin acceso registrado)."""
    identidad = _identidad()
    if not identidad:
        pantalla_login()
        # En segundo plano se llena la caché para que el primero en entrar no
        # espere (la visita automática de cada hora pasa por aquí)
        repo.precalentar_en_segundo_plano()
        st.stop()
    email, nombre = identidad
    email = email.strip().lower()

    if not email.endswith("@" + DOMINIO):
        st.error(f"Acceso restringido a cuentas @{DOMINIO}. Entraste con {email}.")
        if st.button("Cerrar sesión"):
            _cerrar_sesion()
        st.stop()

    try:
        filas = repo.permisos_usuario(email)
    except Exception as ex:
        print(f"[auth] no se pudieron leer los permisos: {ex!r}", flush=True)
        st.error("No se pudieron leer los permisos. Si es la primera vez, ejecuta "
                 "`sql/crear_usuarios_planillas.sql` en Azure.")
        st.stop()
    usuario = Usuario(email=email, nombre=nombre)
    for f in filas.to_dict("records"):
        if f["ROL"] == "PRESUPUESTO":
            usuario.presupuesto = True
        elif f["ROL"] == "DGA":
            usuario.dga = True
        elif f["ROL"] == "DESARROLLO_HUMANO":
            usuario.rrhh = True
        elif f["ROL"] == "DEPARTAMENTO" and f["DEPARTAMENTO"]:
            usuario.departamentos.append(f["DEPARTAMENTO"])
        elif f["ROL"] == "AREA" and f["DEPARTAMENTO"]:
            usuario.areas.append(f["DEPARTAMENTO"])
        elif f["ROL"] == "INVESTIGACION" and f["DEPARTAMENTO"]:
            usuario.investigacion.append(f["DEPARTAMENTO"])

    if not usuario.tiene_acceso:
        st.warning(f"Hola, {nombre}. Tu cuenta ({email}) aún no tiene acceso a la app. "
                   "Pide a la Oficina de Presupuesto que te registre.", icon="🔒")
        if st.button("Cerrar sesión"):
            _cerrar_sesion()
        st.stop()
    return usuario


def barra_usuario(usuario: Usuario):
    """Nombre, rol y botón de cerrar sesión, arriba a la derecha."""
    roles = (["Presupuesto"] if usuario.presupuesto else []) + \
            (["DGA"] if usuario.dga else []) + \
            (["Desarrollo Humano"] if usuario.rrhh else []) + usuario.departamentos + \
            usuario.areas + [f"Investigación {d}" for d in usuario.investigacion]
    c_info, c_btn = st.columns([6, 1], vertical_alignment="center")
    c_info.caption(f"👤 {usuario.nombre} · {usuario.email} · {', '.join(roles)}")
    if c_btn.button("Cerrar sesión", width="stretch", key="btn_logout"):
        _cerrar_sesion()
