# Presupuesto de planillas 2026

Aplicación de entrada de presupuesto de planillas para jefes de departamento.
Reemplaza el formato Excel con macros (`Sub_Actualizacion`) por un motor único
guiado por configuración que escribe en `DATOS_ENTRADA` y dispara los
procedimientos de valorización.

## Qué corrige respecto del Excel + macros

| Problema en el Excel/VBA | Solución en la app |
|---|---|
| Credencial de SQL en texto plano en cada macro, distribuida a cada depto | Cuenta de servicio en `secrets`, nunca en el cliente |
| `INSERT` por concatenación de strings (inyección SQL) | `INSERT` parametrizado con `executemany` |
| `DELETE` sin transacción: borra aunque el `INSERT` falle | `DELETE` + `INSERT` + `EXEC` en una transacción atómica (rollback total si algo falla) |
| Cada hoja atada a coordenadas fijas; mover una fila rompe la carga | Sin coordenadas: el usuario teclea filas, no llena posiciones |
| 7 macros de ~100 líneas, una por hoja | 1 motor + config declarativa (`src/config.py`) |
| El usuario no ve cuánto presupuesta hasta valorizar | Monto en vivo mientras teclea |
| Tarifa a veces en el cliente, a veces en la hoja, a veces en SQL | Tarifa siempre desde catálogo server-side; el usuario nunca teclea precios |

## Estructura

```
app.py                  Entrypoint e interfaz principal
src/config.py           Config declarativa de las 7 planillas (el "7 → 1")
src/repositorio.py      Capa de datos: RepositorioSQL (prod) y RepositorioDemo
src/validacion.py       Reglas de validación y formato, derivadas de la config
src/vistas.py           Componentes de interfaz
.streamlit/config.toml  Tema
.streamlit/secrets.toml.example   Plantilla de credenciales (no subir el real)
```

## Ejecutar localmente

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Sin `secrets.toml` la app arranca en **modo demostración** (datos de ejemplo,
no escribe en ninguna base). Es el modo pensado para revisar la experiencia.

## Conectar Azure SQL (producción)

1. Crea una **cuenta de servicio** con permisos mínimos sobre `DATOS_ENTRADA`
   y los `sp_Valorizar_*`. **No reutilices la credencial que estaba en las
   macros: rótala.**
2. Copia `.streamlit/secrets.toml.example` a `.streamlit/secrets.toml` y
   completa la sección `[sql]`.
3. `RepositorioSQL` usa `python-tds` (driver 100% Python, sin dependencias
   de sistema) — no requiere instalar ningún driver ODBC en la máquina/host.
4. Los catálogos (`Departamentos`, `CENTROS_COSTOS`, `tarifas_2027`, `HORAS_DOCENTES`) deben
   existir en SQL. Ajusta los nombres reales en `src/repositorio.py`.

## Desplegar en Streamlit Community Cloud

1. Sube el repositorio a GitHub (el `.gitignore` ya excluye `secrets.toml`).
2. En share.streamlit.io: **New app** → elige el repo, rama y `app.py`.
3. Sin secrets, la app queda pública en modo demostración.
4. Para producción, pega el contenido de `secrets.toml` en
   **Settings → Secrets**.
5. No hace falta `packages.txt`: `python-tds` es puro Python (vía pip), así
   que evita los problemas de instalar un driver ODBC en Community Cloud
   (el "ODBC Driver 18 for SQL Server" de Microsoft exige su propio repo
   APT que ahí no se puede agregar; FreeTDS vía apt choca con el unixODBC
   que ya trae la imagen).
6. En Azure SQL, habilita el firewall para que Community Cloud pueda
   conectarse: **Networking → Firewall rules**. No publica IPs fijas de
   salida, así que para probar conviene permitir temporalmente todo el rango
   (`0.0.0.0` – `255.255.255.255`) y luego acotarlo, o dejar la cuenta de
   servicio con permisos mínimos como mitigación mientras tanto.

## Pendientes antes de producción

- Derivar el departamento del **usuario autenticado (SSO)**, no de un selector.
- Confirmar nombres reales de tablas de catálogo en `src/repositorio.py`.
- Migrar la tarifa de Horas Adicionales para que la resuelva el `sp` (hoy el
  motor la aplica desde catálogo y la envía, como puente).
- Pre-poblar la grilla desde el padrón real para las planillas TC.
