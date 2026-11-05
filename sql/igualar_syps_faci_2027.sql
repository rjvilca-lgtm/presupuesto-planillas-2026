/*
  Facultad de Arquitectura, Computación e Ingeniería (FACI): los centros de
  Servicio y Proyección a la Sociedad (01.01.04.06.xx) deben ser los mismos en
  sus departamentos DAIC, DIEE y DIIA.

  Diferencias encontradas el 05/11/2026 (ningún departamento tiene aún datos
  2027 guardados en estos centros, así que nada se pierde):

  Pueden presupuestarlos (CECOS_DEPARTAMENTO_2027):
    01.01.04.06.05 SERVICIOS DIVERSOS FACI ............ faltaba DIIA
    01.01.04.06.06 GESTION HIDRICA CUENCA QUILCA-CHILI . faltaban DAIC y DIEE

  Ficha del plan TC (CECO_CONCEPTO_TC):
    01.01.04.06.01: DAIC y DIIA tenían dos conceptos para lo mismo
      («Gestión Administrativa SYPS» y «GESTION ADMINISTRATIVA SERVICIO Y
      PROYECCION A LA SOCIEDAD FACI», agregado hoy) y DIEE solo el segundo.
      Queda en los tres el nombre que usan las demás facultades, «Gestión
      Administrativa SYPS»; el otro se desactiva (no se borra).
    01.01.04.06.02 Proyectos Solidarios, .03 Servicio a Terceros y
      .04 Debate Público: solo los tenía DAIC; se agregan a DIEE y DIIA.
    01.01.04.06.05 y .06 no están en la ficha de ningún departamento: se
      dejan así (se presupuestan en las demás planillas).

  Todo en una transacción y anotado en AUDITORIA_CECOS_2027. Se puede
  ejecutar más de una vez.
*/
SET XACT_ABORT ON;
BEGIN TRAN;

DECLARE @deptos TABLE (DEPARTAMENTO varchar(20));
INSERT INTO @deptos VALUES ('DAIC'), ('DIEE'), ('DIIA');
DECLARE @ahora datetime2 = DATEADD(hour, -5, SYSUTCDATETIME());
DECLARE @quien nvarchar(200) = N'sql/igualar_syps_faci_2027.sql';

-- 1. Los seis centros SYPS, asignados a los tres departamentos
INSERT INTO dbo.CECOS_DEPARTAMENTO_2027 (DEPARTAMENTO, CENTRO_COSTO)
OUTPUT @ahora, @quien, N'ASIGNAR', inserted.DEPARTAMENTO + N' · ' + inserted.CENTRO_COSTO
  INTO dbo.AUDITORIA_CECOS_2027 (FECHA, EMAIL, ACCION, DETALLE)
SELECT d.DEPARTAMENTO, c.CENTRO_COSTO
FROM @deptos d CROSS JOIN dbo.CENTROS_COSTOS_2027 c
WHERE c.CENTRO_COSTO LIKE '01.01.04.06.%'
  AND NOT EXISTS (SELECT 1 FROM dbo.CECOS_DEPARTAMENTO_2027 x
                  WHERE x.DEPARTAMENTO = d.DEPARTAMENTO AND x.CENTRO_COSTO = c.CENTRO_COSTO);

-- 2. Ficha TC: los mismos conceptos en los tres
DECLARE @ficha TABLE (CENTRO_COSTO varchar(20), CONCEPTO nvarchar(200));
INSERT INTO @ficha VALUES
    ('01.01.04.06.01', N'Gestión Administrativa SYPS'),
    ('01.01.04.06.02', N'Proyectos Solidarios'),
    ('01.01.04.06.03', N'Servicio a Terceros'),
    ('01.01.04.06.04', N'Debate Público');

UPDATE t SET ACTIVO = 1
OUTPUT @ahora, @quien, N'FICHA TC REACTIVAR', inserted.DEPARTAMENTO + N' · ' + inserted.CENTRO_COSTO + N': ' + inserted.CONCEPTO
  INTO dbo.AUDITORIA_CECOS_2027 (FECHA, EMAIL, ACCION, DETALLE)
