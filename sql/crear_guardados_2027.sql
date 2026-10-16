/*
  Control de guardados simultáneos (presupuesto 2027).

  Guardar una planilla reemplaza toda la planilla del departamento. Si dos
  personas la editan a la vez, la que guarda última pisaba los cambios de la
  otra sin aviso. GUARDADOS_2027 lleva una versión por planilla y
  departamento: la app recuerda la versión que había al abrir la planilla y,
  al guardar, si alguien guardó mientras tanto, NO guarda y avisa quién y
  cuándo, para recargar antes de seguir.

  Sin esta tabla la app guarda como antes (sin detectar conflictos).
  Se puede ejecutar más de una vez.
*/

IF OBJECT_ID('dbo.GUARDADOS_2027', 'U') IS NULL
    CREATE TABLE dbo.GUARDADOS_2027 (
        PRESUPUESTO nvarchar(20)  NOT NULL,
        HOJA_ORIGEN nvarchar(100) NOT NULL,
        ORIGEN      nvarchar(100) NOT NULL,
        VERSION     int           NOT NULL,
        EMAIL       nvarchar(150) NOT NULL,
        FECHA       datetime2(0)  NOT NULL CONSTRAINT DF_GUARDADOS_2027_FECHA DEFAULT (SYSDATETIME()),
        CONSTRAINT PK_GUARDADOS_2027 PRIMARY KEY (PRESUPUESTO, HOJA_ORIGEN, ORIGEN)
    );
GO

-- Permisos (si ya se ejecutó sql/crear_permisos_app.sql)
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'rol_app_planillas' AND type = 'R')
    GRANT SELECT, INSERT, UPDATE ON dbo.GUARDADOS_2027 TO rol_app_planillas;
GO

-- La limpieza de borradores (sql/crear_limpieza_2027.sql) también reinicia
-- estas versiones: vuelve a ejecutar ese script después de este.

-- Verificación
SELECT OBJECT_ID('dbo.GUARDADOS_2027', 'U') AS tabla;
