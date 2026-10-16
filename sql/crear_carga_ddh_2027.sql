/*
  Importación de la valorización de Desarrollo Humano (DDH) 2027.

  Reemplaza la macro SubirDatos_DDH de "Subir datos DDH.xlsm", que tenía la
  contraseña de la cuenta administradora escrita en el código y borraba los
  datos ANTES de abrir la transacción (si la carga fallaba, DDH quedaba vacío).

  Desarrollo Humano sube el Excel desde la app (Desarrollo Humano ›
  Valorización DDH). La app valida el archivo, carga las filas con bulk copy en
  una tabla temporal (#CARGA_DDH, de la sesión: no escribe en el log de la
  base) y llama a sp_Importar_DDH_2027, que en una sola transacción:
    1. vuelve a validar centros de costo (codificación 2027), mes e importe;
    2. escribe SOLO LAS DIFERENCIAS con la valorización DDH 2027 actual: borra
       las filas que ya no están e inserta las nuevas. Reimportar un archivo
       corregido toca unas pocas filas en vez de miles (en el nivel Basic de
       Azure lo que limita es la escritura del log: ~30 s por cada 13 mil filas
       que cambian);
    3. registra quién importó y cuántas filas cambiaron.
  Si algo falla, no cambia nada.

  Permisos: solo la cuenta de Desarrollo Humano (rol_app_planillas_rrhh, ver
  sql/crear_permisos_app.sql) puede ejecutarlo. El sp escribe en PLANILLA por
  encadenamiento de propiedad: la cuenta no puede tocar PLANILLA por su cuenta.

  Se puede ejecutar más de una vez.
*/

-- La primera versión usaba una tabla de carga permanente; ya no hace falta
IF OBJECT_ID('dbo.CARGA_DDH_2027', 'U') IS NOT NULL
    DROP TABLE dbo.CARGA_DDH_2027;
GO

