"""Sonora: salud, ingreso y territorio. Entrada única de Streamlit."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

RAIZ = Path(__file__).resolve().parent
for carpeta in (RAIZ / "src", RAIZ / "enigh-sonora-main"):
    if str(carpeta) not in sys.path:
        sys.path.insert(0, str(carpeta))

from enigh import config as enigh  # noqa: E402
from health_data import analisis, config, territorio  # noqa: E402
from health_data.processing import cartografia  # noqa: E402
from health_data.visualization import mapas  # noqa: E402

TITULO = "Sonora: salud, ingreso y territorio"
VISTAS = ["Resumen", "Municipios", "Localidades", "Ingreso y bienestar", "Calidad y metodología"]
DESCRIPCIONES = {
    "Resumen": "Una lectura rápida de las principales barreras para llegar a servicios de salud y del ingreso en Sonora.",
    "Municipios": "Compara los 72 municipios. Elige una medida para ver dónde se concentra cada situación.",
    "Localidades": "Busca comunidades, filtra los resultados y consulta sus tiempos de traslado estimados.",
    "Ingreso y bienestar": "Explora cómo se distribuye el ingreso y cómo han cambiado las condiciones de vida.",
    "Calidad y metodología": "Conoce las fuentes, la cobertura y las precauciones para interpretar los resultados.",
}
ESTILOS = """
<style>
/* Diseño de lectura: ancho acotado, controles claros y tarjetas de indicadores. */
.block-container {max-width: 1320px; padding-top: 1.4rem; padding-bottom: 3rem;}
section[data-testid="stSidebar"] {background: #f2f7f6; border-right: 1px solid #d9e7e4;}
h1, h2, h3 {color: #153b43; letter-spacing: -.025em;}
h1 {font-size: clamp(1.8rem, 3.5vw, 2.75rem) !important; line-height: 1.15 !important;}
h2 {font-size: clamp(1.35rem, 2.5vw, 1.8rem) !important; margin-top: 1.5rem !important;}
[data-testid="stMetric"] {background: #fff; border: 1px solid #dce9e6; border-radius: 14px; padding: 1rem; box-shadow: 0 3px 16px #153b4309; min-height: 130px;}
[data-testid="stMetricLabel"] {font-size: .95rem; color: #47636a;}
[data-testid="stMetricValue"] {font-size: clamp(1.35rem, 2.6vw, 2rem); color: #0b6159;}
[data-testid="stPlotlyChart"] {background: white; border: 1px solid #e2ecea; border-radius: 14px; padding: .3rem;}
.stDataFrame {border: 1px solid #e2ecea; border-radius: 12px; overflow: hidden;}
.intro {background: #edf6f3; border-left: 4px solid #087f73; border-radius: 0 12px 12px 0; padding: .9rem 1.1rem; margin: .1rem 0 1.4rem; color: #254d53; line-height: 1.5;}
.eyebrow {color: #087f73; font-size: .83rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; margin-bottom: -.5rem;}
@media (max-width: 768px) {
  .block-container {padding: 1rem .8rem 2rem;}
  [data-testid="stHorizontalBlock"] {flex-wrap: wrap; gap: .55rem;}
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {min-width: min(100%, 280px); flex: 1 1 100% !important;}
  [data-testid="stMetric"] {min-height: auto;}
  [data-testid="stPlotlyChart"] {overflow-x: auto;}
}
</style>
"""
SALUD = "Población ITER 2020 · establecimientos CLUES · tiempos en automóvil SAKBÉ o estimaciones."
PALETA = ["#087f73", "#bd511d"]
UNIDAD = "Pesos corrientes por persona al trimestre"

CAMPOS_MUNICIPIO = {
    "municipio": "Municipio",
    "cvegeo": "Clave INEGI",
    "umbral_centro": "Umbral atención básica (min)",
    "umbral_hospital": "Umbral hospital (min)",
    "population": "Población",
    "poblacion_evaluada": "Población evaluada",
    "acceso_comprometido": "Personas con acceso comprometido",
    "pct_comprometido": "% con acceso comprometido",
    "minutos_hospital": "Minutos al hospital (media ponderada)",
    "pct_sakbe": "% población con ruta hospitalaria SAKBÉ",
    "doble_barrera": "Personas con doble barrera",
    "poblacion_doble_evaluable": "Población evaluada para doble barrera",
    "pct_doble_evaluable": "% evaluado para doble barrera",
    "pct_marginacion_alta": "% en localidades de marginación alta o muy alta",
    "poblacion_con_marginacion": "Población con dato CONAPO",
    "anio_enigh": "Año ENIGH",
    "ing_pc": "Ingreso trimestral per cápita",
    "ing_pc_ic_inferior": "Límite inferior IC 95 %",
    "ing_pc_ic_superior": "Límite superior IC 95 %",
    "n_hogares": "Hogares en muestra ENIGH",
    "n_upm": "UPM ENIGH",
    "estado_enigh": "Calidad ENIGH",
}

CAMPOS_LOCALIDAD = {
    "locality_id": "Clave INEGI", "locality_name": "Localidad",
    "municipality_name": "Municipio", "population": "Población",
    "primary_time_min": "Minutos a la atención básica más cercana",
    "basic_destination": "Tipo de destino para atención básica",
    "basic_clues": "CLUES de referencia para atención básica",
    "basic_method": "Método · atención básica",
    "primary_facility_time_min": "Minutos a la unidad de primer nivel",
    "secondary_time_min": "Minutos al hospital",
    "primary_method": "Método · unidad de primer nivel",
    "secondary_method": "Origen · hospital",
    "nearest_primary_clues": "CLUES · unidad de primer nivel",
    "nearest_secondary_clues": "CLUES · hospital",
    "grado_marginacion": "Marginación CONAPO",
    "transporte_foraneo": "Transporte foráneo",
    "pct_sin_afiliacion": "% sin afiliación",
    "pct_60_y_mas": "% 60 años o más",
    "pct_con_discapacidad": "% con discapacidad",
    "pct_lengua_indigena": "% hablantes de lengua indígena",
    "disponibilidad": "Disponibilidad ITER",
}


@dataclass(frozen=True)
class FuentesTablero:
    """Rutas de una sola publicación de datos o del resultado de los pipelines."""

    mvp: Path | None
    metadatos: dict | None
    sin_teselas: bool

    @property
    def salud(self) -> Path:
        return self.mvp / "salud" if self.mvp else config.PROCESSED_DATA_DIR

    @property
    def tabla_salud(self) -> Path:
        return self.salud / "accesibilidad_localidades.parquet" if self.mvp else config.ARCHIVO_TABLA_FINAL

    @property
    def raiz_enigh(self) -> Path:
        return self.mvp / "enigh" if self.mvp else enigh.DIR_PROCESSED

    @property
    def manifiesto_enigh(self) -> Path:
        return self.raiz_enigh / "manifiesto.json" if self.mvp else enigh.ARCHIVO_MANIFIESTO

    @property
    def geografia(self) -> tuple[Path, ...]:
        archivo = "sonora_municipios.geojson"
        if self.mvp:
            return (self.raiz_enigh / "geografia" / archivo,)
        return (cartografia.NOMBRE_MUNICIPIOS_SONORA, enigh.DIR_GEO / archivo)

    def ruta_agregado(self, anio: int, nombre: str) -> Path:
        if self.mvp:
            return self.raiz_enigh / "agregados" / f"ano={anio}" / f"{nombre}.parquet"
        return enigh.ruta_agregados(anio, nombre)

    def ruta_serie(self, nombre: str) -> Path:
        return self.raiz_enigh / "agregados" / f"{nombre}.parquet"


def resolver_fuentes() -> FuentesTablero:
    modo = os.environ.get("SONORA_DATOS", "").strip().lower() or "auto"
    if modo not in {"auto", "mvp", "local"}:
        raise ValueError("SONORA_DATOS debe ser auto, mvp o local.")

    carpeta = RAIZ / "datos_mvp"
    mvp = carpeta if modo == "mvp" or (modo == "auto" and carpeta.exists()) else None
    modo_mapa = os.environ.get("SONORA_MAPA", "").strip().lower() or ("sin_teselas" if mvp else "en_linea")
    if modo_mapa not in {"sin_teselas", "en_linea"}:
        raise ValueError("SONORA_MAPA debe ser sin_teselas o en_linea.")

    metadatos = None
    if mvp:
        try:
            metadatos = json.loads((mvp / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("No se pudo abrir datos_mvp/manifest.json. Revisa que la copia de datos esté completa.") from exc
        if not isinstance(metadatos, dict) or metadatos.get("schema_version") != 1:
            raise ValueError("El esquema de datos_mvp/manifest.json no es compatible con el tablero.")
        if not all(isinstance(metadatos.get(key), str) and metadatos[key] for key in ("version", "generado_en")):
            raise ValueError("Falta la versión o la fecha de generación en datos_mvp/manifest.json.")
        archivos = metadatos.get("archivos")
        if not isinstance(archivos, dict) or not archivos:
            raise ValueError("Falta el inventario de archivos de datos_mvp.")
        faltante = next((nombre for nombre in archivos if not (mvp / nombre).is_file()), None)
        if faltante:
            raise ValueError(f"La copia de datos del MVP está incompleta. Falta {faltante}.")

    return FuentesTablero(mvp, metadatos, sin_teselas=modo_mapa == "sin_teselas")


@st.cache_data(show_spinner=False)
def leer_parquet(ruta: Path, version: int) -> pd.DataFrame:
    return pd.read_parquet(ruta)


def leer(ruta: Path) -> pd.DataFrame:
    if not ruta.is_file():
        return pd.DataFrame()
    try:
        return leer_parquet(ruta, ruta.stat().st_mtime_ns)
    except (OSError, ValueError):
        st.warning(f"No se pudo leer {ruta.name}. Revisa o vuelve a generar ese producto.")
        return pd.DataFrame()


def leer_contexto(ruta: Path, campo: str) -> pd.DataFrame:
    datos = leer(ruta)
    if datos.empty:
        return datos
    if not {"cvegeo", campo}.issubset(datos) or datos["cvegeo"].astype("string").duplicated().any():
        st.warning(f"No se pudo validar {ruta.name}. Se muestran las rutas con el contexto disponible.")
        return pd.DataFrame()
    return datos


@st.cache_data(show_spinner=False)
def leer_geografia(ruta: Path, version: int) -> dict | None:
    try:
        geo = cartografia.cargar_geojson(ruta)
    except (ValueError, OSError):
        return None
    return geo if isinstance(geo, dict) and geo.get("features") else None


def cartografia_municipal(fuentes: FuentesTablero) -> dict | None:
    for ruta in fuentes.geografia:
        if ruta.is_file():
            geo = leer_geografia(ruta, ruta.stat().st_mtime_ns)
            if geo:
                return geo
    return None


def anios_enigh(fuentes: FuentesTablero) -> list[int]:
    manifiesto = fuentes.manifiesto_enigh
    if manifiesto.is_file():
        try:
            metadatos = json.loads(manifiesto.read_text(encoding="utf-8"))
            argumentos = metadatos.get("argumentos", {}) if isinstance(metadatos, dict) else None
            if not isinstance(argumentos, dict):
                raise ValueError("Formato inválido en el manifiesto ENIGH.")
            if argumentos.get("muestra") is not None:
                st.warning("Los agregados ENIGH se generaron en modo demostración. Ejecuta el pipeline completo para habilitarlos.")
                return []
        except (ValueError, OSError):
            st.warning("No se pudo verificar el manifiesto de ENIGH.")
            return []
    return [a for a in enigh.cargar_configuracion().anios_habilitados
            if fuentes.ruta_agregado(a, "deciles_sonora").is_file()]


def tabla_publica(datos: pd.DataFrame, campos: dict, archivo: str) -> None:
    tabla = datos[[c for c in campos if c in datos]].rename(columns=campos)
    st.dataframe(tabla.round(2), hide_index=True, use_container_width=True)
    st.download_button("Descargar CSV", tabla.to_csv(index=False).encode("utf-8-sig"),
                       archivo, "text/csv")


def sin_salud() -> None:
    st.info("Falta la tabla de accesibilidad. Genera los insumos y reconstruye las rutas desde el caché local.")
    st.code("python -m health_data.processing.ruteo", language="bash")


def sin_enigh() -> None:
    st.info("Los resultados de ENIGH aparecen al generar los agregados con el pipeline de la encuesta.")
    st.code("cd enigh-sonora-main\npython -m enigh.pipeline", language="bash")


def pesos(valor: float) -> str:
    return f"${valor:,.0f}" if pd.notna(valor) else "Sin dato"


def nota_rutas(localidades: pd.DataFrame) -> None:
    st.caption(SALUD)
    if "routing_consulted_at" in localidades:
        fechas = localidades["routing_consulted_at"].dropna().astype(str).str[:10]
        fechas = fechas[fechas.str.fullmatch(r"\d{4}-\d{2}-\d{2}")]
        if not fechas.empty:
            st.caption(f"Fuente de ruteo · INEGI, Sistema de Ruteo de México (SAKBÉ) v3.1. Consultas del {fechas.min()} al {fechas.max()}.")


def abrir_busqueda_localidad() -> None:
    st.session_state["seccion"] = "Localidades"
    st.session_state["municipio_localidades"] = "Todo Sonora"
    st.session_state["filtro_localidades"] = "Todas"


def resumen(
    locales: pd.DataFrame, municipios: pd.DataFrame, anios: list[int],
    centro: int, hospital: int, fuentes: FuentesTablero,
) -> None:
    st.title(TITULO)
    st.markdown("Identifica dónde es más difícil llegar a servicios de salud y cómo se relaciona con las condiciones de vida.")
    st.button("Consulta tu localidad", type="primary", on_click=abrir_busqueda_localidad)
    if locales.empty:
        sin_salud()
    else:
        acceso = int(municipios["acceso_comprometido"].sum())
        evaluada = int(municipios["poblacion_evaluada"].sum())
        cobertura = int(municipios["poblacion_sakbe"].sum())
        poblacion = int(municipios["population"].sum())
        c1, c2, c3 = st.columns(3)
        c1.metric("Personas con acceso comprometido", f"{acceso:,}", f"{100 * acceso / evaluada:.2f} % de la población evaluada" if evaluada else None, delta_color="off")
        c2.metric("Localidades con acceso comprometido", f"{locales['comprometida'].sum():,}")
        c3.metric("Población con tiempo al hospital calculado por SAKBÉ",
                  f"{100 * cobertura / poblacion:.2f} %" if poblacion else "Sin dato")
        st.info("**Cómo leer estas cifras:** ‘acceso comprometido’ significa que el traslado supera alguno de los tiempos elegidos. Solo se calcula el porcentaje con personas para las que hay información suficiente.")
        st.caption(f"Umbrales de traslado · más de {centro} min a atención básica o más de {hospital} min al hospital. Población evaluada: {evaluada:,} de {poblacion:,}.")
        nota_rutas(locales)
        m = municipios.nlargest(10, "acceso_comprometido").query("acceso_comprometido > 0")
        if not m.empty:
            figura = px.bar(m.sort_values("acceso_comprometido"), x="acceso_comprometido", y="municipio",
                            orientation="h", color_discrete_sequence=PALETA,
                            labels={"acceso_comprometido": "Personas", "municipio": "Municipio"})
            st.subheader("Dónde se concentra la barrera de traslado")
            st.plotly_chart(figura, use_container_width=True)
    st.subheader("Ingreso y desigualdad en Sonora")
    if not anios:
        sin_enigh()
        return
    anio = anios[-1]
    deciles = leer(fuentes.ruta_agregado(anio, "deciles_sonora"))
    if deciles.empty:
        return
    fila = deciles.iloc[0]
    a, b, c = st.columns(3)
    a.metric("Ingreso medio trimestral per cápita", pesos(fila.get("ing_pc_media_global", float("nan"))))
    b.metric("Ingreso mediano trimestral per cápita", pesos(fila.get("ing_pc_mediana_global", float("nan"))))
    gini = fila.get("gini_global", float("nan"))
    c.metric("Coeficiente de Gini", f"{gini:.3f}" if pd.notna(gini) else "Sin dato")
    st.caption("El ingreso está expresado por persona y por trimestre. El índice de Gini va de 0 (ingresos iguales) a 1 (mayor desigualdad).")
    st.caption(f"INEGI · ENIGH {anio} · pesos corrientes del levantamiento.")


def explorar_municipios(
    municipios: pd.DataFrame, locales: pd.DataFrame, anios: list[int],
    centro: int, hospital: int, fuentes: FuentesTablero,
) -> None:
    st.title("Explorador municipal")
    st.caption("Selecciona un indicador y usa la escala del mapa para interpretar los colores. La tabla muestra los valores exactos.")
    if municipios.empty:
        sin_salud()
        return
    m = municipios
    if anios:
        anio = st.selectbox("Levantamiento ENIGH para comparar", anios, index=len(anios) - 1)
        ingreso = leer(fuentes.ruta_agregado(anio, "municipios_sonora"))
        try:
            m = territorio.integrar_ingreso(m, ingreso, enigh.cargar_configuracion().umbrales.hogares_min_municipio)
        except (KeyError, ValueError) as exc:
            st.warning(f"No fue posible incorporar el agregado municipal de ENIGH. {exc}")
            m = territorio.integrar_ingreso(m, pd.DataFrame(), 0)
        m = m.assign(anio_enigh=anio)
    else:
        m = territorio.integrar_ingreso(m, pd.DataFrame(), 0)
        st.info("La comparación de ingreso se habilitará cuando estén disponibles los agregados de ENIGH.")
    indicadores = {
        "pct_comprometido": "%", "acceso_comprometido": "personas",
        "minutos_hospital": "min", "pct_sakbe": "%", "doble_barrera": "personas",
        "pct_marginacion_alta": "%", "ing_pc": "MXN/persona/trimestre",
    }
    opciones = [c for c in indicadores if c in m and (c in {"doble_barrera", "ing_pc"} or m[c].notna().any())]
    if opciones:
        campo = st.selectbox("Indicador del mapa", opciones, format_func=CAMPOS_MUNICIPIO.get)
        detalle = None
        if campo == "doble_barrera":
            m = m.assign(detalle_doble=m.apply(
                lambda f: f"Cobertura: {f['poblacion_doble_evaluable']:,} de {f['population']:,} personas "
                          f"({f['pct_doble_evaluable']:.1f} %)" if f["population"]
                          else "Sin población registrada",
                axis=1,
            ))
            detalle = "detalle_doble"
            evaluadas, total = m["poblacion_doble_evaluable"].sum(), m["population"].sum()
            if total:
                st.info(f"Se pudo evaluar al {evaluadas / total:.1%} de la población de Sonora "
                        f"({evaluadas:,} de {total:,} personas). Los conteos incluyen los casos confirmados. "
                        "Consulta la cobertura de cada municipio antes de comparar.")
        elif campo == "ing_pc":
            detalle = "estado_enigh"
        geo = cartografia_municipal(fuentes)
        con_datos = m.dropna(subset=[campo])
        if geo:
            figura = mapas.mapa_municipios(m, geo, columna=campo, columna_nombre="municipio",
                                          titulo=CAMPOS_MUNICIPIO[campo], unidad=indicadores[campo],
                                          sin_teselas=fuentes.sin_teselas, columna_detalle=detalle,
                                          mostrar_sin_dato=True)
            st.plotly_chart(figura, use_container_width=True)
            if campo == "ing_pc":
                st.caption(f"{len(con_datos)} de {len(m)} municipios tienen una estimación publicable. "
                           "El gris indica que el importe no está disponible. Consulta el motivo en el mapa o la tabla.")
            elif m[campo].isna().any():
                st.caption("El gris indica que no hay datos suficientes para este indicador.")
        elif {"latitude", "longitude"}.issubset(locales):
            puntos = locales.dropna(subset=["latitude", "longitude"]).sort_values("population", ascending=False)
            puntos = puntos.drop_duplicates("cvegeo")[["cvegeo", "latitude", "longitude"]].merge(con_datos, on="cvegeo")
            if not puntos.empty:
                figura = mapas.mapa_localidades(
                    puntos, columna=campo, columna_nombre="municipio", columna_municipio="municipio",
                    titulo=CAMPOS_MUNICIPIO[campo], unidad=indicadores[campo], sin_teselas=fuentes.sin_teselas,
                )
                st.plotly_chart(figura, use_container_width=True)
                st.caption("Cada marcador se ubica en la localidad con más habitantes del municipio.")
        if campo == "doble_barrera":
            por_clave = m.sort_values("municipio").set_index("cvegeo")
            clave = st.selectbox("Consultar casos y cobertura de un municipio", por_clave.index, index=None,
                                 format_func=por_clave["municipio"].get)
            if clave is not None:
                fila = por_clave.loc[clave]
                casos = fila["doble_barrera"]
                resultado = f"{casos:,.0f} personas con doble barrera confirmada" if pd.notna(casos) else "Sin población evaluable"
                st.write(f"**{fila['municipio']}** · {resultado}. {fila[detalle]}.")
        m = m.sort_values(campo, ascending=False)
    st.caption("Doble barrera · traslado al hospital por encima del umbral y localidad que reporta ausencia de transporte foráneo (RESLOC 2020). Marginación alta · porcentaje entre habitantes con dato CONAPO 2020.")
    if "ing_pc" in m and m["ing_pc"].notna().any():
        comparables = m.dropna(subset=["ing_pc", "pct_comprometido"])
        if not comparables.empty:
            st.subheader("Ingreso y barrera de traslado")
            st.plotly_chart(px.scatter(
                comparables, x="ing_pc", y="pct_comprometido", size="population",
                hover_name="municipio", hover_data=["n_hogares", "estado_enigh"],
                labels=CAMPOS_MUNICIPIO, color_discrete_sequence=PALETA,
            ), use_container_width=True)
    st.caption("El ingreso municipal es exploratorio y se publica con su estado de calidad. Las coincidencias territoriales combinan años y fuentes distintos.")
    tabla_publica(m.assign(umbral_centro=centro, umbral_hospital=hospital),
                  CAMPOS_MUNICIPIO, "municipios_sonora.csv")


def explorar_localidades(locales: pd.DataFrame, centro: int, hospital: int, fuentes: FuentesTablero) -> None:
    st.title("Localidades y acceso a la salud")
    st.caption("Filtra por municipio y tipo de barrera. Busca una localidad para ver sus tiempos y destinos de atención.")
    if locales.empty:
        sin_salud()
        return
    a, b, c = st.columns(3)
    municipio = a.selectbox("Municipio", ["Todo Sonora", *sorted(locales["municipality_name"].dropna().unique())],
                            key="municipio_localidades")
    filtro = b.selectbox("Mostrar", ["Acceso comprometido", "Doble barrera", "Todas"], key="filtro_localidades")
    nivel = c.selectbox("Tiempo en el mapa", ["Hospital", "Atención básica"])
    t = locales if municipio == "Todo Sonora" else locales[locales["municipality_name"].eq(municipio)]
    if filtro == "Acceso comprometido":
        t = t[t["comprometida"]]
    elif filtro == "Doble barrera":
        t = t[t["doble_barrera"]]
    if t.empty:
        st.info("Ninguna localidad coincide con los filtros.")
        return
    a, b = st.columns(2)
    a.metric("Localidades en la selección", f"{len(t):,}")
    b.metric("Población en la selección", f"{int(t['population'].sum()):,}")
    ordenadas = t.sort_values("population", ascending=False)
    fichas = ordenadas.set_index("locality_id")
    nombres = fichas["locality_name"] + " · " + fichas["municipality_name"] + " (" + fichas.index + ")"
    clave = st.selectbox("Buscar por localidad o clave", fichas.index, index=None, format_func=nombres.get)
    if clave is not None:
        ficha_localidad(fichas.loc[clave], fuentes)
    campo, metodo = ("secondary_time_min", "secondary_method") if nivel == "Hospital" else ("primary_time_min", "basic_method")
    if {"latitude", "longitude"}.issubset(t):
        figura = mapas.mapa_localidades(
            t, columna=campo, columna_metodo=metodo, titulo=f"Traslado · {nivel.lower()}",
            geojson=cartografia_municipal(fuentes) if fuentes.sin_teselas else None,
            sin_teselas=fuentes.sin_teselas, localidad_destacada=clave,
        )
        st.plotly_chart(figura, use_container_width=True)
        visibles = len(figura.data[0].lat) if figura.data else 0
        if visibles < len(t):
            st.caption(f"El mapa muestra {visibles:,} de {len(t):,} localidades de la selección. "
                       "La tabla incluye todas. Para ver más detalle, filtra por municipio o busca una localidad.")
        if clave is not None and len(figura.data) > 1:
            st.caption("El punto azul destaca la localidad seleccionada. Tócalo o pasa el cursor para consultar su tiempo.")
        elif clave is not None:
            st.caption("La localidad seleccionada no tiene coordenadas o tiempo para este mapa. Consulta su ficha.")
    tabla_publica(ordenadas, CAMPOS_LOCALIDAD, "localidades_sonora.csv")
    if filtro == "Todas" and "poblacion_sin_afiliacion" in t:
        grupos = analisis.grupos_vulnerables(t, umbral_primer=centro, umbral_segundo=hospital)
        if not grupos.empty:
            with st.expander("Brechas por grupo en la selección"):
                st.plotly_chart(mapas.barras_grupos_vulnerables(grupos), use_container_width=True)
                st.caption("La comparación usa la población con dato de cada grupo en la selección.")
    nota_rutas(t)


def ficha_localidad(fila: pd.Series, fuentes: FuentesTablero) -> None:
    st.subheader(fila["locality_name"])
    establecimientos = leer(fuentes.salud / "salud-001_establecimientos.parquet")
    unidades = {}
    if {"clues", "nombre_unidad"}.issubset(establecimientos):
        unidades = establecimientos.drop_duplicates("clues").set_index("clues")["nombre_unidad"].to_dict()
    basica, hospital = st.columns(2)
    for col, titulo, tiempo, clues, metodo in (
        (basica, "Atención básica más cercana", fila["primary_time_min"], fila["basic_clues"], fila["basic_method"]),
        (hospital, "Hospital", fila["secondary_time_min"], fila.get("nearest_secondary_clues"), fila.get("secondary_method")),
    ):
        col.metric(titulo, f"{tiempo:.0f} min" if pd.notna(tiempo) else "Sin tiempo")
        if pd.isna(tiempo):
            continue
        if pd.notna(clues):
            nombre = unidades.get(clues, clues)
            referencia = pd.notna(metodo) and metodo != "sakbe"
            col.write(f"Unidad de referencia · {nombre}" if referencia else nombre)
        if pd.notna(metodo):
            col.caption(mapas.METODOS_TRASLADO.get(metodo, metodo))
        else:
            col.caption("Método no identificado en esta versión de los datos.")
    destino = fila["basic_destination"]
    if isinstance(destino, str) and destino == "Hospital":
        basica.caption("Se usó el tiempo al hospital por ser el menor de los dos.")
    elif pd.isna(fila["basic_destination"]) and pd.notna(fila["primary_time_min"]):
        basica.caption("Esta versión de los datos no identifica el destino asociado al mínimo.")


def ingreso_bienestar(anios: list[int], fuentes: FuentesTablero) -> None:
    st.title("Ingreso y bienestar")
    st.caption("Los deciles dividen a la población en diez grupos según ingreso: el 1 reúne a quienes tienen menos y el 10 a quienes tienen más.")
    if not anios:
        sin_enigh()
        return
    vista = st.radio("Análisis", ["Distribución", "Evolución", "Bienestar"], horizontal=True, key="analisis_enigh")
    if vista != "Evolución":
        anio = st.selectbox("Año de la encuesta", anios, index=len(anios) - 1)
    if vista == "Distribución":
        partes = []
        for ambito, nombre in (("Sonora", "deciles_sonora"), ("México", "deciles_nacionales")):
            tabla = leer(fuentes.ruta_agregado(anio, nombre))
            if not tabla.empty:
                partes.append(tabla.assign(ámbito=ambito))
        if not partes:
            sin_enigh()
            return
        datos = pd.concat(partes, ignore_index=True).query("1 <= decil <= 10").copy()
        datos["decil"] = datos["decil"].astype(str)
        if {"ing_pc_ic_inferior", "ing_pc_ic_superior"}.issubset(datos):
            datos["ic_mas"] = (datos["ing_pc_ic_superior"] - datos["ing_pc"]).clip(lower=0)
            datos["ic_menos"] = (datos["ing_pc"] - datos["ing_pc_ic_inferior"]).clip(lower=0)
        st.plotly_chart(px.bar(datos, x="decil", y="ing_pc", color="ámbito", barmode="group",
                               error_y="ic_mas" if "ic_mas" in datos else None,
                               error_y_minus="ic_menos" if "ic_menos" in datos else None,
                               color_discrete_sequence=PALETA,
                               labels={"decil": "Decil nacional", "ing_pc": UNIDAD}), use_container_width=True)
        st.caption("Cortes nacionales comunes y medias ponderadas. Las barras de error muestran el intervalo de confianza al 95 % cuando está disponible.")
        if "ic_mas" not in datos or not datos["ic_mas"].notna().any():
            st.info("Este levantamiento se cargó con estimaciones puntuales. Los intervalos de confianza están pendientes de calcular.")
        tabla_publica(datos.assign(anio=anio), {
            "ámbito": "Ámbito", "anio": "Año ENIGH", "decil": "Decil nacional", "ing_pc": UNIDAD,
            "n_hogares": "Hogares en muestra", "ing_pc_ic_inferior": "IC 95 % inferior",
            "ing_pc_ic_superior": "IC 95 % superior", "ing_pc_cv": "Coeficiente de variación",
            "ing_pc_fiable": "Precisión según ENIGH del proyecto",
        }, "deciles_enigh.csv")
    elif vista == "Evolución":
        serie = leer(fuentes.ruta_serie("serie_deciles_sonora"))
        if serie.empty:
            st.info("Genera al menos dos levantamientos juntos para ver la evolución.")
            return
        cfg = enigh.cargar_configuracion()
        serie["factor_inpc"] = serie["anio"].map(cfg.deflactor)
        serie = serie.dropna(subset=["factor_inpc"]).query("1 <= decil <= 10").sort_values(["decil", "anio"])
        if serie.empty:
            st.info("Faltan deflactores INPC para los años procesados.")
            return
        serie["ingreso_real"] = serie["ing_pc"] * serie["factor_inpc"]
        serie["decil"] = serie["decil"].astype(str)
        serie["anio"] = serie["anio"].astype(str)
        st.plotly_chart(px.line(serie, x="anio", y="ingreso_real", color="decil", markers=True,
                                labels={"anio": "Levantamiento", "decil": "Decil nacional",
                                        "ingreso_real": f"Pesos de {cfg.anio_base_deflactor} por persona al trimestre"}),
                        use_container_width=True)
        desigualdad = leer(fuentes.ruta_serie("serie_desigualdad"))
        if not desigualdad.empty:
            st.plotly_chart(px.line(desigualdad.sort_values("anio").assign(anio=lambda d: d["anio"].astype(str)),
                                    x="anio", y="gini", color="ambito", markers=True,
                                    color_discrete_sequence=PALETA,
                                    labels={"anio": "Levantamiento", "gini": "Coeficiente de Gini", "ambito": "Ámbito"}),
                            use_container_width=True)
        st.caption("Los puntos corresponden a levantamientos de ENIGH. 2020 fue un año atípico por la pandemia.")
    else:
        bienestar = leer(fuentes.ruta_agregado(anio, "bienestar_sonora"))
        if bienestar.empty:
            st.info("Genera el perfil de bienestar con el pipeline ENIGH.")
            return
        dominio = st.selectbox("Dominio", bienestar["dominio"].dropna().unique())
        sub = bienestar[bienestar["dominio"].eq(dominio)]
        indicador = st.selectbox("Indicador", sub["etiqueta"].dropna().unique())
        sub = sub[sub["etiqueta"].eq(indicador)].sort_values("grupo").assign(anio=anio)
        unidad = sub["unidad"].iloc[0]
        if {"ic_inferior", "ic_superior"}.issubset(sub):
            sub["ic_mas"] = (sub["ic_superior"] - sub["valor"]).clip(lower=0)
            sub["ic_menos"] = (sub["valor"] - sub["ic_inferior"]).clip(lower=0)
        figura = px.bar(sub, x=sub["grupo"].astype(str), y="valor", color_discrete_sequence=PALETA,
                        error_y="ic_mas" if "ic_mas" in sub else None,
                        error_y_minus="ic_menos" if "ic_menos" in sub else None,
                        labels={"x": "Decil nacional", "valor": unidad})
        if unidad == "proporción":
            figura.update_yaxes(tickformat=".0%")
        st.plotly_chart(figura, use_container_width=True)
        tabla_publica(sub, {
            "anio": "Año ENIGH", "grupo": "Decil nacional", "etiqueta": "Indicador", "unidad": "Unidad",
            "valor": "Estimación", "n_hogares": "Hogares en muestra", "ic_inferior": "IC 95 % inferior",
            "ic_superior": "IC 95 % superior", "fiable": "Precisión según ENIGH del proyecto",
            "motivo": "Observación de calidad",
        }, "bienestar_enigh.csv")


@st.cache_data(show_spinner=False)
def auditar_cache(ruta: Path, version: int) -> pd.DataFrame:
    return territorio.auditar_cache(ruta)


def metodologia(locales: pd.DataFrame, anios: list[int], fuentes: FuentesTablero) -> None:
    st.title("Calidad y metodología")
    if fuentes.metadatos:
        st.caption(
            f"Datos del MVP · versión {fuentes.metadatos['version']} · "
            f"fecha de generación {fuentes.metadatos['generado_en'][:10]}."
        )
    st.markdown("""
**Acceso.** Para atención básica se usa el menor tiempo entre una unidad de primer nivel y un hospital.
SAKBÉ calcula el tiempo de un trayecto en automóvil sobre la red vial. Para localidades sin esa ruta,
el respaldo CONEVAL asigna un tiempo típico de localidades comparables. Si ese respaldo tampoco está disponible,
el tiempo se estima a partir de la distancia en línea recta.

**Contexto territorial.** ITER, RESLOC y CONAPO corresponden a 2020. Los resultados describen
localidades o agregados municipales. La marginación de una localidad caracteriza su contexto territorial.

**Ingreso.** ENIGH estima ingresos y bienestar para hogares, con factores de expansión.
Las comparaciones municipales son exploratorias. Cuando la muestra es insuficiente o se reporta baja
precisión, el importe queda vacío en la tabla y la descarga. El mapa muestra esos municipios en gris.
Las series en pesos constantes usan el INPC de INEGI.
""")
    if not locales.empty:
        nota_rutas(locales)
        conteos = []
        for nivel, campo in (("Centro de salud", "primary_method"), ("Hospital", "secondary_method")):
            if campo in locales:
                etiquetas = locales[campo].map(mapas.METODOS_TRASLADO).fillna("Método no identificado")
                por_metodo = locales.groupby(etiquetas)["population"].agg(["size", "sum"])
                conteos.append(por_metodo.reset_index().set_axis(["Método", "Localidades", "Población"], axis=1).assign(Nivel=nivel))
        if conteos:
            st.subheader("Cobertura por método de traslado")
            st.dataframe(pd.concat(conteos, ignore_index=True), hide_index=True)
    st.subheader("Resumen del caché SAKBÉ")
    if fuentes.mvp:
        try:
            ruta = fuentes.salud / "sakbe_resumen.json"
            campos = ["servicio", "respuestas", "exitosas", "primera_consulta", "ultima_consulta"]
            auditoria = pd.DataFrame(json.loads(ruta.read_text(encoding="utf-8")))[campos]
        except (OSError, ValueError, TypeError, KeyError):
            auditoria = None
            st.warning("El resumen SAKBÉ de esta versión de datos no está disponible.")
    else:
        auditoria = None
        ruta = config.INTERIM_DATA_DIR / "sakbe_cache.sqlite"
        if ruta.is_file():
            try:
                auditoria = auditar_cache(ruta, ruta.stat().st_mtime_ns)
            except (sqlite3.Error, pd.errors.DatabaseError, OSError):
                st.warning("El resumen del caché local no está disponible.")
        else:
            st.caption("Esta instalación sirve los resultados procesados.")
    if auditoria is not None:
        st.dataframe(auditoria, hide_index=True)
        st.caption("Los conteos corresponden a respuestas almacenadas de la API. Una localidad puede requerir varias consultas.")
    st.subheader("Levantamientos ENIGH disponibles")
    st.write(", ".join(map(str, anios)) if anios else "Pendientes de procesar.")
    st.caption("Proyecto Salud Sonora y tablero ENIGH de Julio Waissman · Maestría en Ciencia de Datos, Universidad de Sonora.")


def main() -> None:
    st.set_page_config(page_title=TITULO, layout="wide", initial_sidebar_state="auto")
    st.markdown(ESTILOS, unsafe_allow_html=True)
    try:
        fuentes = resolver_fuentes()
    except ValueError as exc:
        st.error(str(exc))
        return
    cfg = config.cargar_configuracion().umbrales
    with st.sidebar:
        st.header("Explora Sonora")
        st.caption("Salud · territorio · bienestar")
        vista = st.radio("Secciones", VISTAS, key="seccion")
        centro, hospital = cfg.tiempo_critico_min, cfg.tiempo_critico_segundo_nivel_min
        if vista in ("Resumen", "Municipios", "Localidades"):
            with st.expander("Escenarios de traslado"):
                centro = st.slider("Atención básica (min)", 15, 240, centro, 5)
                hospital = st.slider("Hospital (min)", 15, 360, hospital, 5)
                st.caption("Ajusta el tiempo que consideras un traslado largo. Los indicadores se recalculan al instante.")
        st.caption("Datos preparados para consulta; no necesitas descargar fuentes.")
    st.markdown('<div class="eyebrow">Tablero público de Sonora</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="intro">{DESCRIPCIONES[vista]}</div>', unsafe_allow_html=True)
    anios = anios_enigh(fuentes)
    if vista == "Ingreso y bienestar":
        ingreso_bienestar(anios, fuentes)
        return
    locales = leer(fuentes.tabla_salud)
    if not locales.empty:
        try:
            locales = territorio.preparar_localidades(
                locales,
                leer_contexto(fuentes.salud / "conapo-marg-001_localidades.parquet", "grado_marginacion"),
                leer_contexto(fuentes.salud / "inegi-resloc-001_localidades.parquet", "transporte_foraneo"),
                umbral_centro=centro, umbral_hospital=hospital,
            )
        except (KeyError, ValueError) as exc:
            st.warning(f"No fue posible validar la tabla de localidades. {exc}")
            locales = pd.DataFrame()
    municipios = territorio.resumir_municipios(locales) if not locales.empty else pd.DataFrame()
    if vista == "Resumen":
        resumen(locales, municipios, anios, centro, hospital, fuentes)
    elif vista == "Municipios":
        explorar_municipios(municipios, locales, anios, centro, hospital, fuentes)
    elif vista == "Localidades":
        explorar_localidades(locales, centro, hospital, fuentes)
    else:
        metodologia(locales, anios, fuentes)


if __name__ == "__main__":
    main()
