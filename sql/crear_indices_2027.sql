/*
  Índices y restricción de unicidad.

  1. PLANILLA (~190 mil filas) y DATOS_ENTRADA no tenían índice agrupado
     (eran "heap"). Cada valorización borra e inserta miles de filas filtrando
     por ORIGEN / ORIGEN_2 / AÑO: con estos índices SQL va directo a ellas.
     IX_PLANILLA_ANIO acelera el Resumen de valorización.
     Los índices que creó Azure (nci_msft_*) se mantienen.
  2. Unicidad: una misma fila de plan TC (docente, centro de costo, concepto,
     mes) o de carga académica (centro de costo, concepto, semestre) no puede
     guardarse dos veces en el presupuesto 2027. Antes se encontraron filas TC
     triplicadas por guardados cruzados; la app ya lo evita con un bloqueo, y
     esto lo garantiza en la base aunque los datos lleguen por otro camino.
     Solo aplica a PRESUPUESTO = 'PPTO2027': los datos 2026 no se tocan.

  Nota: los índices filtrados exigen las opciones ANSI estándar en quien
  escribe en DATOS_ENTRADA (las tienen el Query editor, la app y ODBC).
  Se puede ejecutar más de una vez. Tarda pocos segundos.
*/

-- 1. Índices agrupados
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.PLANILLA') AND type = 1)
    CREATE CLUSTERED INDEX CX_PLANILLA_ORIGEN ON dbo.PLANILLA (ORIGEN, ORIGEN_2, AÑO);
GO
-- Para el Resumen de valorización (filtra por AÑO y departamento). Sin él,
-- cada apertura recorría las ~190 mil filas: ~10 s en el nivel Basic.
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_PLANILLA_ANIO')
    CREATE INDEX IX_PLANILLA_ANIO ON dbo.PLANILLA (AÑO, ORIGEN_2)
        INCLUDE (ORIGEN, PARTIDA, CENTRO_COSTO, MES, IMPORTE);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.DATOS_ENTRADA') AND type = 1)
    CREATE CLUSTERED INDEX CX_DATOS_ENTRADA ON dbo.DATOS_ENTRADA (PRESUPUESTO, ORIGEN, HOJA_ORIGEN);
GO

-- 2. Unicidad 2027 (si hay duplicados, el script los muestra y no crea el índice)
IF EXISTS (SELECT 1 FROM dbo.DATOS_ENTRADA
           WHERE PRESUPUESTO = 'PPTO2027'
             AND HOJA_ORIGEN IN ('1. Plan TC-I', 'Plan TC-II', 'Plan TC Transversales')
           GROUP BY ORIGEN, HOJA_ORIGEN, DNI, CENTRO_COSTO, CONCEPTO, MES HAVING COUNT(*) > 1)
    SELECT 'DUPLICADOS TC: corregir antes de crear UX_DATOS_ENTRADA_TC_2027' AS aviso,
           ORIGEN, HOJA_ORIGEN, DNI, CENTRO_COSTO, CONCEPTO, MES, COUNT(*) AS veces
    FROM dbo.DATOS_ENTRADA
    WHERE PRESUPUESTO = 'PPTO2027'
      AND HOJA_ORIGEN IN ('1. Plan TC-I', 'Plan TC-II', 'Plan TC Transversales')
    GROUP BY ORIGEN, HOJA_ORIGEN, DNI, CENTRO_COSTO, CONCEPTO, MES HAVING COUNT(*) > 1;
ELSE IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_DATOS_ENTRADA_TC_2027')
    CREATE UNIQUE INDEX UX_DATOS_ENTRADA_TC_2027
        ON dbo.DATOS_ENTRADA (ORIGEN, HOJA_ORIGEN, DNI, CENTRO_COSTO, CONCEPTO, MES)
        WHERE PRESUPUESTO = 'PPTO2027'
          AND HOJA_ORIGEN IN ('1. Plan TC-I', 'Plan TC-II', 'Plan TC Transversales');
GO

IF EXISTS (SELECT 1 FROM dbo.DATOS_ENTRADA
           WHERE PRESUPUESTO = 'PPTO2027' AND HOJA_ORIGEN = 'Carga Academica'
           GROUP BY CENTRO_COSTO, CONCEPTO, MES HAVING COUNT(*) > 1)
    SELECT 'DUPLICADOS CARGA: corregir antes de crear UX_DATOS_ENTRADA_CARGA_2027' AS aviso,
           CENTRO_COSTO, CONCEPTO, MES, COUNT(*) AS veces
    FROM dbo.DATOS_ENTRADA
    WHERE PRESUPUESTO = 'PPTO2027' AND HOJA_ORIGEN = 'Carga Academica'
    GROUP BY CENTRO_COSTO, CONCEPTO, MES HAVING COUNT(*) > 1;
ELSE IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_DATOS_ENTRADA_CARGA_2027')
    CREATE UNIQUE INDEX UX_DATOS_ENTRADA_CARGA_2027
        ON dbo.DATOS_ENTRADA (CENTRO_COSTO, CONCEPTO, MES)
        WHERE PRESUPUESTO = 'PPTO2027' AND HOJA_ORIGEN = 'Carga Academica';
GO

-- Verificación
SELECT OBJECT_NAME(object_id) AS tabla, name AS indice, type_desc, is_unique, has_filter
FROM sys.indexes
WHERE object_id IN (OBJECT_ID('dbo.PLANILLA'), OBJECT_ID('dbo.DATOS_ENTRADA')) AND index_id > 0
ORDER BY tabla, indice;