CREATE OR ALTER PROCEDURE dbo.sp_Importar_DDH_2027
    @Email nvarchar(150)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;   -- cualquier error revierte todo

    -- #CARGA_DDH la crea y llena la app en la misma sesión
    IF OBJECT_ID('tempdb..#CARGA_DDH') IS NULL
        THROW 50034, 'Falta #CARGA_DDH: la importación se hace desde la app.', 1;
    DECLARE @n int = (SELECT COUNT(*) FROM #CARGA_DDH);
    IF @n = 0
        THROW 50030, 'No hay filas para importar.', 1;
    IF EXISTS (SELECT 1 FROM #CARGA_DDH c
               WHERE NOT EXISTS (SELECT 1 FROM dbo.CENTROS_COSTOS_2027 k
                                 WHERE k.CENTRO_COSTO = c.CENTRO_COSTO))
        THROW 50031, 'Hay centros de costo que no están en CENTROS_COSTOS_2027.', 1;
    IF EXISTS (SELECT 1 FROM #CARGA_DDH WHERE MES NOT BETWEEN 1 AND 12)
        THROW 50032, 'Hay meses fuera de 1 a 12.', 1;

    DECLARE @borradas int = 0, @insertadas int = 0;
    BEGIN TRANSACTION;

    -- Filas DDH 2027 que no vinieron de esta importación (p. ej. cargadas a mano)
    DELETE FROM dbo.PLANILLA
    WHERE ORIGEN_2 = 'DDH' AND AÑO = '2027' AND ISNULL(ORIGEN, '') <> 'Desarrollo Humano';
    SET @borradas = @@ROWCOUNT;

    -- Comparación fila a fila. ROW_NUMBER numera las filas idénticas para que
    -- dos filas iguales en el archivo queden como dos filas en PLANILLA.
    -- Igualdad simple (ISNULL para CONCEPTO vacío): SQL la resuelve con un
    -- hash join; con EXISTS(... INTERSECT ...) comparaba fila contra fila.
    ;WITH actual AS (
        SELECT CENTRO_COSTO, PARTIDA, DIMENSION, MES, IMPORTE, CONCEPTO,
               ROW_NUMBER() OVER (PARTITION BY CENTRO_COSTO, PARTIDA, DIMENSION, MES,
                                  IMPORTE, CONCEPTO ORDER BY (SELECT 0)) AS RN
        FROM dbo.PLANILLA
        -- Con ORIGEN, SQL va directo por el índice agrupado (ORIGEN, ORIGEN_2, AÑO)
        WHERE ORIGEN = 'Desarrollo Humano' AND ORIGEN_2 = 'DDH' AND AÑO = '2027'),
    nuevo AS (
        SELECT CENTRO_COSTO, PARTIDA, DIMENSION, MES, IMPORTE, CONCEPTO,
               ROW_NUMBER() OVER (PARTITION BY CENTRO_COSTO, PARTIDA, DIMENSION, MES,
                                  IMPORTE, CONCEPTO ORDER BY (SELECT 0)) AS RN
        FROM #CARGA_DDH)
    DELETE FROM actual
    WHERE NOT EXISTS (SELECT 1 FROM nuevo b
                      WHERE b.CENTRO_COSTO = actual.CENTRO_COSTO AND b.PARTIDA = actual.PARTIDA
                        AND b.DIMENSION = actual.DIMENSION AND b.MES = actual.MES
                        AND b.IMPORTE = actual.IMPORTE AND b.RN = actual.RN
                        AND ISNULL(b.CONCEPTO, '') = ISNULL(actual.CONCEPTO, ''));
    SET @borradas += @@ROWCOUNT;

    ;WITH actual AS (
        SELECT CENTRO_COSTO, PARTIDA, DIMENSION, MES, IMPORTE, CONCEPTO,
               ROW_NUMBER() OVER (PARTITION BY CENTRO_COSTO, PARTIDA, DIMENSION, MES,
                                  IMPORTE, CONCEPTO ORDER BY (SELECT 0)) AS RN
        FROM dbo.PLANILLA
        -- Con ORIGEN, SQL va directo por el índice agrupado (ORIGEN, ORIGEN_2, AÑO)
        WHERE ORIGEN = 'Desarrollo Humano' AND ORIGEN_2 = 'DDH' AND AÑO = '2027'),
    nuevo AS (
        SELECT CENTRO_COSTO, PARTIDA, DIMENSION, MES, IMPORTE, CONCEPTO,
               ROW_NUMBER() OVER (PARTITION BY CENTRO_COSTO, PARTIDA, DIMENSION, MES,
                                  IMPORTE, CONCEPTO ORDER BY (SELECT 0)) AS RN
        FROM #CARGA_DDH)
    INSERT INTO dbo.PLANILLA (CENTRO_COSTO, PARTIDA, DIMENSION, MES, IMPORTE, ORIGEN,
                              CONCEPTO, ORIGEN_2, AÑO)
    SELECT b.CENTRO_COSTO, b.PARTIDA, b.DIMENSION, b.MES, b.IMPORTE, 'Desarrollo Humano',
           b.CONCEPTO, 'DDH', '2027'
    FROM nuevo b
    WHERE NOT EXISTS (SELECT 1 FROM actual a
                      WHERE a.CENTRO_COSTO = b.CENTRO_COSTO AND a.PARTIDA = b.PARTIDA
                        AND a.DIMENSION = b.DIMENSION AND a.MES = b.MES
                        AND a.IMPORTE = b.IMPORTE AND a.RN = b.RN
                        AND ISNULL(a.CONCEPTO, '') = ISNULL(b.CONCEPTO, ''));
    SET @insertadas = @@ROWCOUNT;

    INSERT INTO dbo.AUDITORIA_DESARROLLO_HUMANO (EMAIL, TABLA, ACCION, DETALLE)
    VALUES (@Email, 'PLANILLA DDH 2027', 'CARGA EXCEL',
            CONCAT(@n, ' fila(s) en el archivo; ', @insertadas, ' nuevas, ',
                   @borradas, ' quitadas, ', @n - @insertadas, ' sin cambios'));

    COMMIT;
    SELECT @n AS filas, @insertadas AS insertadas, @borradas AS borradas;
END;
GO

-- Permisos (si ya se ejecutó sql/crear_permisos_app.sql)
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'rol_app_planillas_rrhh' AND type = 'R')
    GRANT EXECUTE ON dbo.sp_Importar_DDH_2027 TO rol_app_planillas_rrhh;
GO

-- Verificación
SELECT OBJECT_ID('dbo.sp_Importar_DDH_2027', 'P') AS sp_importar,
       OBJECT_ID('dbo.CARGA_DDH_2027', 'U') AS tabla_carga_antigua_debe_ser_null;
