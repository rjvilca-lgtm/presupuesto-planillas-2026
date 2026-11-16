/*
  Valorización 2027 de Prácticas pre-profesionales y Puestos nuevos.

  Hasta ahora estas dos pestañas solo guardaban en DATOS_ENTRADA: no llegaban a
  PLANILLA ni sumaban en «Presupuesto 2027», «Meta vs Presupuesto 2027» ni en el
  árbol de «Planillas 2027» (donde caen en la rama OTROS).

    sp_Valorizar_Practicas_2027
      PLANILLA.ORIGEN = 'Practicas', partida 94.1.1.1.021 (PRACTICANTES), en el
      centro de cada pedido. Importe = horas × tarifa por hora vigente de
      tarifas_2027 (HOJA_ORIGEN 'Practicas'); si no hay tarifa, la de la fila.
      Sin cargas sociales (subvención de practicante).

    sp_Valorizar_PuestosNuevos_2027
      PLANILLA.ORIGEN = 'Puestos nuevos', partida 94.1.1.1.001 (SUELDOS
      ADMINISTRATIVOS), en el centro de cada puesto (decisión 2026-11-16: el centro
      ve el costo de sus puestos). Importe = puestos del mes × costo mensual vigente
      de tarifas_2027 (HOJA_ORIGEN 'Puestos nuevos', por TIPO); si no hay, el de la
      fila. El costo mensual ya incluye bonos, Edenred y cargas sociales, así que no
      se agregan cargas.

  Los dos usan la tarifa vigente (no la que quedó en la fila al guardar) porque
  Desarrollo Humano puede cambiar tarifas y costos después de que se registraron.

  @OrigenEntrada = código del departamento o área (DATOS_ENTRADA.ORIGEN);
  NULL = todos. Cada ejecución reemplaza lo valorizado de ese alcance, en una sola
  transacción. Solo filas con PRESUPUESTO = 'PPTO2027', mes 1-12 y centro de costo.

  Ojo: sp_Importar_DDH_2027 borra de PLANILLA 2027 las filas con ORIGEN_2 = 'DDH'
  que no son de Desarrollo Humano. Si el área DDH registra puestos o prácticas con
  su código 'DDH', se borrarían al importar la valorización DDH: hay que valorizar
  de nuevo después de cada importación DDH (o registrar con otro código).

  Ejecutar con la cuenta administradora, base Saldos. Se puede ejecutar más de una vez.
  Para valorizar todo ahora (al final de este archivo):
      EXEC dbo.sp_Valorizar_Practicas_2027;
      EXEC dbo.sp_Valorizar_PuestosNuevos_2027;
*/

CREATE OR ALTER PROCEDURE dbo.sp_Valorizar_Practicas_2027
    @OrigenEntrada nvarchar(100) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @Origen nvarchar(100) = N'Practicas',
            @Presupuesto nvarchar(20) = N'PPTO2027';
    DECLARE @Tarifa decimal(18, 4) = (SELECT MAX(TARIFA) FROM dbo.tarifas_2027 WHERE HOJA_ORIGEN = 'Practicas');

    BEGIN TRANSACTION;

    DELETE FROM dbo.PLANILLA
    WHERE AÑO = '2027' AND ORIGEN = @Origen
      AND (@OrigenEntrada IS NULL OR ORIGEN_2 = @OrigenEntrada);

    INSERT INTO dbo.PLANILLA (CENTRO_COSTO, PARTIDA, MES, IMPORTE, ORIGEN, HORAS, ORIGEN_2, AÑO)
    SELECT  LTRIM(RTRIM(de.CENTRO_COSTO)),
            '94.1.1.1.021',
            TRY_CAST(de.MES AS int),
            ROUND(de.HORAS * COALESCE(NULLIF(@Tarifa, 0), NULLIF(de.TARIFA, 0), 0), 2),
            @Origen,
            de.HORAS,
            de.ORIGEN,
            2027
    FROM dbo.DATOS_ENTRADA de
    WHERE de.PRESUPUESTO = @Presupuesto
      AND de.HOJA_ORIGEN = @Origen
      AND (@OrigenEntrada IS NULL OR de.ORIGEN = @OrigenEntrada)
      AND ISNULL(de.HORAS, 0) > 0
      AND TRY_CAST(de.MES AS int) BETWEEN 1 AND 12
      AND NULLIF(LTRIM(RTRIM(de.CENTRO_COSTO)), '') IS NOT NULL;

    COMMIT;

    SELECT ORIGEN_2 AS DEPARTAMENTO, COUNT(*) AS Registros, SUM(HORAS) AS Horas, SUM(IMPORTE) AS Total
    FROM dbo.PLANILLA
    WHERE AÑO = '2027' AND ORIGEN = @Origen AND (@OrigenEntrada IS NULL OR ORIGEN_2 = @OrigenEntrada)
    GROUP BY ORIGEN_2;
