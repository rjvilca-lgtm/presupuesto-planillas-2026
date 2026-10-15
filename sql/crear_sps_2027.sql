/*
  Procedimientos de valorización 2027 (los llama la app).

  Copias de los sp_*_2026 con estos cambios, y nada más:
    - @Anio = 2027: en PLANILLA quedan separados de 2026.
    - Leen solo DATOS_ENTRADA con PRESUPUESTO = 'PPTO2027'.
    - Tarifas desde tarifas_2027 en vez de valores fijos
      (Horas Adicionales sin TARIFA en la fila, Ayudantías y Carga Académica).
    - Investigación: el DELETE final usaba AÑO='2026' fijo; ahora usa @Anio.
    - Carga Académica: semestres '2027-1' / '2027-2'.
    - Cargas sociales y factor de grados desde PARAMETROS_2027
      (sql/crear_parametros_2027.sql): ejecutar ese script antes que este.
  Los sp_*_2026 no se modifican. CREATE OR ALTER: se puede ejecutar de nuevo.
  Generado desde las definiciones en Azure del 2026-10-14.
*/

CREATE OR ALTER PROCEDURE [dbo].[sp_Valorizar_HorasAdicionales_2027]
    @OrigenEntrada NVARCHAR(100)  -- 🔹 Nuevo parámetro: DATOS_ENTRADA.ORIGEN
AS
BEGIN
    SET NOCOUNT ON;

    -- Tasas desde PARAMETROS_2027 (sql/crear_parametros_2027.sql); antes fijas
    DECLARE @TasaGrat DECIMAL(9,6), @TasaEssalud DECIMAL(9,6), @TasaCTS DECIMAL(9,6),
            @TasaVac DECIMAL(9,6), @TasaVidaLey DECIMAL(9,6), @TasaAsigFam DECIMAL(9,6),
            @FactorGrados DECIMAL(9,6);
    SELECT @TasaGrat     = MAX(CASE WHEN CODIGO = 'GRATIFICACION' THEN VALOR END),
           @TasaEssalud  = MAX(CASE WHEN CODIGO = 'ESSALUD'       THEN VALOR END),
           @TasaCTS      = MAX(CASE WHEN CODIGO = 'CTS'           THEN VALOR END),
           @TasaVac      = MAX(CASE WHEN CODIGO = 'VACACIONES'    THEN VALOR END),
           @TasaVidaLey  = MAX(CASE WHEN CODIGO = 'VIDA_LEY'      THEN VALOR END),
           @TasaAsigFam  = MAX(CASE WHEN CODIGO = 'ASIG_FAMILIAR' THEN VALOR END),
           @FactorGrados = MAX(CASE WHEN CODIGO = 'FACTOR_GRADOS' THEN VALOR END)
    FROM dbo.PARAMETROS_2027;
    IF @TasaGrat IS NULL OR @TasaEssalud IS NULL OR @TasaCTS IS NULL OR @TasaVac IS NULL
       OR @TasaVidaLey IS NULL OR @TasaAsigFam IS NULL OR @FactorGrados IS NULL
        THROW 50011, 'Faltan parámetros en PARAMETROS_2027 (sql/crear_parametros_2027.sql).', 1;


    ------------------------------------------------------------
    -- Declaraciones iniciales
    ------------------------------------------------------------
    DECLARE 
        @Anio INT = 2027,
        @Presupuesto NVARCHAR(20) = N'PPTO2027',
        @Origen NVARCHAR(100) = 'Horas Adicionales',
        @RegistrosRem INT = 0,
        @RegistrosGrat INT = 0,
        @RegistrosEssalud INT = 0;

    ------------------------------------------------------------
    -- 1️⃣ ELIMINAR REGISTROS PREVIOS DEL MISMO ORIGEN Y AÑO
    ------------------------------------------------------------
    PRINT 'Eliminando registros previos de PLANILLA...';
    DELETE FROM PLANILLA
    WHERE AÑO = @Anio
      AND ORIGEN = @Origen
      AND ORIGEN_2 = @OrigenEntrada;

    PRINT 'Registros eliminados: ' + CAST(@@ROWCOUNT AS VARCHAR(10));

    ------------------------------------------------------------
    -- 2️⃣ INSERTAR REGISTROS BASE (SUELDO BRUTO)
    ------------------------------------------------------------
    INSERT INTO PLANILLA (CENTRO_COSTO, PARTIDA, MES, IMPORTE, ORIGEN, ORIGEN_2, AÑO)
    SELECT
        de.CENTRO_COSTO,
        '94.1.1.1.033' AS PARTIDA,  -- Sueldo Bruto
        CASE 
            WHEN ISNUMERIC(de.MES) = 1 THEN CAST(de.MES AS INT)
            WHEN LOWER(LTRIM(RTRIM(de.MES))) = 'enero' THEN 1
            WHEN LOWER(LTRIM(RTRIM(de.MES))) = 'febrero' THEN 2
            WHEN LOWER(LTRIM(RTRIM(de.MES))) = 'marzo' THEN 3
            WHEN LOWER(LTRIM(RTRIM(de.MES))) = 'abril' THEN 4
            WHEN LOWER(LTRIM(RTRIM(de.MES))) = 'mayo' THEN 5
            WHEN LOWER(LTRIM(RTRIM(de.MES))) = 'junio' THEN 6
            WHEN LOWER(LTRIM(RTRIM(de.MES))) = 'julio' THEN 7
            WHEN LOWER(LTRIM(RTRIM(de.MES))) = 'agosto' THEN 8
            WHEN LOWER(LTRIM(RTRIM(de.MES))) IN ('setiembre','septiembre') THEN 9
            WHEN LOWER(LTRIM(RTRIM(de.MES))) = 'octubre' THEN 10
            WHEN LOWER(LTRIM(RTRIM(de.MES))) = 'noviembre' THEN 11
            WHEN LOWER(LTRIM(RTRIM(de.MES))) = 'diciembre' THEN 12
            ELSE NULL
        END AS MES,
        CASE 
            WHEN de.TARIFA IS NULL OR de.TARIFA = 0 THEN
                -- Sin TARIFA en la fila: se toma de tarifas_2027 según el TIPO
                ROUND(ISNULL(de.HORAS,0) * ISNULL((SELECT MAX(t.TARIFA) FROM tarifas_2027 t
                    WHERE t.HOJA_ORIGEN = @Origen
                      AND LOWER(LTRIM(RTRIM(t.TIPO))) = LOWER(LTRIM(RTRIM(de.TIPO)))), 0), 2)
            ELSE ROUND(ISNULL(de.HORAS,0) * ISNULL(de.TARIFA,0), 2)
        END AS IMPORTE,
        @Origen AS ORIGEN,            -- Fijo: Hoja de origen
        @OrigenEntrada AS ORIGEN_2,   -- Parametro dinámico (Origen de DATOS_ENTRADA)
        @Anio AS AÑO
    FROM DATOS_ENTRADA de
    WHERE de.HOJA_ORIGEN = @Origen
      AND de.ORIGEN = @OrigenEntrada
      AND de.PRESUPUESTO = @Presupuesto
      AND ISNULL(de.HORAS,0) > 0;

    SET @RegistrosRem = @@ROWCOUNT;

    ------------------------------------------------------------
    -- 3️⃣ GRATIFICACIÓN (18.17%) → PARTIDA 94.1.1.1.036
    ------------------------------------------------------------
    INSERT INTO PLANILLA (CENTRO_COSTO, PARTIDA, MES, IMPORTE, ORIGEN, ORIGEN_2, AÑO)
    SELECT
        p.CENTRO_COSTO,
        '94.1.1.1.036',
        p.MES,
        ROUND(p.IMPORTE * @TasaGrat, 2),
        p.ORIGEN,
        p.ORIGEN_2,
        p.AÑO
    FROM PLANILLA p
    WHERE p.ORIGEN = @Origen
      AND p.ORIGEN_2 = @OrigenEntrada
      AND p.AÑO = @Anio
      AND p.PARTIDA = '94.1.1.1.033';
    SET @RegistrosGrat = @@ROWCOUNT;

    ------------------------------------------------------------
    -- 4️⃣ ESSALUD (9%) → PARTIDA 94.1.1.1.035
    ------------------------------------------------------------
    INSERT INTO PLANILLA (CENTRO_COSTO, PARTIDA, MES, IMPORTE, ORIGEN, ORIGEN_2, AÑO)
    SELECT
        p.CENTRO_COSTO,
        '94.1.1.1.035',
        p.MES,
        ROUND(p.IMPORTE * @TasaEssalud, 2),
        p.ORIGEN,
        p.ORIGEN_2,
        p.AÑO
    FROM PLANILLA p
    WHERE p.ORIGEN = @Origen
      AND p.ORIGEN_2 = @OrigenEntrada
      AND p.AÑO = @Anio
      AND p.PARTIDA = '94.1.1.1.033';
    SET @RegistrosEssalud = @@ROWCOUNT;

    ------------------------------------------------------------
    -- 5️⃣ RESUMEN FINAL
    ------------------------------------------------------------
    PRINT '==============================================';
    PRINT 'VALORIZACIÓN HORAS ADICIONALES - AÑO ' + CAST(@Anio AS VARCHAR(10));
    PRINT 'DATOS_ENTRADA.ORIGEN: ' + ISNULL(@OrigenEntrada,'(NULL)');
    PRINT 'Sueldo Bruto (94.1.1.1.033): ' + CAST(@RegistrosRem AS VARCHAR(10));
    PRINT 'Gratificación (94.1.1.1.036): ' + CAST(@RegistrosGrat AS VARCHAR(10));
    PRINT 'Essalud (94.1.1.1.035): ' + CAST(@RegistrosEssalud AS VARCHAR(10));
    PRINT '==============================================';

    SELECT 
        @Origen AS Origen_Hoja,
        @OrigenEntrada AS Origen_Datos,
        @RegistrosRem AS RegistrosSueldoBruto,
        @RegistrosGrat AS RegistrosGratificacion,
        @RegistrosEssalud AS RegistrosEssalud,
        @RegistrosRem + @RegistrosGrat + @RegistrosEssalud AS TotalRegistros,
        GETDATE() AS FechaEjecucion;

