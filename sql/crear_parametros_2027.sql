/*
  Parámetros de valorización 2027 (cargas sociales y factor de grados).

  Antes estaban escritos dentro de los sp_*_2027; ahora los sp los leen de
  PARAMETROS_2027 y Presupuesto los cambia desde la app (pestaña de
  administración). Cada cambio queda en AUDITORIA_PARAMETROS (valor anterior y
  nuevo; no son datos confidenciales).

  Valores iniciales = los de 2026. Orden: este script y luego
  sql/crear_sps_2027.sql (los sp nuevos fallan si falta un parámetro).
  Se puede ejecutar más de una vez: no pisa valores ya cambiados.
*/

IF OBJECT_ID('dbo.PARAMETROS_2027', 'U') IS NULL
    CREATE TABLE dbo.PARAMETROS_2027 (
        CODIGO      varchar(40)    NOT NULL CONSTRAINT PK_PARAMETROS_2027 PRIMARY KEY,
        DESCRIPCION nvarchar(200)  NOT NULL,
        VALOR       decimal(9,6)   NOT NULL CONSTRAINT CK_PARAMETROS_2027_VALOR CHECK (VALOR >= 0),
        ORDEN       int            NOT NULL,
        ACTUALIZADO datetime2(0)   NOT NULL CONSTRAINT DF_PARAMETROS_2027_ACT DEFAULT (SYSDATETIME()),
        EMAIL       nvarchar(150)  NULL
    );
GO

IF OBJECT_ID('dbo.AUDITORIA_PARAMETROS', 'U') IS NULL
    CREATE TABLE dbo.AUDITORIA_PARAMETROS (
        ID              int IDENTITY(1,1) NOT NULL CONSTRAINT PK_AUDITORIA_PARAMETROS PRIMARY KEY,
        FECHA           datetime2(0)  NOT NULL CONSTRAINT DF_AUDITORIA_PARAMETROS_FECHA DEFAULT (SYSDATETIME()),
        EMAIL           nvarchar(150) NOT NULL,
        CODIGO          varchar(40)   NOT NULL,
        VALOR_ANTERIOR  decimal(9,6)  NULL,
        VALOR_NUEVO     decimal(9,6)  NOT NULL
    );
GO

MERGE dbo.PARAMETROS_2027 AS t
USING (VALUES
    ('GRATIFICACION', N'Gratificación (proporción de la remuneración)',                 0.1817, 1),
    ('ESSALUD',       N'EsSalud',                                                      0.09,   2),
    ('CTS',           N'CTS (solo tiempo completo)',                                   0.0972, 3),
    ('VACACIONES',    N'Vacaciones (solo tiempo completo)',                            0.1599, 4),
    ('VIDA_LEY',      N'Seguro Vida Ley (solo tiempo completo)',                       0.0038, 5),
    ('ASIG_FAMILIAR', N'Asignación familiar (solo carga académica)',                   0.0132, 6),
    ('FACTOR_GRADOS', N'Factor maestrías y doctorados (titulares de carga académica)', 1.0851, 7)
) AS s (CODIGO, DESCRIPCION, VALOR, ORDEN)
ON t.CODIGO = s.CODIGO
WHEN NOT MATCHED THEN
    INSERT (CODIGO, DESCRIPCION, VALOR, ORDEN, EMAIL)
    VALUES (s.CODIGO, s.DESCRIPCION, s.VALOR, s.ORDEN, N'valor inicial (2026)');
GO

SELECT CODIGO, DESCRIPCION, VALOR FROM dbo.PARAMETROS_2027 ORDER BY ORDEN;
