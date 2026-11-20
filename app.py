"""Sonora: salud, ingreso y territorio. Entrada única de Streamlit."""

from __future__ import annotations

import json
import sqlite3
import sys
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
SALUD = "Población ITER 2020 · establecimientos CLUES · tiempos en automóvil SAKBÉ o estimaciones."
PALETA = ["#087f73", "#bd511d"]
UNIDAD = "Pesos corrientes por persona al trimestre"

CAMPOS_MUNICIPIO = {
    "municipio": "Municipio",
    "cvegeo": "Clave INEGI",
    "umbral_centro": "Umbral centro de salud (min)",
    "umbral_hospital": "Umbral hospital (min)",
    "population": "Población",
    "poblacion_evaluada": "Población evaluada",
    "acceso_comprometido": "Personas con acceso comprometido",
    "pct_comprometido": "% con acceso comprometido",
    "minutos_hospital": "Minutos al hospital (media ponderada)",
    "pct_sakbe": "% población con ruta hospitalaria SAKBÉ",
    "doble_barrera": "Personas con doble barrera",
    "poblacion_doble_evaluable": "Población evaluada para doble barrera",
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
    "primary_time_min": "Minutos al centro de salud",
    "secondary_time_min": "Minutos al hospital",
    "primary_method": "Origen · centro de salud",
    "secondary_method": "Origen · hospital",
    "nearest_primary_clues": "CLUES · centro de salud",
    "nearest_secondary_clues": "CLUES · hospital",
    "grado_marginacion": "Marginación CONAPO",
    "transporte_foraneo": "Transporte foráneo",
    "pct_sin_afiliacion": "% sin afiliación",
    "pct_60_y_mas": "% 60 años o más",
    "pct_con_discapacidad": "% con discapacidad",
    "pct_lengua_indigena": "% hablantes de lengua indígena",
    "disponibilidad": "Disponibilidad ITER",
}


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


def leer_contexto(nombre: str, campo: str) -> pd.DataFrame:
    datos = leer(config.PROCESSED_DATA_DIR / nombre)
    if datos.empty:
        return datos
    if not {"cvegeo", campo}.issubset(datos) or datos["cvegeo"].astype("string").duplicated().any():
        st.warning(f"No se pudo validar {nombre}. Se muestran las rutas con el contexto disponible.")
        return pd.DataFrame()
    return datos


@st.cache_data(show_spinner=False)
def leer_geografia(ruta: Path, version: int) -> dict | None:
    try:
        geo = cartografia.cargar_geojson(ruta)
    except (ValueError, OSError):
        return None
    return geo if isinstance(geo, dict) and geo.get("features") else None


def cartografia_municipal() -> dict | None:
    for ruta in (cartografia.NOMBRE_MUNICIPIOS_SONORA, enigh.DIR_GEO / "sonora_municipios.geojson"):
        if ruta.is_file():
            geo = leer_geografia(ruta, ruta.stat().st_mtime_ns)
            if geo:
                return geo
    return None


def anios_enigh() -> list[int]:
    manifiesto = enigh.ARCHIVO_MANIFIESTO
    if manifiesto.is_file():
        try:
            argumentos = json.loads(manifiesto.read_text(encoding="utf-8")).get("argumentos", {})
            if argumentos.get("muestra") is not None:
                st.warning("Los agregados ENIGH se generaron en modo demostración. Ejecuta el pipeline completo para habilitarlos.")
                return []
        except (ValueError, OSError):
            st.warning("No se pudo verificar el manifiesto de ENIGH.")
            return []
    return [a for a in enigh.cargar_configuracion().anios_habilitados
            if enigh.ruta_agregados(a, "deciles_sonora").is_file()]


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
            st.caption(f"Consultas SAKBÉ del {fechas.min()} al {fechas.max()}.")