END;
GO

CREATE OR ALTER PROCEDURE [dbo].[sp_Valorizar_Postgrado_2027]
    @OrigenEntrada NVARCHAR(100)  -- 🔹 Parámetro dinámico para DATOS_ENTRADA.ORIGEN
AS
BEGIN
    SET NOCOUNT ON;

    -- Tasas desde PARAMETROS_2027 (sql/crear_parametros_2027.sql); antes fijas
    DECLARE @TasaGrat DECIMAL(9,6), @TasaEssalud DECIMAL(9,6), @TasaCTS DECIMAL(9,6),
            @TasaVac DECIMAL(9,6), @TasaVidaLey DECIMAL(9,6), @TasaAsigFam DECIMAL(9,6),
            @FactorGrados DECIMAL(9,6);
    SELECT @TasaGrat     = MAX(CASE WHEN CODIGO = 'GRATIFICACION' THEN VALOR END),
           @TasaEssalud  = MAX(CASE WHEN CODIGO = 'ESSALUD'       THEN VALOR END),
           @TasaCTS      = MAX(CASE WHEN CODIGO = 'CTS'           THEN VALOR END),
           @TasaVac      = MAX(CASE WHEN CODIGO = 'VACACIONES'    THEN VALOR END),
           @TasaVidaLey  = MAX(CASE WHEN CODIGO = 'VIDA_LEY'      THEN VALOR END),
           @TasaAsigFam  = MAX(CASE WHEN CODIGO = 'ASIG_FAMILIAR' THEN VALOR END),
           @FactorGrados = MAX(CASE WHEN CODIGO = 'FACTOR_GRADOS' THEN VALOR END)
    FROM dbo.PARAMETROS_2027;
    IF @TasaGrat IS NULL OR @TasaEssalud IS NULL OR @TasaCTS IS NULL OR @TasaVac IS NULL
       OR @TasaVidaLey IS NULL OR @TasaAsigFam IS NULL OR @FactorGrados IS NULL
        THROW 50011, 'Faltan parámetros en PARAMETROS_2027 (sql/crear_parametros_2027.sql).', 1;


    DECLARE 
        @Anio INT = 2027,
        @Presupuesto NVARCHAR(20) = N'PPTO2027',
        @Origen NVARCHAR(100) = 'Postgrado';

    ------------------------------------------------------------
    -- 1️⃣ ELIMINAR REGISTROS PREVIOS DEL MISMO ORIGEN Y AÑO
    ------------------------------------------------------------
    PRINT 'Eliminando registros de PLANILLA para ' + @Origen + ' y ORIGEN_2=' + ISNULL(@OrigenEntrada,'(NULL)');
    
    DELETE FROM PLANILLA
    WHERE AÑO = @Anio
      AND ORIGEN = @Origen
      AND ORIGEN_2 = @OrigenEntrada;

    PRINT 'Registros eliminados: ' + CAST(@@ROWCOUNT AS VARCHAR(10));

    ------------------------------------------------------------
    -- 2️⃣ SELECCIÓN DE DATOS BASE
    ------------------------------------------------------------
    WITH Datos AS (
        SELECT
            de.CENTRO_COSTO,
            LTRIM(RTRIM(de.TIPO)) AS TIPO,
            TRY_CAST(de.MES AS INT) AS MES,  -- 🔹 Mes ya numérico
            ISNULL(de.IMPORTE, 0) AS IMPORTE,
            de.HOJA_ORIGEN,
            de.ORIGEN
        FROM DATOS_ENTRADA de
        WHERE LOWER(LTRIM(RTRIM(de.HOJA_ORIGEN))) = LOWER(@Origen)
          AND de.ORIGEN = @OrigenEntrada
          AND de.PRESUPUESTO = @Presupuesto
          AND ISNULL(de.IMPORTE, 0) > 0
          AND TRY_CAST(de.MES AS INT) BETWEEN 1 AND 12
    )

    ------------------------------------------------------------
    -- 3️⃣ SUELDO BRUTO
    ------------------------------------------------------------
    INSERT INTO PLANILLA (CENTRO_COSTO, PARTIDA, MES, IMPORTE, ORIGEN, ORIGEN_2, AÑO)
    SELECT 
        d.CENTRO_COSTO,
        CASE 
            WHEN LOWER(d.TIPO) LIKE '%tiempo completo%' THEN '94.1.1.1.002'
            WHEN LOWER(d.TIPO) LIKE '%tiempo parcial%'  THEN '94.1.1.1.033'
        END AS PARTIDA,
        d.MES,
        ROUND(d.IMPORTE, 2),
        @Origen AS ORIGEN,
        @OrigenEntrada AS ORIGEN_2,
        @Anio
    FROM Datos d
    WHERE d.MES IS NOT NULL
      AND (
            LOWER(d.TIPO) LIKE '%tiempo completo%' 
         OR LOWER(d.TIPO) LIKE '%tiempo parcial%'
      );

    ------------------------------------------------------------
    -- 4️⃣ CARGAS SOCIALES TIEMPO COMPLETO
    ------------------------------------------------------------
    -- Gratificación
    INSERT INTO PLANILLA (CENTRO_COSTO, PARTIDA, MES, IMPORTE, ORIGEN, ORIGEN_2, AÑO)
    SELECT p.CENTRO_COSTO,'94.1.1.1.006',p.MES,ROUND(p.IMPORTE*@TasaGrat,2),p.ORIGEN,p.ORIGEN_2,p.AÑO
    FROM PLANILLA p 
    WHERE p.ORIGEN=@Origen AND p.ORIGEN_2=@OrigenEntrada AND p.AÑO=@Anio AND p.PARTIDA='94.1.1.1.002';

    -- Essalud
    INSERT INTO PLANILLA (CENTRO_COSTO, PARTIDA, MES, IMPORTE, ORIGEN, ORIGEN_2, AÑO)
    SELECT p.CENTRO_COSTO,'94.1.1.1.011',p.MES,ROUND(p.IMPORTE*@TasaEssalud,2),p.ORIGEN,p.ORIGEN_2,p.AÑO
    FROM PLANILLA p 
    WHERE p.ORIGEN=@Origen AND p.ORIGEN_2=@OrigenEntrada AND p.AÑO=@Anio AND p.PARTIDA='94.1.1.1.002';

    -- CTS
    INSERT INTO PLANILLA (CENTRO_COSTO, PARTIDA, MES, IMPORTE, ORIGEN, ORIGEN_2, AÑO)
    SELECT p.CENTRO_COSTO,'94.1.1.1.024',p.MES,ROUND(p.IMPORTE*@TasaCTS,2),p.ORIGEN,p.ORIGEN_2,p.AÑO
    FROM PLANILLA p 
    WHERE p.ORIGEN=@Origen AND p.ORIGEN_2=@OrigenEntrada AND p.AÑO=@Anio AND p.PARTIDA='94.1.1.1.002';

    -- Vacaciones
    INSERT INTO PLANILLA (CENTRO_COSTO, PARTIDA, MES, IMPORTE, ORIGEN, ORIGEN_2, AÑO)
    SELECT p.CENTRO_COSTO,'94.1.1.1.009',p.MES,ROUND(p.IMPORTE*@TasaVac,2),p.ORIGEN,p.ORIGEN_2,p.AÑO
    FROM PLANILLA p 
    WHERE p.ORIGEN=@Origen AND p.ORIGEN_2=@OrigenEntrada AND p.AÑO=@Anio AND p.PARTIDA='94.1.1.1.002';

    -- Vida Ley
    INSERT INTO PLANILLA (CENTRO_COSTO, PARTIDA, MES, IMPORTE, ORIGEN, ORIGEN_2, AÑO)
    SELECT p.CENTRO_COSTO,'94.1.1.1.015',p.MES,ROUND(p.IMPORTE*@TasaVidaLey,2),p.ORIGEN,p.ORIGEN_2,p.AÑO
    FROM PLANILLA p 
    WHERE p.ORIGEN=@Origen AND p.ORIGEN_2=@OrigenEntrada AND p.AÑO=@Anio AND p.PARTIDA='94.1.1.1.002';

    ------------------------------------------------------------
    -- 5️⃣ CARGAS SOCIALES TIEMPO PARCIAL
    ------------------------------------------------------------
    -- Gratificación parcial
    INSERT INTO PLANILLA (CENTRO_COSTO, PARTIDA, MES, IMPORTE, ORIGEN, ORIGEN_2, AÑO)
    SELECT p.CENTRO_COSTO,'94.1.1.1.036',p.MES,ROUND(p.IMPORTE*@TasaGrat,2),p.ORIGEN,p.ORIGEN_2,p.AÑO
    FROM PLANILLA p 
    WHERE p.ORIGEN=@Origen AND p.ORIGEN_2=@OrigenEntrada AND p.AÑO=@Anio AND p.PARTIDA='94.1.1.1.033';

    -- Essalud parcial
    INSERT INTO PLANILLA (CENTRO_COSTO, PARTIDA, MES, IMPORTE, ORIGEN, ORIGEN_2, AÑO)
    SELECT p.CENTRO_COSTO,'94.1.1.1.035',p.MES,ROUND(p.IMPORTE*@TasaEssalud,2),p.ORIGEN,p.ORIGEN_2,p.AÑO
    FROM PLANILLA p 
    WHERE p.ORIGEN=@Origen AND p.ORIGEN_2=@OrigenEntrada AND p.AÑO=@Anio AND p.PARTIDA='94.1.1.1.033';

    ------------------------------------------------------------
    -- 6️⃣ RESUMEN FINAL
    ------------------------------------------------------------
    PRINT '==============================================';
    PRINT 'VALORIZACIÓN POSTGRADO ' + CAST(@Anio AS NVARCHAR(10));
    PRINT 'DATOS_ENTRADA.ORIGEN: ' + ISNULL(@OrigenEntrada,'(NULL)');
    PRINT '==============================================';

    SELECT 
        PARTIDA, 
        COUNT(*) AS Registros, 
        SUM(IMPORTE) AS Total
    FROM PLANILLA
    WHERE ORIGEN=@Origen AND ORIGEN_2=@OrigenEntrada AND AÑO=@Anio
    GROUP BY PARTIDA;

