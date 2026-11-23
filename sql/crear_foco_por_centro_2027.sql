/*
  Foco de un centro 2027 desde la app (Presupuesto · administración ›
  Centros de costo › Focos › Foco de un centro).

  El foco manual de un centro va en dbo.CLASIFICACION_CECOS_2027.FOCO y manda
  sobre el heredado (vw_CENTROS_2027_PROYECTO ya lo usa así). Hasta ahora cada
  fila exigía también PROYECTO, así que cambiar solo el foco dejaba el
  proyecto fijado a mano.

  Este script:
    1. Deja PROYECTO opcional (NULL = el centro sigue heredando su proyecto).
       Las filas que ya existen no cambian.
    2. Permite a la app agregar, cambiar y quitar filas de la tabla.
  La app guarda cada cambio en AUDITORIA_CECOS_2027 (acción FOCO CENTRO).

  No toca CENTROS_COSTOS ni las páginas 2026. Después de cambiar un foco,
  actualizar el modelo de Power BI.
  Ejecutar con la cuenta administradora, base Saldos. Se puede ejecutar más de una vez.
*/

IF EXISTS (SELECT 1 FROM sys.columns
           WHERE object_id = OBJECT_ID('dbo.CLASIFICACION_CECOS_2027') AND name = 'PROYECTO'
             AND is_nullable = 0)
    ALTER TABLE dbo.CLASIFICACION_CECOS_2027 ALTER COLUMN PROYECTO nvarchar(50) NULL;
GO

IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'rol_app_planillas' AND type = 'R')
    GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.CLASIFICACION_CECOS_2027 TO rol_app_planillas;
GO

-- Verificación: PROYECTO opcional y permisos de la app
SELECT name, is_nullable FROM sys.columns
WHERE object_id = OBJECT_ID('dbo.CLASIFICACION_CECOS_2027') AND name = 'PROYECTO';

SELECT STRING_AGG(permission_name, ', ') WITHIN GROUP (ORDER BY permission_name) AS permisos_app
FROM sys.database_permissions
WHERE grantee_principal_id = DATABASE_PRINCIPAL_ID('rol_app_planillas')
  AND major_id = OBJECT_ID('dbo.CLASIFICACION_CECOS_2027');

-- Sin cambios en la clasificación: mismas filas y focos que antes
SELECT COUNT(*) AS centros, COUNT(DISTINCT FOCO) AS focos FROM dbo.vw_CENTROS_2027_PROYECTO;
