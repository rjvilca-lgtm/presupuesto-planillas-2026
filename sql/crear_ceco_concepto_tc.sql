/*
  CECO_CONCEPTO_TC: tabla maestra de la ficha "Plan de trabajo TC".
  Define qué conceptos se presupuestan en cada centro de costo, por
  departamento. La app la lee en RepositorioSQL.estructura_tc().

  - Se puede ejecutar más de una vez: crea la tabla solo si no existe e
    inserta solo las combinaciones que falten.
  - La carga inicial sale de las cargas TC que ya hay en DATOS_ENTRADA
    (hojas 1. Plan TC-I, Plan TC-II y Plan TC Transversales).
  - Para quitar un concepto de la ficha sin borrarlo: ACTIVO = 0.
  - DEPARTAMENTO es el código de Departamentos.CODIGO (DAIC, DHUM, ...).
    CENTRO_COSTO puede ser de otro departamento (docentes transversales).
*/
SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF OBJECT_ID('dbo.CECO_CONCEPTO_TC', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.CECO_CONCEPTO_TC (
        DEPARTAMENTO    varchar(10)    NOT NULL,
        CENTRO_COSTO    nvarchar(50)   NOT NULL,
        CONCEPTO        nvarchar(150)  NOT NULL,
        ACTIVO          bit            NOT NULL
            CONSTRAINT DF_CECO_CONCEPTO_TC_ACTIVO DEFAULT (1),
        FECHA_REGISTRO  datetime2(0)   NOT NULL
            CONSTRAINT DF_CECO_CONCEPTO_TC_FECHA DEFAULT (SYSDATETIME()),
        CONSTRAINT PK_CECO_CONCEPTO_TC
            PRIMARY KEY (DEPARTAMENTO, CENTRO_COSTO, CONCEPTO)
    );
END;

INSERT INTO dbo.CECO_CONCEPTO_TC (DEPARTAMENTO, CENTRO_COSTO, CONCEPTO)
SELECT DISTINCT
    LTRIM(RTRIM(de.ORIGEN)),
    LTRIM(RTRIM(de.CENTRO_COSTO)),
    LTRIM(RTRIM(de.CONCEPTO))
FROM dbo.DATOS_ENTRADA de
WHERE de.HOJA_ORIGEN IN ('1. Plan TC-I', 'Plan TC-II', 'Plan TC Transversales')
  AND NULLIF(LTRIM(RTRIM(de.ORIGEN)), '') IS NOT NULL
  AND NULLIF(LTRIM(RTRIM(de.CENTRO_COSTO)), '') IS NOT NULL
  AND NULLIF(LTRIM(RTRIM(de.CONCEPTO)), '') IS NOT NULL
  AND LTRIM(RTRIM(de.CONCEPTO)) <> '0'
  AND NOT EXISTS (
      SELECT 1 FROM dbo.CECO_CONCEPTO_TC t
      WHERE t.DEPARTAMENTO = LTRIM(RTRIM(de.ORIGEN))
        AND t.CENTRO_COSTO = LTRIM(RTRIM(de.CENTRO_COSTO))
        AND t.CONCEPTO     = LTRIM(RTRIM(de.CONCEPTO))
  );

PRINT CONCAT('Combinaciones insertadas: ', @@ROWCOUNT);

COMMIT TRANSACTION;

-- Verificación: combinaciones por departamento
SELECT DEPARTAMENTO, COUNT(*) AS combinaciones,
       COUNT(DISTINCT CENTRO_COSTO) AS centros_costo
FROM dbo.CECO_CONCEPTO_TC
GROUP BY DEPARTAMENTO
ORDER BY DEPARTAMENTO;