def resumen(locales: pd.DataFrame, municipios: pd.DataFrame, anios: list[int], centro: int, hospital: int) -> None:
    st.title(TITULO)
    st.markdown("Explora dónde coinciden los traslados largos a servicios de salud y las desventajas económicas y sociales.")
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
        c3.metric("Población con ruta al hospital medida", f"{100 * cobertura / poblacion:.2f} %" if poblacion else "Sin dato")
        st.caption(f"Umbrales de traslado · más de {centro} min al centro de salud o más de {hospital} min al hospital. Población evaluada: {evaluada:,} de {poblacion:,}.")
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
    deciles = leer(enigh.ruta_agregados(anio, "deciles_sonora"))
    if deciles.empty:
        return
    fila = deciles.iloc[0]
    a, b, c = st.columns(3)
    a.metric("Ingreso medio trimestral per cápita", pesos(fila.get("ing_pc_media_global", float("nan"))))
    b.metric("Ingreso mediano trimestral per cápita", pesos(fila.get("ing_pc_mediana_global", float("nan"))))
    gini = fila.get("gini_global", float("nan"))
    c.metric("Coeficiente de Gini", f"{gini:.3f}" if pd.notna(gini) else "Sin dato")
    st.caption(f"INEGI · ENIGH {anio} · pesos corrientes del levantamiento.")


def explorar_municipios(
    municipios: pd.DataFrame, locales: pd.DataFrame, anios: list[int], centro: int, hospital: int
) -> None:
    st.title("Explorador municipal")
    if municipios.empty:
        sin_salud()
        return
    m = municipios
    if anios:
        anio = st.selectbox("Levantamiento ENIGH para comparar", anios, index=len(anios) - 1)
        ingreso = leer(enigh.ruta_agregados(anio, "municipios_sonora"))
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
        "pct_marginacion_alta": "%", "ing_pc": "MXN/trimestre",
    }
    opciones = [c for c in indicadores if c in m and m[c].notna().any()]
    if opciones:
        campo = st.selectbox("Indicador del mapa", opciones, format_func=CAMPOS_MUNICIPIO.get)
        geo = cartografia_municipal()
        con_datos = m.dropna(subset=[campo])
        if geo:
            figura = mapas.mapa_municipios(con_datos, geo, columna=campo, columna_nombre="municipio",
                                          titulo=CAMPOS_MUNICIPIO[campo], unidad=indicadores[campo])
            st.plotly_chart(figura, use_container_width=True)
        elif {"latitude", "longitude"}.issubset(locales):
            puntos = locales.dropna(subset=["latitude", "longitude"]).sort_values("population", ascending=False)
            puntos = puntos.drop_duplicates("cvegeo")[["cvegeo", "latitude", "longitude"]].merge(con_datos, on="cvegeo")
            if not puntos.empty:
                figura = px.scatter_mapbox(puntos, lat="latitude", lon="longitude", color=campo,
                                           hover_name="municipio", zoom=4.8,
                                           color_continuous_scale=["#c1e6dc", "#087f73", "#144052"],
                                           labels=CAMPOS_MUNICIPIO, mapbox_style="carto-positron", height=495)
                figura.update_layout(margin=dict(l=0, r=0, t=0, b=0))
                st.plotly_chart(figura, use_container_width=True)
                st.caption("Cada marcador se ubica en la localidad con más habitantes del municipio.")
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