END;
GO

CREATE OR ALTER PROCEDURE [dbo].[sp_Valorizar_Investigacion_2027]
    @OrigenEntrada NVARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;

    -- Tasas desde PARAMETROS_2027 (sql/crear_parametros_2027.sql); antes fijas
    DECLARE @TasaGrat DECIMAL(9,6), @TasaEssalud DECIMAL(9,6), @TasaCTS DECIMAL(9,6),
            @TasaVac DECIMAL(9,6), @TasaVidaLey DECIMAL(9,6), @TasaAsigFam DECIMAL(9,6),
            @FactorGrados DECIMAL(9,6);
    SELECT @TasaGrat     = MAX(CASE WHEN CODIGO = 'GRATIFICACION' THEN VALOR END),
           @TasaEssalud  = MAX(CASE WHEN CODIGO = 'ESSALUD'       THEN VALOR END),
           @TasaCTS      = MAX(CASE WHEN CODIGO = 'CTS'           THEN VALOR END),
           @TasaVac      = MAX(CASE WHEN CODIGO = 'VACACIONES'    THEN VALOR END),
           @TasaVidaLey  = MAX(CASE WHEN CODIGO = 'VIDA_LEY'      THEN VALOR END),
           @TasaAsigFam  = MAX(CASE WHEN CODIGO = 'ASIG_FAMILIAR' THEN VALOR END),
           @FactorGrados = MAX(CASE WHEN CODIGO = 'FACTOR_GRADOS' THEN VALOR END)
    FROM dbo.PARAMETROS_2027;
    IF @TasaGrat IS NULL OR @TasaEssalud IS NULL OR @TasaCTS IS NULL OR @TasaVac IS NULL
       OR @TasaVidaLey IS NULL OR @TasaAsigFam IS NULL OR @FactorGrados IS NULL
        THROW 50011, 'Faltan parámetros en PARAMETROS_2027 (sql/crear_parametros_2027.sql).', 1;


    DECLARE @Anio INT = 2027;
    DECLARE @Presupuesto NVARCHAR(20) = N'PPTO2027';
    DECLARE @Origen NVARCHAR(100) = 'Investigacion';

    ------------------------------------------------------------
    -- 1️⃣ ELIMINAR REGISTROS PREVIOS DEL MISMO ORIGEN Y AÑO
    ------------------------------------------------------------
    DELETE FROM PLANILLA
    WHERE AÑO = @Anio
      AND ORIGEN = @Origen
      AND ORIGEN_2 = @OrigenEntrada;

    ------------------------------------------------------------
    -- 2️⃣ CONVERSIÓN DE MES Y SELECCIÓN DE DATOS
    ------------------------------------------------------------
    WITH Datos AS (
        SELECT
            de.CENTRO_COSTO,
            UPPER(LTRIM(RTRIM(de.CONCEPTO))) AS CONCEPTO,
            CASE 
                WHEN ISNUMERIC(de.MES) = 1 THEN CAST(de.MES AS INT)
                WHEN LOWER(LTRIM(RTRIM(de.MES))) IN ('enero') THEN 1
                WHEN LOWER(LTRIM(RTRIM(de.MES))) IN ('febrero') THEN 2
                WHEN LOWER(LTRIM(RTRIM(de.MES))) IN ('marzo') THEN 3
                WHEN LOWER(LTRIM(RTRIM(de.MES))) IN ('abril') THEN 4
                WHEN LOWER(LTRIM(RTRIM(de.MES))) IN ('mayo') THEN 5
                WHEN LOWER(LTRIM(RTRIM(de.MES))) IN ('junio') THEN 6
                WHEN LOWER(LTRIM(RTRIM(de.MES))) IN ('julio') THEN 7
                WHEN LOWER(LTRIM(RTRIM(de.MES))) IN ('agosto') THEN 8
                WHEN LOWER(LTRIM(RTRIM(de.MES))) IN ('setiembre','septiembre') THEN 9
                WHEN LOWER(LTRIM(RTRIM(de.MES))) IN ('octubre') THEN 10
                WHEN LOWER(LTRIM(RTRIM(de.MES))) IN ('noviembre') THEN 11
                WHEN LOWER(LTRIM(RTRIM(de.MES))) IN ('diciembre') THEN 12
                ELSE NULL
            END AS MES,
            ISNULL(de.IMPORTE,0) AS IMPORTE,
            de.HOJA_ORIGEN,
            de.ORIGEN
        FROM DATOS_ENTRADA de
        WHERE UPPER(LTRIM(RTRIM(de.HOJA_ORIGEN))) = 'INVESTIGACION'
          AND de.ORIGEN = @OrigenEntrada
          AND de.PRESUPUESTO = @Presupuesto
          AND ISNULL(de.IMPORTE,0) > 0
    )

    ------------------------------------------------------------
    -- 3️⃣ SUELDO BRUTO
    ------------------------------------------------------------
    INSERT INTO PLANILLA (CENTRO_COSTO, PARTIDA, MES, IMPORTE, ORIGEN, ORIGEN_2, AÑO)
    SELECT 
        d.CENTRO_COSTO,
        CASE 
            WHEN d.CONCEPTO LIKE '%ADMINISTRATIVO TIEMPO COMPLETO%' THEN '94.1.1.1.002'
            WHEN d.CONCEPTO LIKE '%DOCENTE TIEMPO COMPLETO%' THEN '94.1.1.1.002'
            WHEN d.CONCEPTO LIKE '%ADMINISTRATIVO TIEMPO PARCIAL%' THEN '94.1.1.1.033'
            WHEN d.CONCEPTO LIKE '%DOCENTE TIEMPO PARCIAL%' THEN '94.1.1.1.033'
        END AS PARTIDA,
        d.MES,
        ROUND(d.IMPORTE, 2),
        @Origen AS ORIGEN,
        d.ORIGEN AS ORIGEN_2,
        @Anio
    FROM Datos d
    WHERE d.MES IS NOT NULL;

    ------------------------------------------------------------
    -- 4️⃣ CARGAS SOCIALES: TIEMPO COMPLETO
    ------------------------------------------------------------
    INSERT INTO PLANILLA (CENTRO_COSTO, PARTIDA, MES, IMPORTE, ORIGEN, ORIGEN_2, AÑO)
    SELECT p.CENTRO_COSTO, '94.1.1.1.006', p.MES, ROUND(p.IMPORTE * @TasaGrat, 2), p.ORIGEN, p.ORIGEN_2, p.AÑO
    FROM PLANILLA p
    WHERE p.AÑO = @Anio AND p.ORIGEN = @Origen AND p.ORIGEN_2 = @OrigenEntrada
      AND p.PARTIDA = '94.1.1.1.002';

    INSERT INTO PLANILLA (CENTRO_COSTO, PARTIDA, MES, IMPORTE, ORIGEN, ORIGEN_2, AÑO)
    SELECT p.CENTRO_COSTO, '94.1.1.1.011', p.MES, ROUND(p.IMPORTE * @TasaEssalud, 2), p.ORIGEN, p.ORIGEN_2, p.AÑO
    FROM PLANILLA p
    WHERE p.AÑO = @Anio AND p.ORIGEN = @Origen AND p.ORIGEN_2 = @OrigenEntrada
      AND p.PARTIDA = '94.1.1.1.002';

    INSERT INTO PLANILLA (CENTRO_COSTO, PARTIDA, MES, IMPORTE, ORIGEN, ORIGEN_2, AÑO)
    SELECT p.CENTRO_COSTO, '94.1.1.1.024', p.MES, ROUND(p.IMPORTE * @TasaCTS, 2), p.ORIGEN, p.ORIGEN_2, p.AÑO
    FROM PLANILLA p
    WHERE p.AÑO = @Anio AND p.ORIGEN = @Origen AND p.ORIGEN_2 = @OrigenEntrada
      AND p.PARTIDA = '94.1.1.1.002';

    INSERT INTO PLANILLA (CENTRO_COSTO, PARTIDA, MES, IMPORTE, ORIGEN, ORIGEN_2, AÑO)
    SELECT p.CENTRO_COSTO, '94.1.1.1.009', p.MES, ROUND(p.IMPORTE * @TasaVac, 2), p.ORIGEN, p.ORIGEN_2, p.AÑO
    FROM PLANILLA p
    WHERE p.AÑO = @Anio AND p.ORIGEN = @Origen AND p.ORIGEN_2 = @OrigenEntrada
      AND p.PARTIDA = '94.1.1.1.002';

    ------------------------------------------------------------
    -- 5️⃣ CARGAS SOCIALES: TIEMPO PARCIAL
    ------------------------------------------------------------
    INSERT INTO PLANILLA (CENTRO_COSTO, PARTIDA, MES, IMPORTE, ORIGEN, ORIGEN_2, AÑO)
    SELECT p.CENTRO_COSTO, '94.1.1.1.036', p.MES, ROUND(p.IMPORTE * @TasaGrat, 2), p.ORIGEN, p.ORIGEN_2, p.AÑO
    FROM PLANILLA p
    WHERE p.AÑO = @Anio AND p.ORIGEN = @Origen AND p.ORIGEN_2 = @OrigenEntrada
      AND p.PARTIDA = '94.1.1.1.033';

    INSERT INTO PLANILLA (CENTRO_COSTO, PARTIDA, MES, IMPORTE, ORIGEN, ORIGEN_2, AÑO)
    SELECT p.CENTRO_COSTO, '94.1.1.1.035', p.MES, ROUND(p.IMPORTE * @TasaEssalud, 2), p.ORIGEN, p.ORIGEN_2, p.AÑO
    FROM PLANILLA p
    WHERE p.AÑO = @Anio AND p.ORIGEN = @Origen AND p.ORIGEN_2 = @OrigenEntrada
      AND p.PARTIDA = '94.1.1.1.033';

    ------------------------------------------------------------
    -- 6️⃣ RESUMEN FINAL
    ------------------------------------------------------------
    PRINT '==============================================';
    PRINT 'VALORIZACIÓN INVESTIGACIÓN - AÑO ' + CAST(@Anio AS NVARCHAR(4));
    PRINT 'OrigenEntrada: ' + @OrigenEntrada;
    PRINT '==============================================';

    SELECT 
        PARTIDA,
        COUNT(*) AS Registros,
        SUM(IMPORTE) AS Total
    FROM PLANILLA
    WHERE AÑO = @Anio
      AND ORIGEN = @Origen
      AND ORIGEN_2 = @OrigenEntrada
    GROUP BY PARTIDA
    ORDER BY PARTIDA;

    ------------------------------------------------------------
    -- 🔥 LÍNEAS NUEVAS AL FINAL DEL PROCEDIMIENTO
    ------------------------------------------------------------
    DELETE FROM PLANILLA
    WHERE AÑO = @Anio
      AND CENTRO_COSTO IN (
            '03.01.04.04.07',
            '03.01.05.04.13',
            '03.01.06.04.17',
            '03.01.07.04.06',
            '03.01.08.04.08',
            '03.01.13.04.15',
            '03.01.09.04.02',
            '03.01.11.04.08',
            '03.01.02.04.03'
      )
      AND PARTIDA IN ('94.1.1.1.002','94.1.1.1.033');

