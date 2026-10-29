/*
  Ficha TC de DHUM: el Centro de Estudios Peruanos salía dentro del centro de
  costo 01.01.07.01.02 (Instituto para el Matrimonio y Familia).

  En el Excel 2026 los dos iban bajo el mismo código antiguo 03.01.11.04.02
  (hoja Plan TC Transversales). Al pasar CECO_CONCEPTO_TC a los códigos 2027
  (sql/crear_cecos_2027.sql), ese código se volvió 01.01.07.01.02 para los dos,
  pero el Centro de Estudios Peruanos es el 01.01.07.01.03 (03.01.11.04.04).

  Mueve ese concepto a su centro de costo. Al 2026-10-29 ningún plan 2027
  usaba esos conceptos. Se puede ejecutar más de una vez.
*/

BEGIN TRANSACTION;

UPDATE dbo.CECO_CONCEPTO_TC
SET CENTRO_COSTO = N'01.01.07.01.03'
WHERE DEPARTAMENTO = 'DHUM'
  AND CENTRO_COSTO = N'01.01.07.01.02'
  AND CONCEPTO = N'CENTRO DE ESTUDIOS PERUANOS'
  AND NOT EXISTS (SELECT 1 FROM dbo.CECO_CONCEPTO_TC x
                  WHERE x.DEPARTAMENTO = 'DHUM' AND x.CENTRO_COSTO = N'01.01.07.01.03'
                    AND x.CONCEPTO = N'CENTRO DE ESTUDIOS PERUANOS');
PRINT CONCAT('Filas movidas: ', @@ROWCOUNT);

-- Si ya existía en el 03 (ejecución anterior), sobra la del 02
DELETE FROM dbo.CECO_CONCEPTO_TC
WHERE DEPARTAMENTO = 'DHUM'
  AND CENTRO_COSTO = N'01.01.07.01.02'
  AND CONCEPTO = N'CENTRO DE ESTUDIOS PERUANOS';

COMMIT;
GO

-- Verificación: el 02 con el Instituto y el 03 con el Centro de Estudios Peruanos
SELECT t.CENTRO_COSTO, c.DESCRIPCION_CC, t.CONCEPTO, t.ACTIVO
FROM dbo.CECO_CONCEPTO_TC t
LEFT JOIN dbo.CENTROS_COSTOS_2027 c ON c.CENTRO_COSTO = t.CENTRO_COSTO
WHERE t.DEPARTAMENTO = 'DHUM' AND t.CENTRO_COSTO IN (N'01.01.07.01.02', N'01.01.07.01.03')
ORDER BY t.CENTRO_COSTO;
