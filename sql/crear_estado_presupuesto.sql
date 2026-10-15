/*
  Estado del flujo de presupuesto por departamento (la app lo lee y escribe).

  ESTADO_DEPARTAMENTO: una fila por (PRESUPUESTO, DEPARTAMENTO). DEPARTAMENTO
  es el código de Departamentos.CODIGO, o 'DGA' para la carga académica.
    BLOQUEO            NULL        = se aplica la fecha de bloqueo general
                       'ABIERTO'   = Presupuesto lo desbloqueó (ignora la fecha)
                       'BLOQUEADO' = Presupuesto lo bloqueó
    CERRADO            1 = el departamento cerró su presupuesto (DHUM, DMAT y DCN
                       deben cerrar antes de valorizar la carga académica).
                       Mientras esté cerrado no puede editar; Presupuesto lo reabre.
    FECHA_GUARDADO     último guardado de borrador
    FECHA_VALORIZACION última valorización
    FECHA_CIERRE       cuándo cerró

  CONFIG_PRESUPUESTO: FECHA_BLOQUEO general. Desde esa fecha (hora de Lima)
  los departamentos quedan bloqueados salvo que Presupuesto los desbloquee.

  Se puede ejecutar más de una vez.
*/
IF OBJECT_ID('dbo.ESTADO_DEPARTAMENTO', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ESTADO_DEPARTAMENTO (
        PRESUPUESTO         nvarchar(20)  NOT NULL,
        DEPARTAMENTO        varchar(10)   NOT NULL,
        BLOQUEO             varchar(10)   NULL,
        CERRADO             bit           NOT NULL
            CONSTRAINT DF_ESTADO_DEPARTAMENTO_CERRADO DEFAULT (0),
        FECHA_GUARDADO      datetime2(0)  NULL,
        FECHA_VALORIZACION  datetime2(0)  NULL,
        FECHA_CIERRE        datetime2(0)  NULL,
        ACTUALIZADO         datetime2(0)  NOT NULL
            CONSTRAINT DF_ESTADO_DEPARTAMENTO_ACTUALIZADO DEFAULT (SYSDATETIME()),
        CONSTRAINT PK_ESTADO_DEPARTAMENTO PRIMARY KEY (PRESUPUESTO, DEPARTAMENTO),
        CONSTRAINT CK_ESTADO_DEPARTAMENTO_BLOQUEO
            CHECK (BLOQUEO IS NULL OR BLOQUEO IN ('ABIERTO', 'BLOQUEADO'))
    );
END;
GO

IF OBJECT_ID('dbo.CONFIG_PRESUPUESTO', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.CONFIG_PRESUPUESTO (
        PRESUPUESTO    nvarchar(20)  NOT NULL
            CONSTRAINT PK_CONFIG_PRESUPUESTO PRIMARY KEY,
        FECHA_BLOQUEO  date          NULL,
        ACTUALIZADO    datetime2(0)  NOT NULL
            CONSTRAINT DF_CONFIG_PRESUPUESTO_ACTUALIZADO DEFAULT (SYSDATETIME())
    );
END;
GO

IF NOT EXISTS (SELECT 1 FROM dbo.CONFIG_PRESUPUESTO WHERE PRESUPUESTO = N'PPTO2027')
    INSERT INTO dbo.CONFIG_PRESUPUESTO (PRESUPUESTO, FECHA_BLOQUEO) VALUES (N'PPTO2027', NULL);
GO

-- Verificación
SELECT * FROM dbo.CONFIG_PRESUPUESTO;
SELECT * FROM dbo.ESTADO_DEPARTAMENTO;
