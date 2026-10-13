/*
  Agrega DATOS_ENTRADA.PRESUPUESTO: identifica el ejercicio presupuestal de
  cada fila (la app escribe 'PPTO2027'). Las filas existentes, cargadas
  desde el Excel 2026, quedan en NULL.

  La app borra y reemplaza solo las filas de su propio PRESUPUESTO, por eso
  se agrega un índice para ese DELETE.

  Se puede ejecutar más de una vez.
*/
IF COL_LENGTH('dbo.DATOS_ENTRADA', 'PRESUPUESTO') IS NULL
    ALTER TABLE dbo.DATOS_ENTRADA ADD PRESUPUESTO nvarchar(20) NULL;
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'IX_DATOS_ENTRADA_PRESUPUESTO'
                 AND object_id = OBJECT_ID('dbo.DATOS_ENTRADA'))
    CREATE INDEX IX_DATOS_ENTRADA_PRESUPUESTO
        ON dbo.DATOS_ENTRADA (PRESUPUESTO, HOJA_ORIGEN, ORIGEN);
GO

-- Verificación
SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'DATOS_ENTRADA' AND COLUMN_NAME = 'PRESUPUESTO';