END;
GO

CREATE OR ALTER PROCEDURE dbo.sp_Valorizar_PuestosNuevos_2027
    @OrigenEntrada nvarchar(100) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @Origen nvarchar(100) = N'Puestos nuevos',
            @Presupuesto nvarchar(20) = N'PPTO2027';

    BEGIN TRANSACTION;

    DELETE FROM dbo.PLANILLA
    WHERE AÑO = '2027' AND ORIGEN = @Origen
      AND (@OrigenEntrada IS NULL OR ORIGEN_2 = @OrigenEntrada);

    INSERT INTO dbo.PLANILLA (CENTRO_COSTO, PARTIDA, MES, IMPORTE, ORIGEN, HORAS, ORIGEN_2, AÑO)
    SELECT  LTRIM(RTRIM(de.CENTRO_COSTO)),
            '94.1.1.1.001',
            TRY_CAST(de.MES AS int),
            ROUND(de.HORAS * COALESCE(NULLIF(t.COSTO, 0), NULLIF(de.TARIFA, 0), 0), 2),
            @Origen,
            de.HORAS,          -- puestos en el mes
            de.ORIGEN,
            2027
    FROM dbo.DATOS_ENTRADA de
    OUTER APPLY (SELECT MAX(x.TARIFA) AS COSTO FROM dbo.tarifas_2027 x
                 WHERE x.HOJA_ORIGEN = 'Puestos nuevos'
                   AND LTRIM(RTRIM(x.TIPO)) = LTRIM(RTRIM(de.TIPO))) t
    WHERE de.PRESUPUESTO = @Presupuesto
      AND de.HOJA_ORIGEN = @Origen
      AND (@OrigenEntrada IS NULL OR de.ORIGEN = @OrigenEntrada)
      AND ISNULL(de.HORAS, 0) > 0
      AND TRY_CAST(de.MES AS int) BETWEEN 1 AND 12
      AND NULLIF(LTRIM(RTRIM(de.CENTRO_COSTO)), '') IS NOT NULL;

    COMMIT;

    SELECT ORIGEN_2 AS DEPARTAMENTO, COUNT(*) AS Registros, SUM(HORAS) AS Puestos_mes, SUM(IMPORTE) AS Total
    FROM dbo.PLANILLA
    WHERE AÑO = '2027' AND ORIGEN = @Origen AND (@OrigenEntrada IS NULL OR ORIGEN_2 = @OrigenEntrada)
    GROUP BY ORIGEN_2;
END;
GO

-- La app los podrá llamar como a los demás sp de valorización
GRANT EXECUTE ON dbo.sp_Valorizar_Practicas_2027     TO rol_app_planillas;
GRANT EXECUTE ON dbo.sp_Valorizar_PuestosNuevos_2027 TO rol_app_planillas;
GO

-- Antes de valorizar: filas que quedarían en 0 por no tener tarifa o costo
SELECT de.HOJA_ORIGEN, de.ORIGEN, de.CENTRO_COSTO, de.TIPO, COUNT(*) AS filas
FROM dbo.DATOS_ENTRADA de
WHERE de.PRESUPUESTO = N'PPTO2027' AND de.HOJA_ORIGEN IN (N'Practicas', N'Puestos nuevos') AND ISNULL(de.HORAS, 0) > 0
  AND ISNULL(de.TARIFA, 0) = 0
  AND NOT EXISTS (SELECT 1 FROM dbo.tarifas_2027 t
                  WHERE t.HOJA_ORIGEN = de.HOJA_ORIGEN AND ISNULL(t.TARIFA, 0) > 0
                    AND (de.HOJA_ORIGEN = N'Practicas' OR LTRIM(RTRIM(t.TIPO)) = LTRIM(RTRIM(de.TIPO))))
GROUP BY de.HOJA_ORIGEN, de.ORIGEN, de.CENTRO_COSTO, de.TIPO;

-- Valorizar todo ahora
EXEC dbo.sp_Valorizar_Practicas_2027;
EXEC dbo.sp_Valorizar_PuestosNuevos_2027;

-- Verificación: debe coincidir con lo registrado en la app (horas × tarifa; puestos × costo)
SELECT ORIGEN, PARTIDA, COUNT(*) AS filas, SUM(IMPORTE) AS total
FROM dbo.PLANILLA
WHERE AÑO = '2027' AND ORIGEN IN (N'Practicas', N'Puestos nuevos')
GROUP BY ORIGEN, PARTIDA;
