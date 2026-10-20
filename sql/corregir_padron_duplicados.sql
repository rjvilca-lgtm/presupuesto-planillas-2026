/*
  Padrón de docentes TC (HORAS_DOCENTES): una sola fila por DNI.

  La importación de Desarrollo Humano reemplaza el padrón completo, pero el
  19/10/2026 dos importaciones casi simultáneas dejaron 72 docentes repetidos
  (filas idénticas). Este script:
    1. quita las filas repetidas (deja una por DNI; eran idénticas);
    2. crea un índice único por DNI: desde ahora una importación que dejara
       un DNI repetido falla y se revierte entera, en vez de duplicar.

  Se puede ejecutar más de una vez.
*/

BEGIN TRANSACTION;

;WITH d AS (
    SELECT ROW_NUMBER() OVER (PARTITION BY DNI ORDER BY (SELECT 0)) AS RN
    FROM dbo.HORAS_DOCENTES)
DELETE FROM d WHERE RN > 1;

IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = 'UX_HORAS_DOCENTES_DNI' AND object_id = OBJECT_ID('dbo.HORAS_DOCENTES'))
    CREATE UNIQUE INDEX UX_HORAS_DOCENTES_DNI ON dbo.HORAS_DOCENTES (DNI);

COMMIT;
GO

-- Verificación: filas y docentes deben coincidir
SELECT COUNT(*) AS filas, COUNT(DISTINCT DNI) AS docentes FROM dbo.HORAS_DOCENTES;
