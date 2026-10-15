/*
  Rol Desarrollo Humano.

  1. USUARIOS_PLANILLAS acepta el rol 'DESARROLLO_HUMANO'.
  2. Remuneraciones_2027: copia de dbo.Remuneraciones para el presupuesto 2027.
     Desarrollo Humano actualiza esta copia desde la app; dbo.Remuneraciones
     (que leen los sp de 2026) queda intacta, igual que con tarifas_2027.
  3. AUDITORIA_DESARROLLO_HUMANO: quién cambió qué y cuándo. Para salarios
     registra solo el DNI y los NOMBRES de los campos cambiados, nunca montos.
  4. sp_ValorizarPlanilla_Total_2027 pasa a leer Remuneraciones_2027.

  Se puede ejecutar más de una vez.
*/

-- 1. Rol nuevo
IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_USUARIOS_PLANILLAS_ROL')
    ALTER TABLE dbo.USUARIOS_PLANILLAS DROP CONSTRAINT CK_USUARIOS_PLANILLAS_ROL;
ALTER TABLE dbo.USUARIOS_PLANILLAS ADD CONSTRAINT CK_USUARIOS_PLANILLAS_ROL
    CHECK (ROL IN ('PRESUPUESTO', 'DGA', 'DEPARTAMENTO', 'DESARROLLO_HUMANO'));
GO

-- 2. Remuneraciones 2027 (copia inicial de las vigentes)
IF OBJECT_ID('dbo.Remuneraciones_2027', 'U') IS NULL
BEGIN
    SELECT * INTO dbo.Remuneraciones_2027 FROM dbo.Remuneraciones WHERE DNI IS NOT NULL;
    ALTER TABLE dbo.Remuneraciones_2027 ALTER COLUMN DNI nvarchar(15) NOT NULL;
END;
GO
IF NOT EXISTS (SELECT 1 FROM sys.key_constraints WHERE name = 'PK_Remuneraciones_2027')
    ALTER TABLE dbo.Remuneraciones_2027 ADD CONSTRAINT PK_Remuneraciones_2027 PRIMARY KEY (DNI);
GO

-- 3. Auditoría
IF OBJECT_ID('dbo.AUDITORIA_DESARROLLO_HUMANO', 'U') IS NULL
    CREATE TABLE dbo.AUDITORIA_DESARROLLO_HUMANO (
        ID      int IDENTITY(1,1) NOT NULL CONSTRAINT PK_AUDITORIA_DH PRIMARY KEY,
        FECHA   datetime2(0)  NOT NULL CONSTRAINT DF_AUDITORIA_DH_FECHA DEFAULT (SYSDATETIME()),
        EMAIL   nvarchar(150) NOT NULL,
        TABLA   varchar(50)   NOT NULL,
        DNI     nvarchar(15)  NULL,
        ACCION  varchar(20)   NOT NULL,
        DETALLE nvarchar(1000) NULL
    );
GO

-- 4. El sp 2027 lee Remuneraciones_2027 (solo si aún lee la tabla general)
DECLARE @def nvarchar(max) = OBJECT_DEFINITION(OBJECT_ID('dbo.sp_ValorizarPlanilla_Total_2027'));
IF @def IS NOT NULL AND @def NOT LIKE '%dbo.Remuneraciones[_]2027%'
BEGIN
    SET @def = REPLACE(@def, 'FROM dbo.Remuneraciones', 'FROM dbo.Remuneraciones_2027');
    -- La definición guardada empieza con CREATE: se cambia el primero por ALTER
    SET @def = STUFF(@def, CHARINDEX('CREATE', @def), 6, 'ALTER');
    EXEC sp_executesql @def;
END;
GO

-- Verificación
SELECT COUNT(*) AS remuneraciones_2027 FROM dbo.Remuneraciones_2027;
SELECT CASE WHEN OBJECT_DEFINITION(OBJECT_ID('dbo.sp_ValorizarPlanilla_Total_2027'))
            LIKE '%dbo.Remuneraciones[_]2027%' THEN 'sp 2027 lee Remuneraciones_2027'
            ELSE 'REVISAR: el sp 2027 no lee Remuneraciones_2027' END AS sp;