END;
GO

CREATE OR ALTER PROCEDURE [dbo].[sp_Valorizar_Ayudantias_2027]
    @OrigenEntrada NVARCHAR(100)  -- 🔹 Parámetro que viene desde DATOS_ENTRADA.ORIGEN
AS
BEGIN
    SET NOCOUNT ON;

    ------------------------------------------------------------
    -- Declaraciones iniciales
    ------------------------------------------------------------
    DECLARE @Anio INT = 2027;
    DECLARE @Presupuesto NVARCHAR(20) = N'PPTO2027';
    DECLARE @Origen NVARCHAR(100) = 'Ayudantias';

    ------------------------------------------------------------
    -- 1️⃣ ELIMINAR REGISTROS PREVIOS DEL MISMO ORIGEN Y AÑO
    ------------------------------------------------------------
    DELETE FROM PLANILLA
    WHERE AÑO = @Anio
      AND ORIGEN = @Origen
      AND ORIGEN_2 = @OrigenEntrada;

    ------------------------------------------------------------
    -- 2️⃣ INSERTAR NUEVOS REGISTROS DESDE DATOS_ENTRADA
    ------------------------------------------------------------
    INSERT INTO PLANILLA (CENTRO_COSTO, PARTIDA, MES, IMPORTE, ORIGEN, ORIGEN_2, AÑO)
    SELECT 
        LTRIM(RTRIM(de.CENTRO_COSTO)) AS CENTRO_COSTO,
        '74.1.1.1.001' AS PARTIDA,  -- Partida fija para Ayudantías
        TRY_CAST(de.MES AS INT) AS MES,
        -- Horas (en IMPORTE) x tarifa: la de la fila o, si no viene, la de tarifas_2027
        ROUND(ISNULL(de.IMPORTE, 0) * COALESCE(NULLIF(de.TARIFA, 0),
            (SELECT MAX(t.TARIFA) FROM tarifas_2027 t WHERE t.HOJA_ORIGEN = @Origen), 0), 2) AS IMPORTE,
        @Origen AS ORIGEN,
        de.ORIGEN AS ORIGEN_2,
        @Anio AS AÑO
    FROM DATOS_ENTRADA de
    WHERE LOWER(LTRIM(RTRIM(de.HOJA_ORIGEN))) = 'ayudantias'
      AND de.ORIGEN = @OrigenEntrada
      AND de.PRESUPUESTO = @Presupuesto
      AND ISNULL(de.IMPORTE, 0) > 0
      AND TRY_CAST(de.MES AS INT) BETWEEN 1 AND 12;

    ------------------------------------------------------------
    -- 3️⃣ RESUMEN FINAL
    ------------------------------------------------------------
    PRINT '==============================================';
    PRINT 'VALORIZACIÓN AYUDANTÍAS ' + CAST(@Anio AS NVARCHAR(4));
    PRINT 'OrigenEntrada: ' + @OrigenEntrada;
    PRINT '==============================================';

    SELECT 
        PARTIDA,
        COUNT(*) AS Registros,
        SUM(IMPORTE) AS Total
    FROM PLANILLA
    WHERE AÑO = @Anio
      AND ORIGEN = @Origen
      AND ORIGEN_2 = @OrigenEntrada
    GROUP BY PARTIDA
    ORDER BY PARTIDA;

