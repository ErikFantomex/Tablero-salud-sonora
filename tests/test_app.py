"""Pruebas del tablero integrado con insumos locales y sin red."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import health_data.config as config

APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture
def fuentes(tmp_path, monkeypatch):
    monkeypatch.setenv("SONORA_DATOS", "local")
    monkeypatch.syspath_prepend(str(APP.parent / "enigh-sonora-main"))
    from enigh import config as enigh

    salud = tmp_path / "salud"
    salud.mkdir()
    monkeypatch.setattr(config, "ARCHIVO_TABLA_FINAL", salud / "accesibilidad.parquet")
    monkeypatch.setattr(config, "PROCESSED_DATA_DIR", salud)
    monkeypatch.setattr(config, "INTERIM_DATA_DIR", tmp_path / "interim")
    monkeypatch.setattr(enigh, "DIR_PROCESSED", tmp_path / "enigh")
    monkeypatch.setattr(enigh, "ARCHIVO_MANIFIESTO", tmp_path / "enigh" / "manifiesto.json")
    return enigh


def guardar_salud():
    pd.DataFrame({
        "locality_id": ["260010001", "260010002", "260020001", "260050001"],
        "locality_name": ["Ciudad", "Rancho", "Sierra", "Ejido"],
        "municipality_name": ["A", "A", "B", "C"],
        "population": [1000, 50, 200, 100],
        "latitude": [29.0, 29.2, 28.5, 28.6],
        "longitude": [-110.9, -110.5, -109.0, -109.2],
        "primary_time_min": [5.0, 70.0, 20.0, 10.0],
        "primary_method": ["sakbe", "estimado", "sakbe", "sakbe"],
        "secondary_time_min": [10.0, 90.0, 200.0, np.nan],
        "secondary_method": ["sakbe", "estimado", "sakbe", None],
        "routing_status": ["ok", "estimado", "ok", "parcial"],
    }).to_parquet(config.ARCHIVO_TABLA_FINAL)
    pd.DataFrame({
        "cvegeo": ["260010002", "260020001"], "transporte_foraneo": ["NO", "NO"],
    }).to_parquet(config.PROCESSED_DATA_DIR / "inegi-resloc-001_localidades.parquet")


def guardar_enigh(enigh):
    d = pd.DataFrame({
        "decil": [1, 2], "ing_pc": [1000.0, 3000.0], "n_hogares": [40, 50],
        "ing_pc_media_global": [2500.0, 2500.0], "ing_pc_mediana_global": [2200.0, 2200.0],
        "gini_global": [0.4, 0.4],
    })
    for anio in [2022, 2024]:
        ruta = enigh.ruta_agregados(anio, "deciles_sonora")
        ruta.parent.mkdir(parents=True)
        d.to_parquet(ruta)
    d.to_parquet(enigh.ruta_agregados(2024, "deciles_nacionales"))
    pd.DataFrame({
        "clave_cvegeo": ["260020", "26002", "26001", "26005"],
        "nom_municipio": ["Otro", "Nombre diferente", "A", "C"],
        "ing_pc": [1.0, 3000.0, 999999.0, 888888.0], "n_hogares": [100, 65, 12, 65],
        "n_upm": [30, 20, 4, 5], "fiable": [True, True, False, True],
        "ing_pc_fiable": [True, True, True, False],
        "ing_pc_ic_inferior": [0.5, 2700.0, 999998.0, 888887.0],
    }).to_parquet(enigh.ruta_agregados(2024, "municipios_sonora"))
    pd.DataFrame({
        "grupo": [1, 2], "etiqueta": ["Internet", "Internet"], "unidad": ["proporción"] * 2,
        "dominio": ["Vivienda"] * 2, "valor": [.2, .4],
    }).to_parquet(enigh.ruta_agregados(2024, "bienestar_sonora"))
    pd.concat([d.assign(anio=a) for a in [2022, 2024]]).to_parquet(
        enigh.DIR_PROCESSED / "agregados" / "serie_deciles_sonora.parquet"
    )


def iniciar():
    return AppTest.from_file(str(APP), default_timeout=45).run()


def navegar(at, vista):
    return at.sidebar.radio[0].set_value(vista).run()


def test_resumen_cambia_con_umbral_y_excluye_poblacion_sin_tiempo(fuentes):
    guardar_salud()
    at = iniciar()
    assert not at.exception
    assert at.metric[0].value == "250"
    assert at.metric[0].delta == "20.00 % de la población evaluada"
    at.sidebar.slider[1].set_value(75).run()
    assert not at.exception
    assert at.metric[0].value == "250"
    navegar(at, "Localidades")
    at.selectbox[1].set_value("Doble barrera").run()
    assert not at.exception
    assert at.metric[1].value == "250"


def test_cruce_municipal_suprime_ingreso_frágil(fuentes):
    guardar_salud()
    guardar_enigh(fuentes)
    at = navegar(iniciar(), "Municipios")
    assert not at.exception
    tabla = at.dataframe[0].value.set_index("Clave INEGI")
    assert tabla.loc["26002", "Ingreso trimestral per cápita"] == 3000
    assert tabla.loc["26001", "Calidad ENIGH"] == "Muestra insuficiente"
    assert tabla.loc["26005", "Calidad ENIGH"] == "Precisión insuficiente"
    assert pd.isna(tabla.loc["26001", "Ingreso trimestral per cápita"])
    assert pd.isna(tabla.loc["26001", "Límite inferior IC 95 %"])
    assert pd.isna(tabla.loc["26005", "Ingreso trimestral per cápita"])


def test_enigh_disponible_aunque_falte_salud(fuentes):
    guardar_enigh(fuentes)
    at = navegar(iniciar(), "Ingreso y bienestar")
    assert not at.exception
    assert len(at.dataframe[0].value) == 4
    at.radio(key="analisis_enigh").set_value("Evolución").run()
    assert not at.exception
    assert at.get("plotly_chart")
    at.radio(key="analisis_enigh").set_value("Bienestar").run()
    assert not at.exception
    assert list(at.dataframe[0].value["Estimación"]) == [.2, .4]


def test_sin_fuentes_y_metodologia(fuentes):
    at = iniciar()
    assert not at.exception
    assert len(at.info) == 2
    navegar(at, "Calidad y metodología")
    assert not at.exception
    assert at.title[0].value == "Calidad y metodología"
