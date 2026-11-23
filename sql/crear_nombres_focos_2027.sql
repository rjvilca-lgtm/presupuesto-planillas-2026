/*
  Nombres de los focos 2027 desde la app (Presupuesto · administración ›
  Centros de costo › Focos).

  El foco de cada centro 2027 sale de dbo.vw_CENTROS_2027_PROYECTO: el manual
  (CLASIFICACION_CECOS_2027), si no el heredado del centro antiguo
  (CENTROS_COSTOS, 2026) y si no el de su grupo. No hay un catálogo de nombres,
  así que para cambiar uno había que tocar muchos centros y, en los heredados,
  también las páginas 2026.

  Este script:
    1. Crea dbo.FOCOS_NOMBRES_2027 (FOCO_ORIGINAL → FOCO_NOMBRE).
    2. Cambia dbo.vw_CENTROS_2027_PROYECTO: si el foco calculado está en esa
       tabla, muestra FOCO_NOMBRE. Lo demás de la vista no cambia. Así el nombre
       nuevo llega a todas las vistas 2027 que leen el foco (DIM, detalle,
       requerimientos, meta vs presupuesto y accesos por foco) y a los centros
       nuevos que hereden ese foco.
    3. Permisos de la app: escribir FOCOS_NOMBRES_2027 y mover las cuentas de
       USUARIOS_FOCOS_2027 al nombre nuevo (si no, perderían el acceso).
  Cada cambio queda en AUDITORIA_CECOS_2027 (acción FOCO NOMBRE).

  No toca CENTROS_COSTOS ni CLASIFICACION_CECOS_2027 ni las páginas 2026.
  Requiere sql/crear_gestion_cecos_2027.sql (auditoría). Después, actualizar
  el modelo de Power BI para ver los nombres nuevos.
  Ejecutar con la cuenta administradora, base Saldos. Se puede ejecutar más de una vez.
*/

IF OBJECT_ID('dbo.FOCOS_NOMBRES_2027', 'U') IS NULL
    CREATE TABLE dbo.FOCOS_NOMBRES_2027 (
        FOCO_ORIGINAL nvarchar(150) NOT NULL CONSTRAINT PK_FOCOS_NOMBRES_2027 PRIMARY KEY,
        FOCO_NOMBRE   nvarchar(150) NOT NULL
    );
GO

CREATE OR ALTER VIEW dbo.vw_CENTROS_2027_PROYECTO
AS
WITH origen AS (   -- centros antiguos -> centro 2027
    SELECT e.CODIGO_NUEVO AS CENTRO_COSTO,
           NULLIF(LTRIM(RTRIM(c.Proyecto)), '') AS PROYECTO,
           NULLIF(LTRIM(RTRIM(c.Foco)), '')     AS FOCO
    FROM dbo.EQUIVALENCIA_CECOS e
    JOIN dbo.CENTROS_COSTOS c ON c.CENTRO_COSTO = e.CODIGO_ANTIGUO
    UNION ALL
    SELECT c.CENTRO_COSTO, NULLIF(LTRIM(RTRIM(c.Proyecto)), ''), NULLIF(LTRIM(RTRIM(c.Foco)), '')
    FROM dbo.CENTROS_COSTOS c
    WHERE c.CENTRO_COSTO NOT LIKE '03.%'
),
p AS (
    SELECT CENTRO_COSTO, PROYECTO,
           ROW_NUMBER() OVER (PARTITION BY CENTRO_COSTO ORDER BY COUNT(*) DESC, PROYECTO) AS RN,
           COUNT(*) OVER (PARTITION BY CENTRO_COSTO) AS VALORES
    FROM origen WHERE PROYECTO IS NOT NULL GROUP BY CENTRO_COSTO, PROYECTO
),
f AS (
    SELECT CENTRO_COSTO, FOCO,
           ROW_NUMBER() OVER (PARTITION BY CENTRO_COSTO ORDER BY COUNT(*) DESC, FOCO) AS RN
    FROM origen WHERE FOCO IS NOT NULL GROUP BY CENTRO_COSTO, FOCO
),
centros AS (
    SELECT CENTRO_COSTO FROM dbo.CENTROS_COSTOS_2027
    UNION SELECT CENTRO_COSTO FROM dbo.CLASIFICACION_CECOS_2027
    UNION SELECT CENTRO_COSTO FROM origen
),
heredada AS (
    SELECT c.CENTRO_COSTO, LEFT(c.CENTRO_COSTO, 11) AS GRUPO,
           p.PROYECTO, f.FOCO, CASE WHEN p.VALORES > 1 THEN 1 ELSE 0 END AS CONFLICTO
    FROM centros c
    LEFT JOIN p ON p.CENTRO_COSTO = c.CENTRO_COSTO AND p.RN = 1
    LEFT JOIN f ON f.CENTRO_COSTO = c.CENTRO_COSTO AND f.RN = 1
),
grupo_p AS (
    SELECT GRUPO, PROYECTO, ROW_NUMBER() OVER (PARTITION BY GRUPO ORDER BY COUNT(*) DESC, PROYECTO) AS RN
    FROM heredada WHERE PROYECTO IS NOT NULL GROUP BY GRUPO, PROYECTO
),
grupo_f AS (
    SELECT GRUPO, FOCO, ROW_NUMBER() OVER (PARTITION BY GRUPO ORDER BY COUNT(*) DESC, FOCO) AS RN
    FROM heredada WHERE FOCO IS NOT NULL GROUP BY GRUPO, FOCO
)
SELECT CAST(h.CENTRO_COSTO AS varchar(100)) AS CENTRO_COSTO,
       CAST(COALESCE(m.PROYECTO, h.PROYECTO, gp.PROYECTO) AS nvarchar(50)) AS PROYECTO,
       -- Nombre del foco: el de FOCOS_NOMBRES_2027 si se cambió en la app
       CAST(COALESCE(fn.FOCO_NOMBRE, m.FOCO, h.FOCO, gf.FOCO) AS nvarchar(150)) AS FOCO,
       CAST(CASE WHEN m.PROYECTO IS NULL AND h.CONFLICTO = 1 THEN 1 ELSE 0 END AS bit) AS CONFLICTO,
       CAST(CASE WHEN m.PROYECTO IS NOT NULL THEN 'manual'
                 WHEN h.PROYECTO IS NOT NULL THEN 'heredada'
                 WHEN gp.PROYECTO IS NOT NULL THEN 'grupo' END AS varchar(10)) AS ORIGEN_PROYECTO,
       CAST(CASE WHEN m.FOCO IS NOT NULL THEN 'manual'
                 WHEN h.FOCO IS NOT NULL THEN 'heredada'
                 WHEN gf.FOCO IS NOT NULL THEN 'grupo' END AS varchar(10))     AS ORIGEN_FOCO