END;
GO

CREATE OR ALTER PROCEDURE [dbo].[sp_ValorizarPlanilla_Total_2027]
    @OrigenEntrada NVARCHAR(100)  -- 🔹 Filtro de DATOS_ENTRADA.ORIGEN
AS
BEGIN
    SET NOCOUNT ON;

    -- Tasas desde PARAMETROS_2027 (sql/crear_parametros_2027.sql); antes fijas
    DECLARE @TasaGrat DECIMAL(9,6), @TasaEssalud DECIMAL(9,6), @TasaCTS DECIMAL(9,6),
            @TasaVac DECIMAL(9,6), @TasaVidaLey DECIMAL(9,6), @TasaAsigFam DECIMAL(9,6),
            @FactorGrados DECIMAL(9,6);
    SELECT @TasaGrat     = MAX(CASE WHEN CODIGO = 'GRATIFICACION' THEN VALOR END),
           @TasaEssalud  = MAX(CASE WHEN CODIGO = 'ESSALUD'       THEN VALOR END),
           @TasaCTS      = MAX(CASE WHEN CODIGO = 'CTS'           THEN VALOR END),
           @TasaVac      = MAX(CASE WHEN CODIGO = 'VACACIONES'    THEN VALOR END),
           @TasaVidaLey  = MAX(CASE WHEN CODIGO = 'VIDA_LEY'      THEN VALOR END),
           @TasaAsigFam  = MAX(CASE WHEN CODIGO = 'ASIG_FAMILIAR' THEN VALOR END),
           @FactorGrados = MAX(CASE WHEN CODIGO = 'FACTOR_GRADOS' THEN VALOR END)
    FROM dbo.PARAMETROS_2027;
    IF @TasaGrat IS NULL OR @TasaEssalud IS NULL OR @TasaCTS IS NULL OR @TasaVac IS NULL
       OR @TasaVidaLey IS NULL OR @TasaAsigFam IS NULL OR @FactorGrados IS NULL
        THROW 50011, 'Faltan parámetros en PARAMETROS_2027 (sql/crear_parametros_2027.sql).', 1;


    ------------------------------------------------------------
    -- VARIABLES
    ------------------------------------------------------------
    DECLARE @Origen NVARCHAR(100);
    DECLARE @Anio INT = 2027;
    DECLARE @Presupuesto NVARCHAR(20) = N'PPTO2027';

    CREATE TABLE #Resumen (
        ORIGEN NVARCHAR(100),
        RegistrosRem INT,
        RegistrosCTS INT,
        RegistrosVac INT,
        RegistrosGrat INT,
        RegistrosEssalud INT,
        RegistrosVidaLey INT,
        RegistrosReplica INT
    );

    ------------------------------------------------------------
    -- CURSOR SOBRE LOS ORÍGENES
    ------------------------------------------------------------
    DECLARE c CURSOR FOR
        SELECT 'Plan TC Transversales'
        UNION ALL
        SELECT '1. Plan TC-I'
        UNION ALL
        SELECT 'Plan TC-II';

    OPEN c;
    FETCH NEXT FROM c INTO @Origen;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        DECLARE 
            @RegRem INT = 0, @RegCTS INT = 0, @RegVac INT = 0,
            @RegGrat INT = 0, @RegEss INT = 0, @RegVida INT = 0, @RegRep INT = 0;

        PRINT '================================================';
        PRINT 'Procesando ORIGEN: ' + @Origen + ' con ORIGEN_2 = ' + @OrigenEntrada;

        --------------------------------------------------------
        -- 1️⃣ ELIMINAR DATOS PREVIOS
        --------------------------------------------------------
        DELETE FROM PLANILLA 
        WHERE AÑO = @Anio 
          AND ORIGEN = @Origen
          AND ORIGEN_2 = @OrigenEntrada;

        --------------------------------------------------------
        -- 2️⃣ CÁLCULO DE HORAS Y REMUNERACIONES
        --------------------------------------------------------
        ;WITH HorasPorProfesor AS (
            SELECT 
                LTRIM(RTRIM(DNI)) AS DNI, 
                MES, 
                SUM(ISNULL(HORAS,0)) AS TotalHoras
            FROM DATOS_ENTRADA
            WHERE HOJA_ORIGEN = @Origen
              AND ORIGEN = @OrigenEntrada
              AND PRESUPUESTO = @Presupuesto
              -- **Filtro para excluir concepto específico**
              AND CONCEPTO <> 'Horas Dictado Pregrado (académicas)'
            GROUP BY LTRIM(RTRIM(DNI)), MES
        ),
        RemuneracionTotal AS (
            SELECT 
                LTRIM(RTRIM(DNI)) AS DNI,
                ISNULL(
                    (ISNULL(Basico,0)+ISNULL(Asignacion_Familiar,0)+ISNULL(Bonificacion_Docente_TC,0)+
                     ISNULL(Bonificacion_Dedicacion_Exclusiva,0)+ISNULL(Bono_por_Decano,0)+ISNULL(Bono_por_Director_de_Escuela,0)+
                     ISNULL(Bono_por_Departamento,0)+ISNULL(Bono_al_Cargo,0)+ISNULL(Bonificacion_Variable_por_Profesor_Extranjero,0)+
                     ISNULL(Bonificacion_Ordinaria_por_Acuerdo_Rem,0)+ISNULL(Bonificacion_por_Representacion,0)+
                     ISNULL(Grado_de_Maestria,0)+ISNULL(Grado_de_Doctorado,0)+
                     ISNULL(Asignacion_por_Vivienda,0)+ISNULL(Asignacion_por_Hijo_Menor,0)+
                     ISNULL(Vale_por_Alimentos,0)),0) AS TotalRemuneracion
            FROM dbo.Remuneraciones_2027  -- copia 2027 (sql/crear_rol_desarrollo_humano.sql)
        )
        INSERT INTO PLANILLA (CENTRO_COSTO, PARTIDA, MES, IMPORTE, ORIGEN, ORIGEN_2, AÑO)
        SELECT 
            de.CENTRO_COSTO,
            '94.1.1.1.002',
            de.MES,
            ROUND((de.HORAS / NULLIF(h.TotalHoras,0)) * r.TotalRemuneracion,2),
            de.HOJA_ORIGEN,
            de.ORIGEN,
            @Anio
        FROM DATOS_ENTRADA de
        INNER JOIN HorasPorProfesor h 
            ON LTRIM(RTRIM(de.DNI))=h.DNI 
               AND de.MES=h.MES
        INNER JOIN RemuneracionTotal r 
            ON LTRIM(RTRIM(de.DNI))=r.DNI
        WHERE de.HOJA_ORIGEN = @Origen 
          AND ISNULL(de.HORAS,0) > 0
          AND de.ORIGEN = @OrigenEntrada
          AND de.PRESUPUESTO = @Presupuesto
          -- **Filtro para excluir el mismo concepto en el detalle**
          AND de.CONCEPTO <> 'Horas Dictado Pregrado (académicas)';

        SET @RegRem = @@ROWCOUNT;

        --------------------------------------------------------
        -- 3️⃣ CARGAS SOCIALES
        --------------------------------------------------------
        INSERT INTO PLANILLA (CENTRO_COSTO,PARTIDA,MES,IMPORTE,ORIGEN,ORIGEN_2,AÑO)
        SELECT p.CENTRO_COSTO,'94.1.1.1.024',p.MES,ROUND(p.IMPORTE*@TasaCTS,2),p.ORIGEN,p.ORIGEN_2,p.AÑO
        FROM PLANILLA p 
        WHERE p.AÑO=@Anio 
          AND p.PARTIDA='94.1.1.1.002' 
          AND p.ORIGEN=@Origen 
          AND p.ORIGEN_2=@OrigenEntrada;
        SET @RegCTS=@@ROWCOUNT;

        INSERT INTO PLANILLA (CENTRO_COSTO,PARTIDA,MES,IMPORTE,ORIGEN,ORIGEN_2,AÑO)
        SELECT p.CENTRO_COSTO,'94.1.1.1.009',p.MES,ROUND(p.IMPORTE*@TasaVac,2),p.ORIGEN,p.ORIGEN_2,p.AÑO
        FROM PLANILLA p 
        WHERE p.AÑO=@Anio 
          AND p.PARTIDA='94.1.1.1.002' 
          AND p.ORIGEN=@Origen 
          AND p.ORIGEN_2=@OrigenEntrada;
        SET @RegVac=@@ROWCOUNT;

        INSERT INTO PLANILLA (CENTRO_COSTO,PARTIDA,MES,IMPORTE,ORIGEN,ORIGEN_2,AÑO)
        SELECT p.CENTRO_COSTO,'94.1.1.1.006',p.MES,ROUND(p.IMPORTE*@TasaGrat,2),p.ORIGEN,p.ORIGEN_2,p.AÑO
        FROM PLANILLA p 
        WHERE p.AÑO=@Anio 
          AND p.PARTIDA='94.1.1.1.002' 
          AND p.ORIGEN=@Origen 
          AND p.ORIGEN_2=@OrigenEntrada;
        SET @RegGrat=@@ROWCOUNT;

        INSERT INTO PLANILLA (CENTRO_COSTO,PARTIDA,MES,IMPORTE,ORIGEN,ORIGEN_2,AÑO)
        SELECT p.CENTRO_COSTO,'94.1.1.1.011',p.MES,ROUND(p.IMPORTE*@TasaEssalud,2),p.ORIGEN,p.ORIGEN_2,p.AÑO
        FROM PLANILLA p 
        WHERE p.AÑO=@Anio 
          AND p.PARTIDA='94.1.1.1.002' 
          AND p.ORIGEN=@Origen 
          AND p.ORIGEN_2=@OrigenEntrada;
        SET @RegEss=@@ROWCOUNT;

        INSERT INTO PLANILLA (CENTRO_COSTO,PARTIDA,MES,IMPORTE,ORIGEN,ORIGEN_2,AÑO)
        SELECT p.CENTRO_COSTO,'94.1.1.1.015',p.MES,ROUND(p.IMPORTE*@TasaVidaLey,2),p.ORIGEN,p.ORIGEN_2,p.AÑO
        FROM PLANILLA p 
        WHERE p.AÑO=@Anio 
          AND p.PARTIDA='94.1.1.1.002' 
          AND p.ORIGEN=@Origen 
          AND p.ORIGEN_2=@OrigenEntrada;
        SET @RegVida=@@ROWCOUNT;

        --------------------------------------------------------
        -- 4️⃣ REPLICACIÓN DE MESES SEGÚN ORIGEN
        --------------------------------------------------------
        IF @Origen = 'Plan TC Transversales'
        BEGIN
            INSERT INTO PLANILLA (CENTRO_COSTO,PARTIDA,MES,IMPORTE,ORIGEN,ORIGEN_2,AÑO)
            SELECT p.CENTRO_COSTO,p.PARTIDA,v.MES,p.IMPORTE,p.ORIGEN,p.ORIGEN_2,p.AÑO
            FROM PLANILLA p
            CROSS APPLY (
                SELECT MES FROM (VALUES(1),(2),(4),(5),(6),(7),(9),(10),(11),(12)) AS x(MES)
                WHERE (p.MES=3 AND x.MES IN(1,2,4,5,6,7))
                   OR (p.MES=8 AND x.MES IN(9,10,11,12))
            ) v
            WHERE p.AÑO=@Anio 
              AND p.ORIGEN=@Origen 
              AND p.ORIGEN_2=@OrigenEntrada;
        END
        ELSE IF @Origen = '1. Plan TC-I'
        BEGIN
            INSERT INTO PLANILLA (CENTRO_COSTO,PARTIDA,MES,IMPORTE,ORIGEN,ORIGEN_2,AÑO)
            SELECT p.CENTRO_COSTO,p.PARTIDA,v.MES,p.IMPORTE,p.ORIGEN,p.ORIGEN_2,p.AÑO
            FROM PLANILLA p
            CROSS APPLY (
                SELECT MES FROM (VALUES(1),(2),(4),(5),(6),(7)) AS x(MES)
                WHERE p.MES=3
            ) v
            WHERE p.AÑO=@Anio 
              AND p.ORIGEN=@Origen 
              AND p.ORIGEN_2=@OrigenEntrada;
        END
        ELSE IF @Origen = 'Plan TC-II'
        BEGIN
            INSERT INTO PLANILLA (CENTRO_COSTO,PARTIDA,MES,IMPORTE,p.ORIGEN,p.ORIGEN_2,p.AÑO)
            SELECT p.CENTRO_COSTO,p.PARTIDA,v.MES,p.IMPORTE,p.ORIGEN,p.ORIGEN_2,p.AÑO
            FROM PLANILLA p
            CROSS APPLY (
                SELECT MES FROM (VALUES(9),(10),(11),(12)) AS x(MES)
                WHERE p.MES=8
            ) v
            WHERE p.AÑO=@Anio 
              AND p.ORIGEN=@Origen 
              AND p.ORIGEN_2=@OrigenEntrada;
        END

        SET @RegRep = @@ROWCOUNT;

        --------------------------------------------------------
        -- 5️⃣ REGISTRAR RESULTADOS
        --------------------------------------------------------
        INSERT INTO #Resumen 
        VALUES (@Origen,@RegRem,@RegCTS,@RegVac,@RegGrat,@RegEss,@RegVida,@RegRep);

        FETCH NEXT FROM c INTO @Origen;
    END

    CLOSE c; DEALLOCATE c;

    ------------------------------------------------------------
    -- 6️⃣ MOSTRAR RESUMEN
    ------------------------------------------------------------
    SELECT 
        ORIGEN,
        RegistrosRem AS Remuneraciones,
        RegistrosCTS AS CTS,
        RegistrosVac AS Vacaciones,
        RegistrosGrat AS Gratificacion,
        RegistrosEssalud AS Essalud,
        RegistrosVidaLey AS VidaLey,
        RegistrosReplica AS MesesReplicados,
        RegistrosRem + RegistrosCTS + RegistrosVac + RegistrosGrat + 
        RegistrosEssalud + RegistrosVidaLey + RegistrosReplica AS TotalRegistros
    FROM #Resumen;

