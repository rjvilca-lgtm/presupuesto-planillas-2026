/*
  Historial de guardados de las planillas 2027.

  GUARDADOS_2027 solo recuerda el último guardado de cada planilla. Esta
  bitácora agrega una fila por cada guardado (quién, cuándo, qué planilla y
  cuántas filas quedaron), dentro de la misma transacción del guardado: si el
  guardado se revierte, la fila tampoco queda. Sirve para responder «yo lo
  había llenado y desapareció».

  La app la usa apenas existe (Administración › Historial de guardados y, para
  cada departamento, Resumen y valorización). Mientras no exista, la app
  guarda igual que antes. Se puede ejecutar más de una vez.
*/

IF OBJECT_ID('dbo.BITACORA_GUARDADOS_2027', 'U') IS NULL
    CREATE TABLE dbo.BITACORA_GUARDADOS_2027 (
        ID          int IDENTITY(1, 1) NOT NULL CONSTRAINT PK_BITACORA_GUARDADOS_2027 PRIMARY KEY,
        PRESUPUESTO varchar(20)   NOT NULL,
        HOJA_ORIGEN nvarchar(100) NOT NULL,
        ORIGEN      varchar(20)   NOT NULL,
        EMAIL       nvarchar(256) NULL,
        FECHA       datetime2(0)  NOT NULL,   -- hora de Lima, como GUARDADOS_2027
        FILAS       int           NOT NULL,
        VERSION     int           NULL,
        VALORIZADO  bit           NOT NULL CONSTRAINT DF_BITACORA_GUARDADOS_2027_VAL DEFAULT (0)
    );
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_BITACORA_GUARDADOS_2027_ORIGEN')
    CREATE INDEX IX_BITACORA_GUARDADOS_2027_ORIGEN
        ON dbo.BITACORA_GUARDADOS_2027 (PRESUPUESTO, ORIGEN, FECHA DESC);
GO

IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'rol_app_planillas' AND type = 'R')
    GRANT SELECT, INSERT ON dbo.BITACORA_GUARDADOS_2027 TO rol_app_planillas;
GO

-- Verificación
SELECT OBJECT_ID('dbo.BITACORA_GUARDADOS_2027', 'U') AS tabla,
       (SELECT COUNT(*) FROM dbo.BITACORA_GUARDADOS_2027) AS filas;