FROM heredada h
LEFT JOIN dbo.CLASIFICACION_CECOS_2027 m ON m.CENTRO_COSTO = h.CENTRO_COSTO
LEFT JOIN grupo_p gp ON gp.GRUPO = h.GRUPO AND gp.RN = 1
LEFT JOIN grupo_f gf ON gf.GRUPO = h.GRUPO AND gf.RN = 1
LEFT JOIN dbo.FOCOS_NOMBRES_2027 fn ON fn.FOCO_ORIGINAL = COALESCE(m.FOCO, h.FOCO, gf.FOCO);
GO

GRANT SELECT ON dbo.FOCOS_NOMBRES_2027 TO rol_app_sync;
GO

IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'rol_app_planillas' AND type = 'R')
BEGIN
    GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.FOCOS_NOMBRES_2027  TO rol_app_planillas;
    GRANT SELECT, UPDATE, DELETE         ON dbo.USUARIOS_FOCOS_2027 TO rol_app_planillas;
    GRANT SELECT                         ON dbo.vw_CENTROS_2027_PROYECTO TO rol_app_planillas;
END
GO

-- Verificación: sin nombres cambiados, la vista da los mismos focos que antes
SELECT FOCO, COUNT(*) AS centros_2027
FROM dbo.vw_CENTROS_2027_PROYECTO p
WHERE EXISTS (SELECT 1 FROM dbo.CENTROS_COSTOS_2027 n WHERE n.CENTRO_COSTO = p.CENTRO_COSTO)
GROUP BY FOCO ORDER BY FOCO;

SELECT OBJECT_NAME(major_id) AS objeto,
       STRING_AGG(permission_name, ', ') WITHIN GROUP (ORDER BY permission_name) AS permisos
FROM sys.database_permissions
WHERE grantee_principal_id = DATABASE_PRINCIPAL_ID('rol_app_planillas')
  AND major_id IN (OBJECT_ID('dbo.FOCOS_NOMBRES_2027'), OBJECT_ID('dbo.USUARIOS_FOCOS_2027'),
                   OBJECT_ID('dbo.vw_CENTROS_2027_PROYECTO'))
GROUP BY major_id;

/* Para volver a los nombres originales:
DELETE FROM dbo.FOCOS_NOMBRES_2027;
   (las cuentas de USUARIOS_FOCOS_2027 movidas a un nombre nuevo hay que
   devolverlas a mano)
*/
