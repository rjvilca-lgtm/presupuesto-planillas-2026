/*
  Áreas no académicas que presupuestan ayudantías (pestaña "Ayudantías · áreas").

  En 2026 algunas direcciones (Secretaría General, Marketing, Planeación, etc.)
  cargaban ayudantías con la misma hoja que los departamentos. En 2027 lo hacen
  desde la app con el rol AREA:

    AREAS_2027   catálogo de áreas. Cada área ve los centros de costo 2027 de
                 su dirección (CENTROS_COSTOS_2027.DIRECCION). CODIGO es lo que
                 queda en DATOS_ENTRADA.ORIGEN y PLANILLA.ORIGEN_2 (máx. 10
                 caracteres, distinto de los departamentos y de 'DGA'/'DDH').
    ROL 'AREA'   en USUARIOS_PLANILLAS, con DEPARTAMENTO = código del área.

  Lo guardado se valoriza con sp_Valorizar_Ayudantias_2027, igual que las
  ayudantías de los departamentos. Para agregar un área, inserta una fila en
  AREAS_2027; para ocultarla, ACTIVO = 0.

  Se puede ejecutar más de una vez.
*/

IF OBJECT_ID('dbo.AREAS_2027', 'U') IS NULL
    CREATE TABLE dbo.AREAS_2027 (
        CODIGO       varchar(10)   NOT NULL CONSTRAINT PK_AREAS_2027 PRIMARY KEY,
        DESCRIPCION  nvarchar(150) NOT NULL,
        DIRECCION    nvarchar(255) NOT NULL,   -- = CENTROS_COSTOS_2027.DIRECCION
        ACTIVO       bit           NOT NULL CONSTRAINT DF_AREAS_2027_ACTIVO DEFAULT (1)
    );
GO

-- Las direcciones no académicas de CENTROS_COSTOS_2027 (sin facultades). El
-- texto de DIRECCION se copia de la tabla para que el cruce sea exacto.
;WITH a (CODIGO, DESCRIPCION, PATRON) AS (
    SELECT * FROM (VALUES
        ('VRAC',  N'Vicerrectorado Académico',                            N'VICERRECTORADO ACAD%'),
        ('GESAC', N'Dirección de Gestión Académica',                      N'DIRECCION DE GESTI%N ACAD%'),
        ('PREGR', N'Dirección de Pregrado',                               N'DIRECCION DE PREGRADO'),
        ('POSTG', N'Dirección de la Escuela de Postgrado',                N'DIRECCION DE LA ESCUELA DE POSTGRADO'),
        ('INVES', N'Dirección de Investigación',                          N'DIRECCION DE INVESTIGACION'),
        ('DSPS',  N'Dirección de Servicio y Proyección a la Sociedad',    N'DIRECCION DE SERVICIO Y PROYECCION%'),
        ('DRIC',  N'Dirección de Relaciones Internacionales y Cooperación', N'DIRECCION DE RELACIONES INTERNACIONALES%'),
        ('RECT',  N'Rectorado',                                           N'RECTORADO'),
        ('SGEN',  N'Secretaría General',                                  N'SECRETARIA GENERAL'),
        ('PYC',   N'Persona y Cultura',                                   N'PERSONA Y CULTURA'),
        ('DAF',   N'Dirección de Administración y Finanzas',              N'DIRECCION DE ADMINISTRACION Y FINANZAS'),
        ('DCM',   N'Dirección de Comunicaciones y Marketing',             N'DIRECCION DE COMUNICACIONES Y MARKETING'),
        ('DPE',   N'Dirección de Planeación Estratégica',                 N'DIRECCION DE PLANEACION ESTRATEGICA')
    ) v (CODIGO, DESCRIPCION, PATRON))
INSERT INTO dbo.AREAS_2027 (CODIGO, DESCRIPCION, DIRECCION)
SELECT a.CODIGO, a.DESCRIPCION,
       (SELECT TOP 1 c.DIRECCION FROM dbo.CENTROS_COSTOS_2027 c WHERE c.DIRECCION LIKE a.PATRON)
FROM a
WHERE NOT EXISTS (SELECT 1 FROM dbo.AREAS_2027 x WHERE x.CODIGO = a.CODIGO)
  AND EXISTS (SELECT 1 FROM dbo.CENTROS_COSTOS_2027 c WHERE c.DIRECCION LIKE a.PATRON);
GO

-- Rol AREA en USUARIOS_PLANILLAS (como DEPARTAMENTO, lleva el código del área)
IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_USUARIOS_PLANILLAS_ROL')
    ALTER TABLE dbo.USUARIOS_PLANILLAS DROP CONSTRAINT CK_USUARIOS_PLANILLAS_ROL;
ALTER TABLE dbo.USUARIOS_PLANILLAS ADD CONSTRAINT CK_USUARIOS_PLANILLAS_ROL
    CHECK (ROL IN ('PRESUPUESTO', 'DGA', 'DESARROLLO_HUMANO', 'DEPARTAMENTO', 'AREA'));
IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_USUARIOS_PLANILLAS_DEPTO')
    ALTER TABLE dbo.USUARIOS_PLANILLAS DROP CONSTRAINT CK_USUARIOS_PLANILLAS_DEPTO;
ALTER TABLE dbo.USUARIOS_PLANILLAS ADD CONSTRAINT CK_USUARIOS_PLANILLAS_DEPTO
    CHECK ((ROL IN ('DEPARTAMENTO', 'AREA') AND DEPARTAMENTO IS NOT NULL)
        OR (ROL NOT IN ('DEPARTAMENTO', 'AREA') AND DEPARTAMENTO IS NULL));
GO

IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'rol_app_planillas' AND type = 'R')
    GRANT SELECT ON dbo.AREAS_2027 TO rol_app_planillas;
GO

-- Verificación: cada área con sus centros de costo (ninguna debe tener 0)
SELECT a.CODIGO, a.DESCRIPCION, COUNT(c.CENTRO_COSTO) AS centros_de_costo
FROM dbo.AREAS_2027 a
LEFT JOIN dbo.CENTROS_COSTOS_2027 c ON c.DIRECCION = a.DIRECCION
GROUP BY a.CODIGO, a.DESCRIPCION
ORDER BY a.DESCRIPCION;
