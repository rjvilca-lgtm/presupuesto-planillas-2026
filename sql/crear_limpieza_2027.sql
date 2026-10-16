/*
  Limpieza de datos 2027 (por ejemplo, las pruebas) para dejar la app lista
  para producción, todo o por partes. Lo usa Presupuesto desde la app
  (Presupuesto · administración › Limpiar datos 2027).

  sp_Limpiar_2027 borra, en una transacción y solo del presupuesto 2027:
    @Borradores = 1    lo guardado en las planillas (DATOS_ENTRADA, PPTO2027) y
                       sus versiones de guardado (GUARDADOS_2027)
    @Valorizacion = 1  lo valorizado (PLANILLA, AÑO 2027)
    @Estado = 1        el estado del flujo (ESTADO_DEPARTAMENTO: guardado,
                       valorizado, cerrado y bloqueos por departamento)
  @Departamento: un código (DCN, DGA = carga académica, DDH = valorización de
  Desarrollo Humano, ...) o NULL para todos.

  NO toca: datos 2026 y anteriores, catálogos, centros de costo, tarifas,
  parámetros, padrón de docentes, salarios, usuarios ni las auditorías.
  Cada limpieza queda registrada en AUDITORIA_LIMPIEZA_2027.

  La cuenta de la app no puede borrar PLANILLA ni ESTADO_DEPARTAMENTO por su
  cuenta: solo a través de este sp (encadenamiento de propiedad).
  Se puede ejecutar más de una vez.
*/

IF OBJECT_ID('dbo.AUDITORIA_LIMPIEZA_2027', 'U') IS NULL
    CREATE TABLE dbo.AUDITORIA_LIMPIEZA_2027 (
        ID           int IDENTITY(1,1) NOT NULL CONSTRAINT PK_AUDITORIA_LIMPIEZA_2027 PRIMARY KEY,
        FECHA        datetime2(0)  NOT NULL CONSTRAINT DF_AUDITORIA_LIMPIEZA_FECHA DEFAULT (SYSDATETIME()),
        EMAIL        nvarchar(150) NOT NULL,
        DEPARTAMENTO varchar(20)   NULL,      -- NULL = todos
        BORRADORES   int           NOT NULL,  -- filas borradas
        VALORIZACION int           NOT NULL,
        ESTADO       int           NOT NULL
    );
GO

CREATE OR ALTER PROCEDURE dbo.sp_Limpiar_2027
    @Departamento varchar(20) = NULL,
    @Borradores   bit = 0,
    @Valorizacion bit = 0,
    @Estado       bit = 0,
    @Email        nvarchar(150)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;   -- cualquier error revierte todo
    DECLARE @b int = 0, @v int = 0, @e int = 0;

    BEGIN TRANSACTION;

    IF @Borradores = 1
    BEGIN
        DELETE FROM dbo.DATOS_ENTRADA
        WHERE PRESUPUESTO = 'PPTO2027' AND (@Departamento IS NULL OR ORIGEN = @Departamento)
        OPTION (RECOMPILE);
        SET @b = @@ROWCOUNT;
        -- Versiones de guardado (sql/crear_guardados_2027.sql), si existe
        IF OBJECT_ID('dbo.GUARDADOS_2027', 'U') IS NOT NULL
            DELETE FROM dbo.GUARDADOS_2027
            WHERE PRESUPUESTO = 'PPTO2027' AND (@Departamento IS NULL OR ORIGEN = @Departamento);
    END;

    IF @Valorizacion = 1
    BEGIN
        DELETE FROM dbo.PLANILLA
        WHERE AÑO = '2027' AND (@Departamento IS NULL OR ORIGEN_2 = @Departamento)
        OPTION (RECOMPILE);
        SET @v = @@ROWCOUNT;
    END;

    IF @Estado = 1
    BEGIN
        DELETE FROM dbo.ESTADO_DEPARTAMENTO
        WHERE PRESUPUESTO = 'PPTO2027' AND (@Departamento IS NULL OR DEPARTAMENTO = @Departamento);
        SET @e = @@ROWCOUNT;
    END;

    INSERT INTO dbo.AUDITORIA_LIMPIEZA_2027 (EMAIL, DEPARTAMENTO, BORRADORES, VALORIZACION, ESTADO)
    VALUES (@Email, @Departamento, @b, @v, @e);

    COMMIT;
    SELECT @b AS borradores, @v AS valorizacion, @e AS estado;
END;
GO

-- Permisos (si ya se ejecutó sql/crear_permisos_app.sql)
IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'rol_app_planillas' AND type = 'R')
BEGIN
    GRANT EXECUTE ON dbo.sp_Limpiar_2027 TO rol_app_planillas;
    GRANT SELECT ON dbo.AUDITORIA_LIMPIEZA_2027 TO rol_app_planillas;
END;
GO

-- Verificación
SELECT OBJECT_ID('dbo.sp_Limpiar_2027', 'P') AS sp_limpiar,
       OBJECT_ID('dbo.AUDITORIA_LIMPIEZA_2027', 'U') AS auditoria;
