/*
  Permisos de Power BI 2027 desde la app (Presupuesto · administración ›
  Centros de costo › Permisos Power BI).

  Qué centros 2027 ve cada cuenta del informe sale de dbo.vw_USUARIOS_CECOS_2027,
  que junta:
    - dbo.USUARIOS (centro o departamento de cada cuenta, también para 2026):
      la app solo la LEE, no la cambia;
    - dbo.USUARIOS_FOCOS_2027: la cuenta ve todos los centros 2027 de un foco;
    - dbo.USUARIOS_PREFIJOS_2027: la cuenta ve todos los centros 2027 cuyo
      código empieza con un prefijo (un código completo = un solo centro).
  Con la app se dan y se quitan focos y prefijos. Cada cambio queda en
  AUDITORIA_CECOS_2027 (acción PERMISO BI).

  Este script solo da permisos a la app; no cambia datos ni las páginas 2026.
  Después de un cambio, actualizar el modelo de Power BI. En el servicio, la
  cuenta debe estar en el rol Usuarios o Usuario_centro (la página de
  requerimientos usa Usuario_centro).
  Ejecutar con la cuenta administradora, base Saldos. Se puede ejecutar más de una vez.
*/

IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'rol_app_planillas' AND type = 'R')
BEGIN
    GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.USUARIOS_FOCOS_2027    TO rol_app_planillas;
    GRANT SELECT, INSERT, UPDATE, DELETE ON dbo.USUARIOS_PREFIJOS_2027 TO rol_app_planillas;
    GRANT SELECT                         ON dbo.vw_USUARIOS_CECOS_2027 TO rol_app_planillas;
    GRANT SELECT                         ON dbo.USUARIOS               TO rol_app_planillas;
END
GO

-- Verificación: permisos de la app
SELECT OBJECT_NAME(major_id) AS objeto,
       STRING_AGG(permission_name, ', ') WITHIN GROUP (ORDER BY permission_name) AS permisos_app
FROM sys.database_permissions
WHERE grantee_principal_id = DATABASE_PRINCIPAL_ID('rol_app_planillas')
  AND major_id IN (OBJECT_ID('dbo.USUARIOS_FOCOS_2027'), OBJECT_ID('dbo.USUARIOS_PREFIJOS_2027'),
                   OBJECT_ID('dbo.vw_USUARIOS_CECOS_2027'), OBJECT_ID('dbo.USUARIOS'))
GROUP BY major_id;
