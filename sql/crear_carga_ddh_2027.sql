/*
  Importación de la valorización de Desarrollo Humano (DDH) 2027.

  Reemplaza la macro SubirDatos_DDH de "Subir datos DDH.xlsm", que tenía la
  contraseña de la cuenta administradora escrita en el código y borraba los
  datos ANTES de abrir la transacción (si la carga fallaba, DDH quedaba vacío).

  Ahora Desarrollo Humano sube el Excel desde la app (Desarrollo Humano ›
  Valorización DDH). La app valida el archivo, lo deja en CARGA_DDH_2027 y
  llama a sp_Importar_DDH_2027, que en una sola transacción:
    1. vuelve a validar centros de costo (codificación 2027), mes e importe;
    2. borra la valorización DDH 2027 anterior de PLANILLA;
    3. inserta la nueva (ORIGEN = 'Desarrollo Humano', ORIGEN_2 = 'DDH',
       AÑO = '2027');
    4. vacía CARGA_DDH_2027 y registra quién importó y cuántas filas.
  Si algo falla, no cambia nada.

  Permisos: solo la cuenta de Desarrollo Humano (rol_app_planillas_rrhh, ver
  sql/crear_permisos_app.sql) puede cargar y ejecutar. El sp escribe en
  PLANILLA por encadenamiento de propiedad: la cuenta no puede borrar ni
  insertar en PLANILLA por su cuenta.

  Se puede ejecutar más de una vez.
*/

IF OBJECT_ID('dbo.CARGA_DDH_2027', 'U') IS NULL
    CREATE TABLE dbo.CARGA_DDH_2027 (
        CENTRO_COSTO varchar(50)   NOT NULL,
        PARTIDA      varchar(50)   NOT NULL,
        DIMENSION    varchar(50)   NOT NULL,
        MES          int           NOT NULL,
        IMPORTE      decimal(10,2) NOT NULL,
        CONCEPTO     varchar(100)  NULL
    );
GO

CREATE OR ALTER PROCEDURE dbo.sp_Importar_DDH_2027
    @Email nvarchar(150)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;   -- cualquier error revierte todo

    DECLARE @n int = (SELECT COUNT(*) FROM dbo.CARGA_DDH_2027);
    IF @n = 0
        THROW 50030, 'No hay filas para importar.', 1;
    IF EXISTS (SELECT 1 FROM dbo.CARGA_DDH_2027 c
               WHERE NOT EXISTS (SELECT 1 FROM dbo.CENTROS_COSTOS_2027 k
                                 WHERE k.CENTRO_COSTO = c.CENTRO_COSTO))
        THROW 50031, 'Hay centros de costo que no están en CENTROS_COSTOS_2027.', 1;
    IF EXISTS (SELECT 1 FROM dbo.CARGA_DDH_2027 WHERE MES NOT BETWEEN 1 AND 12)
        THROW 50032, 'Hay meses fuera de 1 a 12.', 1;

    BEGIN TRANSACTION;

    DELETE FROM dbo.PLANILLA WHERE ORIGEN_2 = 'DDH' AND AÑO = '2027';

    INSERT INTO dbo.PLANILLA (CENTRO_COSTO, PARTIDA, DIMENSION, MES, IMPORTE, ORIGEN,
                              CONCEPTO, ORIGEN_2, AÑO)
    SELECT CENTRO_COSTO, PARTIDA, DIMENSION, MES, IMPORTE, 'Desarrollo Humano',
           CONCEPTO, 'DDH', '2027'
    FROM dbo.CARGA_DDH_2027;

    DELETE FROM dbo.CARGA_DDH_2027;

    INSERT INTO dbo.AUDITORIA_DESARROLLO_HUMANO (EMAIL, TABLA, ACCION, DETALLE)
    VALUES (@Email, 'PLANILLA DDH 2027', 'CARGA EXCEL',
            CONCAT(@n, ' fila(s) de valorización DDH importadas'));

    COMMIT;
    SELECT @n AS filas;
END;
GO

-- Permisos (si ya se ejecutó sql/crear_permisos_app.sql)
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'rol_app_planillas_rrhh' AND type = 'R')
BEGIN
    GRANT INSERT, DELETE ON dbo.CARGA_DDH_2027 TO rol_app_planillas_rrhh;
    GRANT EXECUTE ON dbo.sp_Importar_DDH_2027 TO rol_app_planillas_rrhh;
END;
GO

-- Verificación
SELECT OBJECT_ID('dbo.CARGA_DDH_2027', 'U') AS tabla_carga,
       OBJECT_ID('dbo.sp_Importar_DDH_2027', 'P') AS sp_importar;