def explorar_localidades(locales: pd.DataFrame, centro: int, hospital: int) -> None:
    st.title("Localidades y acceso a la salud")
    if locales.empty:
        sin_salud()
        return
    a, b, c = st.columns(3)
    municipio = a.selectbox("Municipio", ["Todo Sonora", *sorted(locales["municipality_name"].dropna().unique())])
    filtro = b.selectbox("Mostrar", ["Acceso comprometido", "Doble barrera", "Todas"])
    nivel = c.selectbox("Tiempo en el mapa", ["Hospital", "Centro de salud"])
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
    campo = "secondary_time_min" if nivel == "Hospital" else "primary_time_min"
    if {"latitude", "longitude"}.issubset(t):
        st.plotly_chart(mapas.mapa_localidades(t, columna=campo, titulo=f"Traslado · {nivel.lower()}"), use_container_width=True)
    ordenadas = t.sort_values("population", ascending=False)
    tabla_publica(ordenadas, CAMPOS_LOCALIDAD, "localidades_sonora.csv")
    with st.expander("Ficha de una localidad"):
        fichas = ordenadas.set_index("locality_id")
        nombres = fichas.apply(lambda f: f"{f['locality_name']} · {f['municipality_name']} ({f.name})", axis=1)
        clave = st.selectbox("Buscar por localidad o clave", fichas.index, format_func=nombres.get)
        fila = fichas.loc[clave]
        establecimientos = leer(config.PROCESSED_DATA_DIR / "salud-001_establecimientos.parquet")
        unidades = {}
        if {"clues", "nombre_unidad"}.issubset(establecimientos):
            unidades = establecimientos.drop_duplicates("clues").set_index("clues")["nombre_unidad"].to_dict()
        for col, prefijo, titulo in zip(st.columns(2), ("primary", "secondary"), ("Centro de salud", "Hospital")):
            tiempo = fila[f"{prefijo}_time_min"]
            clues = fila.get(f"nearest_{prefijo}_clues")
            metodo = fila.get(f"{prefijo}_method")
            col.metric(titulo, f"{tiempo:.0f} min" if pd.notna(tiempo) else "Sin tiempo")
            if pd.notna(clues):
                col.write(unidades.get(clues, clues))
            if pd.notna(metodo):
                col.caption(f"Método · {metodo}")
    if filtro == "Todas" and "poblacion_sin_afiliacion" in t:
        grupos = analisis.grupos_vulnerables(t, umbral_primer=centro, umbral_segundo=hospital)
        if not grupos.empty:
            with st.expander("Brechas por grupo en la selección"):
                st.plotly_chart(mapas.barras_grupos_vulnerables(grupos), use_container_width=True)
                st.caption("La comparación usa la población con dato de cada grupo en la selección.")
    nota_rutas(t)


def ingreso_bienestar(anios: list[int]) -> None:
    st.title("Ingreso y bienestar")
    if not anios:
        sin_enigh()
        return
    anio = st.selectbox("Levantamiento", anios, index=len(anios) - 1)
    vista = st.radio("Análisis", ["Distribución", "Evolución", "Bienestar"], horizontal=True, key="analisis_enigh")
    if vista == "Distribución":
        partes = []
        for ambito, nombre in (("Sonora", "deciles_sonora"), ("México", "deciles_nacionales")):
            tabla = leer(enigh.ruta_agregados(anio, nombre))
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
        serie = leer(enigh.DIR_PROCESSED / "agregados" / "serie_deciles_sonora.parquet")
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
        desigualdad = leer(enigh.DIR_PROCESSED / "agregados" / "serie_desigualdad.parquet")
        if not desigualdad.empty:
            st.plotly_chart(px.line(desigualdad.sort_values("anio").assign(anio=lambda d: d["anio"].astype(str)),
                                    x="anio", y="gini", color="ambito", markers=True,
                                    color_discrete_sequence=PALETA,
                                    labels={"anio": "Levantamiento", "gini": "Coeficiente de Gini", "ambito": "Ámbito"}),
                            use_container_width=True)
        st.caption("Los puntos corresponden a levantamientos de ENIGH. 2020 fue un año atípico por la pandemia.")
    else:
        bienestar = leer(enigh.ruta_agregados(anio, "bienestar_sonora"))
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