FROM dbo.CECO_CONCEPTO_TC t
JOIN @deptos d ON d.DEPARTAMENTO = t.DEPARTAMENTO
JOIN @ficha f ON f.CENTRO_COSTO = t.CENTRO_COSTO AND f.CONCEPTO = t.CONCEPTO
WHERE t.ACTIVO = 0;

INSERT INTO dbo.CECO_CONCEPTO_TC (DEPARTAMENTO, CENTRO_COSTO, CONCEPTO, ACTIVO)
OUTPUT @ahora, @quien, N'FICHA TC AGREGAR', inserted.DEPARTAMENTO + N' · ' + inserted.CENTRO_COSTO + N': ' + inserted.CONCEPTO
  INTO dbo.AUDITORIA_CECOS_2027 (FECHA, EMAIL, ACCION, DETALLE)
SELECT d.DEPARTAMENTO, f.CENTRO_COSTO, f.CONCEPTO, 1
FROM @deptos d CROSS JOIN @ficha f
WHERE NOT EXISTS (SELECT 1 FROM dbo.CECO_CONCEPTO_TC x WHERE x.DEPARTAMENTO = d.DEPARTAMENTO
                  AND x.CENTRO_COSTO = f.CENTRO_COSTO AND x.CONCEPTO = f.CONCEPTO);

-- El concepto duplicado de 06.01 se desactiva (si alguien ya tuviera horas
-- guardadas con él, no se toca y queda en el listado de abajo)
UPDATE t SET ACTIVO = 0
OUTPUT @ahora, @quien, N'FICHA TC QUITAR', inserted.DEPARTAMENTO + N' · ' + inserted.CENTRO_COSTO + N': ' + inserted.CONCEPTO
  INTO dbo.AUDITORIA_CECOS_2027 (FECHA, EMAIL, ACCION, DETALLE)
FROM dbo.CECO_CONCEPTO_TC t
JOIN @deptos d ON d.DEPARTAMENTO = t.DEPARTAMENTO
WHERE t.CENTRO_COSTO = '01.01.04.06.01' AND t.ACTIVO = 1
  AND t.CONCEPTO = N'GESTION ADMINISTRATIVA SERVICIO Y PROYECCION A LA SOCIEDAD FACI'
  AND NOT EXISTS (SELECT 1 FROM dbo.DATOS_ENTRADA e WHERE e.PRESUPUESTO = 'PPTO2027'
                  AND e.ORIGEN = t.DEPARTAMENTO AND e.CENTRO_COSTO = t.CENTRO_COSTO
                  AND e.CONCEPTO = t.CONCEPTO);

COMMIT;

-- Verificación: cada fila debe decir DAIC, DIEE, DIIA en las dos columnas
-- (05 y 06 solo en la primera: no van en la ficha TC)
SELECT c.CENTRO_COSTO, c.DESCRIPCION_CC,
       (SELECT STRING_AGG(d.DEPARTAMENTO, ', ') WITHIN GROUP (ORDER BY d.DEPARTAMENTO)
        FROM dbo.CECOS_DEPARTAMENTO_2027 d WHERE d.CENTRO_COSTO = c.CENTRO_COSTO
          AND d.DEPARTAMENTO IN ('DAIC', 'DIEE', 'DIIA')) AS PUEDEN_PRESUPUESTARLO,
       (SELECT STRING_AGG(t.DEPARTAMENTO + ': ' + t.CONCEPTO, ' | ')
                 WITHIN GROUP (ORDER BY t.DEPARTAMENTO)
        FROM dbo.CECO_CONCEPTO_TC t WHERE t.CENTRO_COSTO = c.CENTRO_COSTO AND t.ACTIVO = 1
          AND t.DEPARTAMENTO IN ('DAIC', 'DIEE', 'DIIA')) AS FICHA_TC
FROM dbo.CENTROS_COSTOS_2027 c
WHERE c.CENTRO_COSTO LIKE '01.01.04.06.%'
ORDER BY c.CENTRO_COSTO;
