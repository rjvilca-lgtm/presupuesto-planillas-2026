/*
  Prácticas pre-profesionales 2027: tarifa por hora de practicante.

  La pestaña «Prácticas pre-profesionales» la ven los usuarios con rol
  DEPARTAMENTO o AREA (el de ayudantías) y Presupuesto. Lo que registran va a
  DATOS_ENTRADA con HOJA_ORIGEN = 'Practicas': en HORAS las horas del mes (solo
  marzo a diciembre), en TARIFA la tarifa por hora y en IMPORTE horas × tarifa.

  La tarifa es una sola fila de tarifas_2027 (HOJA_ORIGEN = 'Practicas').
  Empieza en S/ 9.00 y Desarrollo Humano la cambia en su pestaña › Tarifas.

  No crea tablas, roles ni permisos: la app ya escribe DATOS_ENTRADA y lee y
  actualiza tarifas_2027. Se puede ejecutar más de una vez (no pisa una tarifa
  que Desarrollo Humano ya haya cambiado).
*/

IF NOT EXISTS (SELECT 1 FROM dbo.tarifas_2027 WHERE HOJA_ORIGEN = 'Practicas')
    INSERT INTO dbo.tarifas_2027 (HOJA_ORIGEN, TIPO, TARIFA)
    VALUES ('Practicas', 'Hora de practica', 9.00);
GO

-- Verificación: una fila, 9.00
SELECT HOJA_ORIGEN, TIPO, TARIFA FROM dbo.tarifas_2027 WHERE HOJA_ORIGEN = 'Practicas';
