/*
  Ficha del plan TC: un solo nombre por concepto (06/11/2026).

  Algunos conceptos estaban escritos de dos formas según el departamento
  («GESTION DE DIRECCION» y «Gestión de Dirección»), o en mayúsculas cuando el
  resto va en tipo título. Se renombran en la ficha y en las horas 2027 ya
  guardadas, para que lo guardado siga apareciendo en el plan de cada docente.
  Las horas no cambian.

  Se sube la versión del plan TC de los departamentos con horas renombradas:
  quien lo tenga abierto verá el aviso para recargar, en vez de volver a
  guardar con los nombres viejos.

  Se puede ejecutar antes o después de sql/igualar_cecos_facultades_2027.sql,
  y más de una vez. Queda anotado en AUDITORIA_CECOS_2027.
*/
SET XACT_ABORT ON;
BEGIN TRAN;

DECLARE @ahora datetime2 = DATEADD(hour, -5, SYSUTCDATETIME());
DECLARE @quien nvarchar(200) = N'sql/unificar_nombres_ficha_tc_2027.sql';

DECLARE @nombres TABLE (VIEJO nvarchar(200) COLLATE Latin1_General_CS_AS,
                        NUEVO nvarchar(200));
INSERT INTO @nombres VALUES
    (N'GESTION DE DIRECCION',                                     N'Gestión de Dirección'),
    (N'CENTRO DE DESARROLLO PARA LA EDUCACION',                   N'Centro de Desarrollo para la Educación'),
    (N'CENTRO DE ESTUDIOS PERUANOS',                              N'Centro de Estudios Peruanos'),
    (N'COMISION DE PERUANIDAD',                                   N'Comisión de Peruanidad'),
    (N'INSTITUTO PARA EL MATRIMONIO Y FAMILIA',                   N'Instituto para el Matrimonio y Familia'),
    (N'FACULTAD DE ARQUITECTURA, COMPUTACIÓN E INGENIERÍA',       N'Facultad de Arquitectura, Computación e Ingeniería'),
    (N'Facultad de humanidades, matemática y ciencias naturales', N'Facultad de Humanidades, Matemática y Ciencias Naturales');

-- Versión del plan TC de quienes tienen horas guardadas con un nombre viejo
UPDATE g SET VERSION = g.VERSION + 1, EMAIL = N'Presupuesto (nombres de la ficha TC)', FECHA = @ahora
FROM dbo.GUARDADOS_2027 g
WHERE g.PRESUPUESTO = 'PPTO2027'
  AND g.HOJA_ORIGEN IN ('1. Plan TC-I', 'Plan TC-II', 'Plan TC Transversales')
  AND EXISTS (SELECT 1 FROM dbo.DATOS_ENTRADA e JOIN @nombres n
                ON e.CONCEPTO COLLATE Latin1_General_CS_AS = n.VIEJO
              WHERE e.PRESUPUESTO = g.PRESUPUESTO AND e.HOJA_ORIGEN = g.HOJA_ORIGEN
                AND e.ORIGEN = g.ORIGEN);

-- Horas ya guardadas
UPDATE e SET CONCEPTO = n.NUEVO
FROM dbo.DATOS_ENTRADA e
JOIN @nombres n ON e.CONCEPTO COLLATE Latin1_General_CS_AS = n.VIEJO
WHERE e.PRESUPUESTO = 'PPTO2027'
  AND e.HOJA_ORIGEN IN ('1. Plan TC-I', 'Plan TC-II', 'Plan TC Transversales');

-- Ficha (activos e inactivos)
UPDATE t SET CONCEPTO = n.NUEVO
OUTPUT @ahora, @quien, N'FICHA TC RENOMBRAR',
       inserted.DEPARTAMENTO + N' · ' + inserted.CENTRO_COSTO + N': ' + deleted.CONCEPTO + N' → ' + inserted.CONCEPTO
  INTO dbo.AUDITORIA_CECOS_2027 (FECHA, EMAIL, ACCION, DETALLE)
FROM dbo.CECO_CONCEPTO_TC t
JOIN @nombres n ON t.CONCEPTO COLLATE Latin1_General_CS_AS = n.VIEJO;

COMMIT;

SELECT ACCION, DETALLE FROM dbo.AUDITORIA_CECOS_2027
WHERE EMAIL = @quien AND FECHA >= DATEADD(minute, -1, @ahora)
ORDER BY DETALLE;
