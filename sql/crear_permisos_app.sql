/*
  Cuentas de base de datos con permisos mínimos para la app de planillas.

  Hoy la app entra con la cuenta administradora del servidor, que puede leer
  y modificar todo. Con este script entra con dos cuentas propias de la base
  Saldos (usuarios contenidos: no sirven para otras bases ni para el servidor):

    app_planillas       la app en general: catálogos, borradores, estado,
                        usuarios, tarifas, parámetros y valorización (EXEC de
                        los sp 2027). NO puede leer salarios: los sp los leen
                        por encadenamiento de propiedad (todo es de dbo), sin
                        que la cuenta tenga permiso sobre las tablas.
    app_planillas_rrhh  solo salarios 2027 (Remuneraciones_2027), para la
                        importación de Desarrollo Humano ([sql_rrhh]).

  ANTES DE EJECUTAR: reemplaza las dos contraseñas de abajo directamente en el
  Query editor (no las guardes en este archivo ni en el repositorio). Usa
  contraseñas largas y distintas (16+ caracteres, mayúsculas, minúsculas,
  números y símbolos), y guárdalas solo en los secrets de Streamlit Cloud.

  Después:
    1. En Streamlit Cloud → Settings → Secrets:
         [sql]       username = "app_planillas"       password = "..."
         [sql_rrhh]  server, port y database iguales a [sql],
                     username = "app_planillas_rrhh"  password = "..."
    2. Probar la app. La cuenta administradora sigue funcionando para el
       Query editor y la app de traslados; esto no la cambia.

  Se puede ejecutar más de una vez (para cambiar una contraseña:
  ALTER USER app_planillas WITH PASSWORD = '...').
*/

-- 1. Usuarios (reemplaza las contraseñas)
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'app_planillas')
    CREATE USER app_planillas WITH PASSWORD = '<<CONTRASEÑA_APP>>';
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'app_planillas_rrhh')
    CREATE USER app_planillas_rrhh WITH PASSWORD = '<<CONTRASEÑA_RRHH>>';
GO

-- 2. Roles
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'rol_app_planillas' AND type = 'R')
    CREATE ROLE rol_app_planillas;
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'rol_app_planillas_rrhh' AND type = 'R')
    CREATE ROLE rol_app_planillas_rrhh;
GO
ALTER ROLE rol_app_planillas ADD MEMBER app_planillas;
ALTER ROLE rol_app_planillas_rrhh ADD MEMBER app_planillas_rrhh;
GO

-- 3. App en general: solo lectura de catálogos y del resumen
GRANT SELECT ON dbo.Departamentos           TO rol_app_planillas;
GRANT SELECT ON dbo.CENTROS_COSTOS          TO rol_app_planillas;
GRANT SELECT ON dbo.CENTROS_COSTOS_2027     TO rol_app_planillas;
GRANT SELECT ON dbo.CECOS_DEPARTAMENTO_2027 TO rol_app_planillas;
GRANT SELECT ON dbo.EQUIVALENCIA_CECOS      TO rol_app_planillas;
GRANT SELECT ON dbo.CECO_CONCEPTO_TC        TO rol_app_planillas;
GRANT SELECT ON dbo.PartidaPresupuestal     TO rol_app_planillas;
GRANT SELECT ON dbo.DIMENSIONES             TO rol_app_planillas;
GRANT SELECT ON dbo.PLANILLA                TO rol_app_planillas;

-- Lo que la app escribe
GRANT SELECT, INSERT, DELETE         ON dbo.DATOS_ENTRADA       TO rol_app_planillas;  -- borradores
GRANT SELECT, INSERT, UPDATE         ON dbo.ESTADO_DEPARTAMENTO TO rol_app_planillas;  -- flujo
GRANT SELECT, UPDATE                 ON dbo.CONFIG_PRESUPUESTO  TO rol_app_planillas;  -- fecha de bloqueo
GRANT SELECT, INSERT, UPDATE         ON dbo.USUARIOS_PLANILLAS  TO rol_app_planillas;  -- administración
GRANT SELECT, UPDATE                 ON dbo.tarifas_2027        TO rol_app_planillas;
GRANT SELECT, UPDATE                 ON dbo.PARAMETROS_2027     TO rol_app_planillas;
GRANT SELECT, INSERT                 ON dbo.AUDITORIA_PARAMETROS        TO rol_app_planillas;
GRANT SELECT, INSERT                 ON dbo.AUDITORIA_DESARROLLO_HUMANO TO rol_app_planillas;
GRANT SELECT, INSERT, DELETE         ON dbo.HORAS_DOCENTES      TO rol_app_planillas;  -- padrón (Desarrollo Humano)

-- Valorización: solo los sp 2027 (escriben PLANILLA y leen salarios por dentro)
GRANT EXECUTE ON dbo.sp_ValorizarPlanilla_Total_2027    TO rol_app_planillas;
GRANT EXECUTE ON dbo.sp_Valorizar_HorasAdicionales_2027 TO rol_app_planillas;
GRANT EXECUTE ON dbo.sp_Valorizar_Postgrado_2027        TO rol_app_planillas;
GRANT EXECUTE ON dbo.sp_Valorizar_Investigacion_2027    TO rol_app_planillas;
GRANT EXECUTE ON dbo.sp_Valorizar_Ayudantias_2027       TO rol_app_planillas;
GRANT EXECUTE ON dbo.sp_Valorizar_CargaAcademica_2027   TO rol_app_planillas;

-- Salarios: prohibido leerlos directamente (aunque alguien agregue permisos
-- más amplios después). No afecta a los sp, que no revisan permisos al leer
-- tablas del mismo dueño.
DENY SELECT, INSERT, UPDATE, DELETE ON dbo.Remuneraciones_2027 TO rol_app_planillas;
DENY SELECT, INSERT, UPDATE, DELETE ON dbo.Remuneraciones      TO rol_app_planillas;
IF OBJECT_ID('dbo.SALARIOS', 'U') IS NOT NULL
    DENY SELECT, INSERT, UPDATE, DELETE ON dbo.SALARIOS TO rol_app_planillas;
GO

-- 4. Salarios 2027: solo la cuenta de Desarrollo Humano
GRANT SELECT, INSERT, DELETE ON dbo.Remuneraciones_2027 TO rol_app_planillas_rrhh;
-- Valorización DDH 2027 (sql/crear_carga_ddh_2027.sql), si ya existe
IF OBJECT_ID('dbo.CARGA_DDH_2027', 'U') IS NOT NULL
    GRANT INSERT, DELETE ON dbo.CARGA_DDH_2027 TO rol_app_planillas_rrhh;
IF OBJECT_ID('dbo.sp_Importar_DDH_2027', 'P') IS NOT NULL
    GRANT EXECUTE ON dbo.sp_Importar_DDH_2027 TO rol_app_planillas_rrhh;
GO

-- Verificación: permisos efectivos de cada rol
SELECT pr.name AS rol, OBJECT_NAME(pe.major_id) AS objeto, pe.permission_name AS permiso,
       pe.state_desc AS estado
FROM sys.database_permissions pe
JOIN sys.database_principals pr ON pr.principal_id = pe.grantee_principal_id
WHERE pr.name IN ('rol_app_planillas', 'rol_app_planillas_rrhh')
ORDER BY rol, objeto, permiso;
