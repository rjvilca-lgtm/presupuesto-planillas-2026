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
    2. compara con la valorización DDH 2027 actual: si solo hay filas nuevas,
       inserta esas (reimportar un archivo con unas filas más toca pocas filas);
       si hay filas que quitar, reemplaza el bloque completo (borrar por el
       índice agrupado e insertar todo tarda ~1 min en Basic, mientras que
       quitar fila por fila llegó a tardar más de una hora);
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

    -- Diferencias en tablas temporales con índice. ROW_NUMBER numera las filas
    -- idénticas para que dos filas iguales en el archivo queden como dos filas en
    -- PLANILLA. (La versión anterior borraba a través de un CTE con ROW_NUMBER:
    -- con muchos cambios ese plan tardó 51 y 82 minutos en el nivel Basic y dejó
    -- la base al 100 % de CPU para todos los usuarios.)
    SELECT CENTRO_COSTO, PARTIDA, DIMENSION, MES, IMPORTE, ISNULL(CONCEPTO, '') AS CONCEPTO,
           ROW_NUMBER() OVER (PARTITION BY CENTRO_COSTO, PARTIDA, DIMENSION, MES, IMPORTE,
                              ISNULL(CONCEPTO, '') ORDER BY (SELECT 0)) AS RN
    INTO #ACTUAL_DDH
    FROM dbo.PLANILLA
    -- Con ORIGEN, SQL va directo por el índice agrupado (ORIGEN, ORIGEN_2, AÑO)
    WHERE ORIGEN = 'Desarrollo Humano' AND ORIGEN_2 = 'DDH' AND AÑO = '2027';
    SELECT CENTRO_COSTO, PARTIDA, DIMENSION, MES, IMPORTE, ISNULL(CONCEPTO, '') AS CONCEPTO,
           CONCEPTO AS CONCEPTO_ORIGINAL,
           ROW_NUMBER() OVER (PARTITION BY CENTRO_COSTO, PARTIDA, DIMENSION, MES, IMPORTE,
                              ISNULL(CONCEPTO, '') ORDER BY (SELECT 0)) AS RN
    INTO #NUEVO_DDH
    FROM #CARGA_DDH;
    CREATE CLUSTERED INDEX CX ON #ACTUAL_DDH (CENTRO_COSTO, PARTIDA, DIMENSION, MES, IMPORTE, CONCEPTO, RN);
    CREATE CLUSTERED INDEX CX ON #NUEVO_DDH (CENTRO_COSTO, PARTIDA, DIMENSION, MES, IMPORTE, CONCEPTO, RN);

    DECLARE @quitar int = (
        SELECT COUNT(*) FROM #ACTUAL_DDH a
        WHERE NOT EXISTS (SELECT 1 FROM #NUEVO_DDH b
                          WHERE b.CENTRO_COSTO = a.CENTRO_COSTO AND b.PARTIDA = a.PARTIDA
                            AND b.DIMENSION = a.DIMENSION AND b.MES = a.MES
                            AND b.IMPORTE = a.IMPORTE AND b.CONCEPTO = a.CONCEPTO AND b.RN = a.RN));
    DECLARE @agregar int = (
        SELECT COUNT(*) FROM #NUEVO_DDH b
        WHERE NOT EXISTS (SELECT 1 FROM #ACTUAL_DDH a
                          WHERE a.CENTRO_COSTO = b.CENTRO_COSTO AND a.PARTIDA = b.PARTIDA
                            AND a.DIMENSION = b.DIMENSION AND a.MES = b.MES
                            AND a.IMPORTE = b.IMPORTE AND a.CONCEPTO = b.CONCEPTO AND a.RN = b.RN));

    DECLARE @borradas int = 0, @insertadas int = 0;
    BEGIN TRANSACTION;

    -- Filas DDH 2027 que no vinieron de esta importación (p. ej. cargadas a mano)
    DELETE FROM dbo.PLANILLA
    WHERE ORIGEN_2 = 'DDH' AND AÑO = '2027' AND ISNULL(ORIGEN, '') <> 'Desarrollo Humano';
    SET @borradas = @@ROWCOUNT;

    IF @quitar > 0
    BEGIN
        -- Hay filas que quitar: se reemplaza el bloque completo. Borrar por el
        -- índice agrupado e insertar todo es lineal (~1 min para 9 mil filas en
        -- Basic); quitar fila por fila buscándolas no lo es.
        DELETE FROM dbo.PLANILLA
        WHERE ORIGEN = 'Desarrollo Humano' AND ORIGEN_2 = 'DDH' AND AÑO = '2027';
        INSERT INTO dbo.PLANILLA (CENTRO_COSTO, PARTIDA, DIMENSION, MES, IMPORTE, ORIGEN,
                                  CONCEPTO, ORIGEN_2, AÑO)
        SELECT CENTRO_COSTO, PARTIDA, DIMENSION, MES, IMPORTE, 'Desarrollo Humano',
               CONCEPTO, 'DDH', '2027'
        FROM #CARGA_DDH;
    END
    ELSE IF @agregar > 0
        -- Solo filas nuevas: se agregan esas
        INSERT INTO dbo.PLANILLA (CENTRO_COSTO, PARTIDA, DIMENSION, MES, IMPORTE, ORIGEN,
                                  CONCEPTO, ORIGEN_2, AÑO)
        SELECT b.CENTRO_COSTO, b.PARTIDA, b.DIMENSION, b.MES, b.IMPORTE, 'Desarrollo Humano',
               b.CONCEPTO_ORIGINAL, 'DDH', '2027'
        FROM #NUEVO_DDH b
        WHERE NOT EXISTS (SELECT 1 FROM #ACTUAL_DDH a
                          WHERE a.CENTRO_COSTO = b.CENTRO_COSTO AND a.PARTIDA = b.PARTIDA
                            AND a.DIMENSION = b.DIMENSION AND a.MES = b.MES
                            AND a.IMPORTE = b.IMPORTE AND a.CONCEPTO = b.CONCEPTO
                            AND a.RN = b.RN);
    -- Se informa lo que cambió de verdad, aunque se reescriba el bloque completo
    SET @borradas += @quitar;
    SET @insertadas = @agregar;

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