END;
GO

CREATE OR ALTER PROCEDURE [dbo].[sp_Valorizar_CargaAcademica_2027]
AS
BEGIN
    SET NOCOUNT ON;

    -- Tasas desde PARAMETROS_2027 (sql/crear_parametros_2027.sql); antes fijas
    DECLARE @TasaGrat DECIMAL(9,6), @TasaEssalud DECIMAL(9,6), @TasaCTS DECIMAL(9,6),
            @TasaVac DECIMAL(9,6), @TasaVidaLey DECIMAL(9,6), @TasaAsigFam DECIMAL(9,6),
            @FactorGrados DECIMAL(9,6);
    SELECT @TasaGrat     = MAX(CASE WHEN CODIGO = 'GRATIFICACION' THEN VALOR END),
           @TasaEssalud  = MAX(CASE WHEN CODIGO = 'ESSALUD'       THEN VALOR END),
           @TasaCTS      = MAX(CASE WHEN CODIGO = 'CTS'           THEN VALOR END),
           @TasaVac      = MAX(CASE WHEN CODIGO = 'VACACIONES'    THEN VALOR END),
           @TasaVidaLey  = MAX(CASE WHEN CODIGO = 'VIDA_LEY'      THEN VALOR END),
           @TasaAsigFam  = MAX(CASE WHEN CODIGO = 'ASIG_FAMILIAR' THEN VALOR END),
           @FactorGrados = MAX(CASE WHEN CODIGO = 'FACTOR_GRADOS' THEN VALOR END)
    FROM dbo.PARAMETROS_2027;
    IF @TasaGrat IS NULL OR @TasaEssalud IS NULL OR @TasaCTS IS NULL OR @TasaVac IS NULL
       OR @TasaVidaLey IS NULL OR @TasaAsigFam IS NULL OR @FactorGrados IS NULL
        THROW 50011, 'Faltan parámetros en PARAMETROS_2027 (sql/crear_parametros_2027.sql).', 1;


    DECLARE @Presupuesto NVARCHAR(20) = N'PPTO2027';
    -- Tarifas por hora desde tarifas_2027 (antes fijas: 152 / 100 / 105)
    DECLARE @TarifaTitular   DECIMAL(18,4) = (SELECT MAX(TARIFA) FROM tarifas_2027 WHERE HOJA_ORIGEN = 'Horas Adicionales' AND TIPO = 'Titular');
    DECLARE @TarifaAsistente DECIMAL(18,4) = (SELECT MAX(TARIFA) FROM tarifas_2027 WHERE HOJA_ORIGEN = 'Horas Adicionales' AND TIPO = 'Asistente');
    DECLARE @TarifaJP        DECIMAL(18,4) = (SELECT MAX(TARIFA) FROM tarifas_2027 WHERE HOJA_ORIGEN = 'Horas Adicionales' AND TIPO = 'Jefe de practica');
    IF @TarifaTitular IS NULL OR @TarifaAsistente IS NULL OR @TarifaJP IS NULL
        THROW 50010, 'Faltan tarifas Titular / Asistente / Jefe de practica en tarifas_2027.', 1;

    ------------------------------------------------------------
    -- 1️⃣ ELIMINAR REGISTROS PREVIOS
    ------------------------------------------------------------
    DELETE FROM PLANILLA
    WHERE AÑO = 2027
      AND ORIGEN = 'Carga Academica';


    ------------------------------------------------------------
    -- 2️⃣ HORAS DESCONTADAS (usa el campo HORAS de Plan TC)
    ------------------------------------------------------------
    ;WITH HorasDescontadas AS (
        SELECT 
            LTRIM(RTRIM(de.CENTRO_COSTO)) AS CENTRO_COSTO,
            CASE 
                WHEN TRY_CAST(de.MES AS INT) BETWEEN 1 AND 7 THEN '2027-1'
                WHEN TRY_CAST(de.MES AS INT) BETWEEN 8 AND 12 THEN '2027-2'
            END AS SEMESTRE,
            SUM(ISNULL(de.HORAS,0)) AS HORAS_TC
        FROM DATOS_ENTRADA de
        WHERE LTRIM(RTRIM(de.HOJA_ORIGEN)) IN ('Plan TC Transversales', '1. Plan TC-I', 'Plan TC-II')
          AND LTRIM(RTRIM(de.CONCEPTO)) = 'Horas Dictado Pregrado (académicas)'
          AND de.PRESUPUESTO = @Presupuesto
        GROUP BY 
            LTRIM(RTRIM(de.CENTRO_COSTO)),
            CASE 
                WHEN TRY_CAST(de.MES AS INT) BETWEEN 1 AND 7 THEN '2027-1'
                WHEN TRY_CAST(de.MES AS INT) BETWEEN 8 AND 12 THEN '2027-2'
            END
    ),

    ------------------------------------------------------------
    -- 3️⃣ BASE INICIAL CON DESCUENTO Y AJUSTES (MAESTRÍAS / DOCTORADOS)
    ------------------------------------------------------------
    BaseDescontada AS (
        SELECT 
            LTRIM(RTRIM(de.CENTRO_COSTO)) AS CENTRO_COSTO,
            LTRIM(RTRIM(de.CONCEPTO)) AS CONCEPTO,
            LTRIM(RTRIM(de.MES)) AS MES_CARGA,
            CASE 
                WHEN LTRIM(RTRIM(de.CONCEPTO)) = '# HORAS TITULARES' THEN 
                    (
                        CASE 
                            WHEN LTRIM(RTRIM(de.MES)) = '2027-1' THEN 
                                CASE WHEN ISNULL(de.IMPORTE,0)*@TarifaTitular - ISNULL(hd.HORAS_TC,0)*@TarifaTitular > 0 
                                     THEN ISNULL(de.IMPORTE,0)*@TarifaTitular - ISNULL(hd.HORAS_TC,0)*@TarifaTitular ELSE 0 END
                            WHEN LTRIM(RTRIM(de.MES)) = '2027-2' THEN 
                                CASE WHEN ISNULL(de.IMPORTE,0)*@TarifaTitular - ISNULL(hd.HORAS_TC,0)*@TarifaTitular > 0 
                                     THEN ISNULL(de.IMPORTE,0)*@TarifaTitular - ISNULL(hd.HORAS_TC,0)*@TarifaTitular ELSE 0 END
                            ELSE ISNULL(de.IMPORTE,0)*@TarifaTitular
                        END
                        * @FactorGrados  -- 🔹 8% Maestrías + 0.51% Doctorado
                    )
                WHEN LTRIM(RTRIM(de.CONCEPTO)) = '# HORAS ASITENTES' THEN ISNULL(de.IMPORTE,0)*@TarifaAsistente
                WHEN LTRIM(RTRIM(de.CONCEPTO)) = '# HORAS JEFES DE PRÁCTICA' THEN ISNULL(de.IMPORTE,0)*@TarifaJP
                ELSE 0
            END AS VALOR_AJUSTADO,
            de.ORIGEN,
            de.HOJA_ORIGEN,
            LTRIM(RTRIM(de.MES)) AS SEMESTRE
        FROM DATOS_ENTRADA de
        LEFT JOIN HorasDescontadas hd
               ON LTRIM(RTRIM(de.CENTRO_COSTO)) = hd.CENTRO_COSTO
              AND LTRIM(RTRIM(de.MES)) = hd.SEMESTRE
        WHERE LOWER(LTRIM(RTRIM(de.HOJA_ORIGEN))) = 'carga academica'
          AND de.PRESUPUESTO = @Presupuesto
    ),

    ------------------------------------------------------------
    -- 4️⃣ DUPLICACIÓN DE MESES (DESPUÉS DEL AJUSTE)
    ------------------------------------------------------------
    BaseExpandida AS (
        SELECT 
            bd.CENTRO_COSTO,
            bd.CONCEPTO,
            m.MES,
            bd.VALOR_AJUSTADO AS VALOR,
            bd.ORIGEN,
            bd.HOJA_ORIGEN,
            '2027-1' AS SEMESTRE
        FROM BaseDescontada bd
        CROSS APPLY (
            SELECT MES FROM (VALUES
                (CASE WHEN bd.CONCEPTO = '# HORAS ASITENTES' THEN 4 END),
                (CASE WHEN bd.CONCEPTO = '# HORAS ASITENTES' THEN 5 END),
                (CASE WHEN bd.CONCEPTO = '# HORAS ASITENTES' THEN 6 END),
                (CASE WHEN bd.CONCEPTO = '# HORAS ASITENTES' THEN 7 END),
                (CASE WHEN bd.CONCEPTO <> '# HORAS ASITENTES' THEN 3 END),
                (CASE WHEN bd.CONCEPTO <> '# HORAS ASITENTES' THEN 4 END),
                (CASE WHEN bd.CONCEPTO <> '# HORAS ASITENTES' THEN 5 END),
                (CASE WHEN bd.CONCEPTO <> '# HORAS ASITENTES' THEN 6 END),
                (CASE WHEN bd.CONCEPTO <> '# HORAS ASITENTES' THEN 7 END)
            ) AS t(MES)
            WHERE MES IS NOT NULL
        ) m
        WHERE bd.SEMESTRE = '2027-1'

        UNION ALL

        SELECT 
            bd.CENTRO_COSTO,
            bd.CONCEPTO,
            m.MES,
            bd.VALOR_AJUSTADO AS VALOR,
            bd.ORIGEN,
            bd.HOJA_ORIGEN,
            '2027-2' AS SEMESTRE
        FROM BaseDescontada bd
        CROSS APPLY (
            SELECT MES FROM (VALUES
                (CASE WHEN bd.CONCEPTO = '# HORAS ASITENTES' THEN 9 END),
                (CASE WHEN bd.CONCEPTO = '# HORAS ASITENTES' THEN 10 END),
                (CASE WHEN bd.CONCEPTO = '# HORAS ASITENTES' THEN 11 END),
                (CASE WHEN bd.CONCEPTO = '# HORAS ASITENTES' THEN 12 END),
                (CASE WHEN bd.CONCEPTO <> '# HORAS ASITENTES' THEN 8 END),
                (CASE WHEN bd.CONCEPTO <> '# HORAS ASITENTES' THEN 9 END),
                (CASE WHEN bd.CONCEPTO <> '# HORAS ASITENTES' THEN 10 END),
                (CASE WHEN bd.CONCEPTO <> '# HORAS ASITENTES' THEN 11 END),
                (CASE WHEN bd.CONCEPTO <> '# HORAS ASITENTES' THEN 12 END)
            ) AS t(MES)
            WHERE MES IS NOT NULL
        ) m
        WHERE bd.SEMESTRE = '2027-2'
    )

    ------------------------------------------------------------
    -- 5️⃣ INSERCIÓN PRINCIPAL (AHORA CON TODAS LAS COLUMNAS)
    ------------------------------------------------------------
    INSERT INTO PLANILLA 
    (CENTRO_COSTO, PARTIDA, DIMENSION, MES, IMPORTE, ORIGEN, DNI, CONCEPTO, HORAS, ORIGEN_2, COMENTARIO, AÑO)
    SELECT 
        be.CENTRO_COSTO,
        '94.1.1.1.033',
        NULL,
        be.MES,
        ROUND(be.VALOR, 2),
        'Carga Academica',
        NULL,
        be.CONCEPTO,
        NULL,
        be.ORIGEN,
        NULL,
        2027
    FROM BaseExpandida be
    WHERE be.VALOR > 0;


    ------------------------------------------------------------
    -- 6️⃣ CARGAS SOCIALES (9%, 18.17%, 0.94%)
    ------------------------------------------------------------
    -- Gratificación
    INSERT INTO PLANILLA 
    (CENTRO_COSTO, PARTIDA, DIMENSION, MES, IMPORTE, ORIGEN, DNI, CONCEPTO, HORAS, ORIGEN_2, COMENTARIO, AÑO)
    SELECT 
        p.CENTRO_COSTO, 
        '94.1.1.1.036',
        NULL, p.MES,
        ROUND(p.IMPORTE * @TasaEssalud, 2),
        p.ORIGEN, NULL, p.CONCEPTO, NULL, p.ORIGEN_2, NULL, p.AÑO
    FROM PLANILLA p 
    WHERE p.AÑO=2027 AND p.ORIGEN='Carga Academica' AND p.PARTIDA='94.1.1.1.033';

    -- Essalud
    INSERT INTO PLANILLA 
    (CENTRO_COSTO, PARTIDA, DIMENSION, MES, IMPORTE, ORIGEN, DNI, CONCEPTO, HORAS, ORIGEN_2, COMENTARIO, AÑO)
    SELECT 
        p.CENTRO_COSTO, 
        '94.1.1.1.035',
        NULL, p.MES,
        ROUND(p.IMPORTE * @TasaGrat, 2),
        p.ORIGEN, NULL, p.CONCEPTO, NULL, p.ORIGEN_2, NULL, p.AÑO
    FROM PLANILLA p 
    WHERE p.AÑO=2027 AND p.ORIGEN='Carga Academica' AND p.PARTIDA='94.1.1.1.033';

    -- Asignación Familiar
    INSERT INTO PLANILLA 
    (CENTRO_COSTO, PARTIDA, DIMENSION, MES, IMPORTE, ORIGEN, DNI, CONCEPTO, HORAS, ORIGEN_2, COMENTARIO, AÑO)
    SELECT 
        p.CENTRO_COSTO, 
        '94.1.1.1.034',
        NULL, p.MES,
        ROUND(p.IMPORTE * @TasaAsigFam, 2),
        p.ORIGEN, NULL, p.CONCEPTO, NULL, p.ORIGEN_2, NULL, p.AÑO
    FROM PLANILLA p 
    WHERE p.AÑO=2027 AND p.ORIGEN='Carga Academica' AND p.PARTIDA='94.1.1.1.033';


    ------------------------------------------------------------
    -- 7️⃣ RESUMEN FINAL
    ------------------------------------------------------------
    SELECT PARTIDA, COUNT(*) AS Registros, SUM(IMPORTE) AS Total
    FROM PLANILLA
    WHERE ORIGEN='Carga Academica' AND AÑO=2027
    GROUP BY PARTIDA;

END;
GO

-- Verificación
SELECT name, create_date, modify_date FROM sys.procedures WHERE name LIKE 'sp_Valorizar%2027' ORDER BY name;
