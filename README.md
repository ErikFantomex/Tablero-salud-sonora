# Tablero de Salud Sonora

Tablero Streamlit para explorar accesibilidad a servicios de salud, contexto socioeconómico y escenarios de red vial en Sonora. El MVP funciona con los datos versionados en [`datos_mvp/`](datos_mvp/) y no necesita descargar datos al arrancar.

## Qué incluye

- **Resumen estatal y municipios:** población, tiempos y brechas de acceso.
- **Localidades:** búsqueda por nombre o clave INEGI y mapa de accesibilidad.
- **Ingreso y bienestar:** agregados ENIGH para Sonora y sus municipios.
- **Red vial y brigadas:** cierre simulado de carretera y recorrido optimizado para una brigada en el piloto de Yécora.
- **Calidad de datos:** cobertura, métodos de cálculo y advertencias.

## Resultados principales del MVP

- La accesibilidad se calcula como tiempo de traslado en automóvil al servicio más cercano. La mayoría de las brechas se concentra en el acceso hospitalario.
- El escenario de cierre vial de Yécora cubre **70 localidades y 4,558 personas**. Las 70 siguen conectadas; el aumento máximo observado es de **5.23 minutos**.
- En el ejemplo de brigada, el recorrido optimizado baja de **262.9 a 202.3 minutos**, un ahorro estimado de **60.6 minutos**. No incluye tiempo de visita ni tramos fuera de la red.

Estos son escenarios analíticos, no mediciones de operación en campo.

## Ejecutar el tablero

Con Docker:

```powershell
docker compose up --build --wait app
```

Sin Docker:

```powershell
python -m pip install -r requirements.txt
python -m pip install -e .
python -m streamlit run app.py
```

Abre <http://localhost:8501>.

## Datos y reproducibilidad

`datos_mvp/manifest.json` registra versión, fuentes, fechas y SHA-256. El paquete incluye Parquet de salud e ingreso, límites municipales, el resumen de SAKBÉ y los archivos viales del piloto. Los tiempos SAKBÉ representan rutas en automóvil en condiciones óptimas; algunas localidades usan respaldos cuando no hay ruta disponible.

Para trabajar con datos generados localmente, usa el Compose adicional:

```powershell
docker compose -f docker-compose.yml -f docker-compose.datos.yml up --build
```

El mapa puede usar el modo local (`SONORA_MAPA=sin_teselas`) o teselas externas (`SONORA_MAPA=en_linea`).

## Estructura útil

```text
app.py                         # aplicación Streamlit
datos_mvp/                     # datos publicados del MVP
src/health_data/               # ingesta, ruteo y visualizaciones
enigh-sonora-main/             # pipeline de ENIGH
notebooks/                     # EDA y generación de escenarios
tests/                         # pruebas automatizadas
Dockerfile                     # ejecución reproducible
docker-compose*.yml            # tablero y modo de actualización
```

## Pruebas

```powershell
docker compose run --rm app python -m pytest tests -q
```

## Alcance y límites

El tablero mide accesibilidad geográfica potencial. No mide espera dentro del establecimiento, capacidad, calidad, disponibilidad de medicamentos, costo ni transporte público. El TSP y los cierres viales son simulaciones sobre la red disponible.

Para actualizar el MVP, genera nuevos datos con los pipelines, revisa el reporte de comparación y publica una nueva versión con `python -m health_data.publicar_mvp --version <versión>`.

Proyecto académico de la Maestría en Ciencia de Datos de la Universidad de Sonora.