def metodologia(locales: pd.DataFrame, anios: list[int]) -> None:
    st.title("Calidad y metodología")
    st.markdown("""
**Acceso.** Los tiempos describen el traslado en automóvil al establecimiento operativo seleccionado.
Entre los candidatos cercanos se conserva la ruta de menor tiempo. La cobertura distingue rutas SAKBÉ
de estimaciones, y la población con información incompleta queda visible en los denominadores.

**Contexto territorial.** ITER, RESLOC y CONAPO corresponden a 2020. Los resultados describen
localidades o agregados municipales. La marginación de una localidad caracteriza su contexto territorial.

**Ingreso.** ENIGH estima ingresos y bienestar para hogares, con factores de expansión.
Las comparaciones municipales son exploratorias. Las celdas por debajo del mínimo de hogares y las
que presentan baja precisión reportada se omiten del mapa, la tabla y la descarga.
Las series en pesos constantes usan el INPC de INEGI.
""")
    if not locales.empty:
        nota_rutas(locales)
        conteos = []
        for nivel, campo in (("Centro de salud", "primary_method"), ("Hospital", "secondary_method")):
            if campo in locales:
                por_metodo = locales.groupby(locales[campo].fillna("Sin dato"))["population"].agg(["size", "sum"])
                conteos.append(por_metodo.reset_index().set_axis(["Método", "Localidades", "Población"], axis=1).assign(Nivel=nivel))
        if conteos:
            st.subheader("Cobertura por método de traslado")
            st.dataframe(pd.concat(conteos, ignore_index=True), hide_index=True)
    st.subheader("Caché local SAKBÉ")
    ruta = config.INTERIM_DATA_DIR / "sakbe_cache.sqlite"
    if ruta.is_file():
        try:
            st.dataframe(auditar_cache(ruta, ruta.stat().st_mtime_ns), hide_index=True)
            st.caption("Los conteos corresponden a respuestas almacenadas de la API. Una localidad puede requerir varias consultas.")
        except (sqlite3.Error, pd.errors.DatabaseError, OSError):
            st.warning("El resumen del caché local no está disponible.")
    else:
        st.caption("Esta instalación sirve los resultados procesados.")
    st.subheader("Levantamientos ENIGH disponibles")
    st.write(", ".join(map(str, anios)) if anios else "Pendientes de procesar.")
    st.caption("Proyecto Salud Sonora y tablero ENIGH de Julio Waissman · Maestría en Ciencia de Datos, Universidad de Sonora.")


def main() -> None:
    st.set_page_config(page_title=TITULO, page_icon="📍", layout="wide")
    cfg = config.cargar_configuracion().umbrales
    with st.sidebar:
        st.header("Sonora")
        vista = st.radio("Navegación", VISTAS)
        centro, hospital = cfg.tiempo_critico_min, cfg.tiempo_critico_segundo_nivel_min
        if vista in ("Resumen", "Municipios", "Localidades"):
            with st.expander("Escenarios de traslado"):
                centro = st.slider("Centro de salud (min)", 15, 240, centro, 5)
                hospital = st.slider("Hospital (min)", 15, 360, hospital, 5)
    anios = anios_enigh()
    if vista == "Ingreso y bienestar":
        ingreso_bienestar(anios)
        return
    locales = leer(config.ARCHIVO_TABLA_FINAL)
    if not locales.empty:
        try:
            locales = territorio.preparar_localidades(
                locales,
                leer_contexto("conapo-marg-001_localidades.parquet", "grado_marginacion"),
                leer_contexto("inegi-resloc-001_localidades.parquet", "transporte_foraneo"),
                umbral_centro=centro, umbral_hospital=hospital,
            )
        except (KeyError, ValueError) as exc:
            st.warning(f"No fue posible validar la tabla de localidades. {exc}")
            locales = pd.DataFrame()
    municipios = territorio.resumir_municipios(locales) if not locales.empty else pd.DataFrame()
    if vista == "Resumen":
        resumen(locales, municipios, anios, centro, hospital)
    elif vista == "Municipios":
        explorar_municipios(municipios, locales, anios, centro, hospital)
    elif vista == "Localidades":
        explorar_localidades(locales, centro, hospital)
    else:
        metodologia(locales, anios)


if __name__ == "__main__":
    main()
