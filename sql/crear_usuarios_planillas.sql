/*
  USUARIOS_PLANILLAS: quién puede entrar a la app y qué puede hacer.
  El usuario entra con su cuenta Google @ucsp.edu.pe; la app busca su correo aquí.

    ROL = 'PRESUPUESTO'   ve todos los departamentos, la carga académica y la
                          pestaña de administración (bloqueos, usuarios).
    ROL = 'DGA'           registra y valoriza la carga académica.
    ROL = 'DEPARTAMENTO'  registra las planillas de DEPARTAMENTO (código de
                          Departamentos.CODIGO). Una fila por departamento si
                          maneja más de uno.
  Todos pueden ver la consulta de carga académica.
  Para quitar un acceso sin borrarlo: ACTIVO = 0.

  Se puede ejecutar más de una vez.
*/
IF OBJECT_ID('dbo.USUARIOS_PLANILLAS', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.USUARIOS_PLANILLAS (
        ID              int IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_USUARIOS_PLANILLAS PRIMARY KEY,
        EMAIL           nvarchar(150) NOT NULL,
        ROL             varchar(20)   NOT NULL,
        DEPARTAMENTO    varchar(10)   NULL,
        ACTIVO          bit           NOT NULL
            CONSTRAINT DF_USUARIOS_PLANILLAS_ACTIVO DEFAULT (1),
        FECHA_REGISTRO  datetime2(0)  NOT NULL
            CONSTRAINT DF_USUARIOS_PLANILLAS_FECHA DEFAULT (SYSDATETIME()),
        CONSTRAINT CK_USUARIOS_PLANILLAS_ROL
            CHECK (ROL IN ('PRESUPUESTO', 'DGA', 'DEPARTAMENTO')),
        CONSTRAINT CK_USUARIOS_PLANILLAS_DEPTO
            CHECK ((ROL = 'DEPARTAMENTO' AND DEPARTAMENTO IS NOT NULL)
                OR (ROL <> 'DEPARTAMENTO' AND DEPARTAMENTO IS NULL))
    );
    CREATE UNIQUE INDEX UX_USUARIOS_PLANILLAS
        ON dbo.USUARIOS_PLANILLAS (EMAIL, ROL, DEPARTAMENTO);
END;
GO

-- Primer usuario de Presupuesto (después se administran desde la app)
IF NOT EXISTS (SELECT 1 FROM dbo.USUARIOS_PLANILLAS
               WHERE EMAIL = N'rjvilca@ucsp.edu.pe' AND ROL = 'PRESUPUESTO')
    INSERT INTO dbo.USUARIOS_PLANILLAS (EMAIL, ROL) VALUES (N'rjvilca@ucsp.edu.pe', 'PRESUPUESTO');
GO

-- Verificación
SELECT EMAIL, ROL, DEPARTAMENTO, ACTIVO FROM dbo.USUARIOS_PLANILLAS ORDER BY EMAIL, ROL;
