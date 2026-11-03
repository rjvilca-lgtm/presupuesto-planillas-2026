/*
  Gestión de centros de costo 2027 desde la app (Presupuesto · administración ›
  Centros de costo).

  La app ya lee CENTROS_COSTOS_2027 (catálogo), CECOS_DEPARTAMENTO_2027 (qué
  centros puede presupuestar cada departamento) y CECO_CONCEPTO_TC (estructura
  de la ficha TC). Este script le permite además:
    - agregar centros al catálogo y corregir su descripción o dirección
      (nunca los borra: los datos 2026 y 2027 los usan);
    - asignar y quitar centros a un departamento (quitar solo si el
      departamento no tiene datos 2027 en ese centro; lo controla la app);
    - agregar centros a la ficha TC o desactivarlos (ACTIVO = 0, sin borrar).
  Cada cambio queda en AUDITORIA_CECOS_2027 (quién, cuándo, qué).

  Solo la pantalla de administración (rol PRESUPUESTO) hace estos cambios.
  No toca CENTROS_COSTOS (2026), que usan los datos 2026 y la app de traslados.
  Se puede ejecutar más de una vez.
*/

IF OBJECT_ID('dbo.AUDITORIA_CECOS_2027', 'U') IS NULL
    CREATE TABLE dbo.AUDITORIA_CECOS_2027 (
        ID      int IDENTITY(1, 1) NOT NULL CONSTRAINT PK_AUDITORIA_CECOS_2027 PRIMARY KEY,
        FECHA   datetime2(0)  NOT NULL,   -- hora de Lima
        EMAIL   nvarchar(256) NULL,
        ACCION  varchar(40)   NOT NULL,
        DETALLE nvarchar(max) NULL
    );
GO

IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'rol_app_planillas' AND type = 'R')
BEGIN
    GRANT SELECT, INSERT, UPDATE ON dbo.CENTROS_COSTOS_2027     TO rol_app_planillas;
    GRANT SELECT, INSERT, DELETE ON dbo.CECOS_DEPARTAMENTO_2027 TO rol_app_planillas;
    GRANT SELECT, INSERT, UPDATE ON dbo.CECO_CONCEPTO_TC        TO rol_app_planillas;
    GRANT SELECT, INSERT         ON dbo.AUDITORIA_CECOS_2027    TO rol_app_planillas;
END
GO

-- Verificación: permisos de la app sobre las cuatro tablas
SELECT OBJECT_NAME(major_id) AS tabla,
       STRING_AGG(permission_name, ', ') WITHIN GROUP (ORDER BY permission_name) AS permisos
FROM sys.database_permissions
WHERE grantee_principal_id = DATABASE_PRINCIPAL_ID('rol_app_planillas')
  AND major_id IN (OBJECT_ID('dbo.CENTROS_COSTOS_2027'), OBJECT_ID('dbo.CECOS_DEPARTAMENTO_2027'),
                   OBJECT_ID('dbo.CECO_CONCEPTO_TC'), OBJECT_ID('dbo.AUDITORIA_CECOS_2027'))
GROUP BY major_id;
