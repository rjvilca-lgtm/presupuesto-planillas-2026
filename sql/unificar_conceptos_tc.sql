/*
  Ficha TC: conceptos repetidos con otro nombre en el mismo centro de costo.

  En el Excel 2026 la hoja del I semestre usaba un nombre (en mayúsculas) y la
  del II semestre otro, para la misma actividad, los mismos docentes y horas
  parecidas. Al armar CECO_CONCEPTO_TC entraron los dos y la ficha mostraba
  dos campos para lo mismo. Se deja el nombre estándar (el que usan los demás
  departamentos) y se quita la variante:

    DAIC    01.01.04.01.03  CENTRO DE GESTION DE PROYECTOS E INFRAESTRUCTURA
                            -> Centro de Gestión de Proyectos e Infraestructura
    DAIC    01.01.04.06.04  DEBATE PUBLICO DAIC -> Debate Público
    DCCOMP  01.01.04.06.04  DEBATE PUBLICO DCC  -> Debate Público
    DDER    01.01.03.06.05  DEBATE PUBLICO DCP  -> Debate Público

  Los procedimientos de valorización no usan estos nombres. Si algún plan
  2027 ya tiene horas en una variante, el script se detiene sin cambiar nada
  (al 2026-10-29 no había ninguno). Se puede ejecutar más de una vez.
*/

SET XACT_ABORT ON;
BEGIN TRANSACTION;

DECLARE @pares TABLE (DEPARTAMENTO varchar(10), CENTRO_COSTO nvarchar(100),
                      VARIANTE nvarchar(200), ESTANDAR nvarchar(200));
INSERT INTO @pares VALUES
    ('DAIC',   N'01.01.04.01.03', N'CENTRO DE GESTION DE PROYECTOS E INFRAESTRUCTURA',
                                  N'Centro de Gestión de Proyectos e Infraestructura'),
    ('DAIC',   N'01.01.04.06.04', N'DEBATE PUBLICO DAIC', N'Debate Público'),
    ('DCCOMP', N'01.01.04.06.04', N'DEBATE PUBLICO DCC',  N'Debate Público'),
    ('DDER',   N'01.01.03.06.05', N'DEBATE PUBLICO DCP',  N'Debate Público');

IF EXISTS (SELECT 1 FROM dbo.DATOS_ENTRADA d JOIN @pares p
             ON d.ORIGEN = p.DEPARTAMENTO AND LTRIM(RTRIM(d.CONCEPTO)) = p.VARIANTE
           WHERE d.PRESUPUESTO = 'PPTO2027')
    THROW 50030, 'Hay planes 2027 con horas en una variante: no se cambió nada. Avisa para pasarlas al nombre estándar.', 1;

-- El nombre estándar debe quedar (normalmente ya está)
INSERT INTO dbo.CECO_CONCEPTO_TC (DEPARTAMENTO, CENTRO_COSTO, CONCEPTO)
SELECT p.DEPARTAMENTO, p.CENTRO_COSTO, p.ESTANDAR FROM @pares p
WHERE NOT EXISTS (SELECT 1 FROM dbo.CECO_CONCEPTO_TC t
                  WHERE t.DEPARTAMENTO = p.DEPARTAMENTO AND t.CENTRO_COSTO = p.CENTRO_COSTO
                    AND t.CONCEPTO = p.ESTANDAR);
PRINT CONCAT('Nombres estándar agregados: ', @@ROWCOUNT);

DELETE t FROM dbo.CECO_CONCEPTO_TC t
JOIN @pares p ON t.DEPARTAMENTO = p.DEPARTAMENTO AND t.CENTRO_COSTO = p.CENTRO_COSTO
             AND t.CONCEPTO = p.VARIANTE;
PRINT CONCAT('Variantes quitadas: ', @@ROWCOUNT);

COMMIT;
GO

-- Verificación: una sola fila por centro de costo, con el nombre estándar
SELECT DEPARTAMENTO, CENTRO_COSTO, CONCEPTO, ACTIVO
FROM dbo.CECO_CONCEPTO_TC
WHERE (DEPARTAMENTO = 'DAIC'   AND CENTRO_COSTO IN (N'01.01.04.01.03', N'01.01.04.06.04'))
   OR (DEPARTAMENTO = 'DCCOMP' AND CENTRO_COSTO = N'01.01.04.06.04')
   OR (DEPARTAMENTO = 'DDER'   AND CENTRO_COSTO = N'01.01.03.06.05')
ORDER BY DEPARTAMENTO, CENTRO_COSTO;
