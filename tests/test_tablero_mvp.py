"""Arranque del tablero publicado sin consultar las fuentes originales."""

import json
import socket
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

RAIZ = Path(__file__).resolve().parents[1]


def _comprobar_mapa_local(tablero, tipo):
    graficos = [json.loads(el.proto.spec) for el in tablero.get("plotly_chart")]
    mapas = [fig for fig in graficos if any(traza["type"] == tipo for traza in fig["data"])]
    assert mapas, f"No se dibujó el mapa {tipo}"
    for figura in mapas:
        mapa = figura["layout"]["map"]
        assert mapa["style"]["sources"] == {}
        assert all(capa["type"] == "background" for capa in mapa["style"]["layers"])
        if tipo == "choroplethmap":
            assert any(t.get("geojson", {}).get("features") for t in figura["data"])
        else:
            assert mapa["layers"][0]["sourcetype"] == "geojson"
    return mapas[0]


def test_cinco_vistas_del_mvp_sin_red_ni_credenciales(monkeypatch):
    monkeypatch.delenv("SONORA_DATOS", raising=False)
    monkeypatch.delenv("SONORA_MAPA", raising=False)
    for nombre in ("SAKBE_TOKEN", "SAKBE_TOKENS", "CARTO_API_KEY"):
        monkeypatch.delenv(nombre, raising=False)

    intentos = []

    def bloquear(*args, **kwargs):
        intentos.append(True)
        raise OSError("El tablero debe leer solo los insumos versionados")

    monkeypatch.setattr(socket, "getaddrinfo", bloquear)
    monkeypatch.setattr(socket.socket, "connect", bloquear)
    monkeypatch.setattr(socket.socket, "connect_ex", bloquear)

    tablero = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=45).run()
    assert not tablero.exception
    assert any(m.label == "Personas con acceso comprometido" for m in tablero.metric)
    assert any("calculado por SAKBÉ" in m.label for m in tablero.metric)

    tablero.sidebar.radio[0].set_value("Municipios").run()
    assert not tablero.exception
    assert len(tablero.dataframe[0].value) == 72
    _comprobar_mapa_local(tablero, "choroplethmap")
    tablero.selectbox[1].set_value("doble_barrera").run()
    assert not tablero.exception
    assert "10.1%" in tablero.info[0].value
    doble = _comprobar_mapa_local(tablero, "choroplethmap")
    assert all("Cobertura:" in detalle for traza in doble["data"] for detalle in traza["hovertext"])
    tablero.selectbox[2].set_value("26001").run()
    assert not tablero.exception
    assert any("Cobertura:" in texto.value for texto in tablero.markdown)

    tablero.selectbox[1].set_value("ing_pc").run()
    assert not tablero.exception
    gris, valores = _comprobar_mapa_local(tablero, "choroplethmap")["data"]
    assert gris["showscale"] is False
    assert len(valores["locations"]) == 15
    assert len(set(gris["locations"] + valores["locations"])) == 72
    assert "Muestra insuficiente" in gris["hovertext"]

    tablero.sidebar.radio[0].set_value("Localidades").run()
    assert not tablero.exception
    assert not tablero.dataframe[0].value.empty
    _comprobar_mapa_local(tablero, "scattermap")
    tablero.selectbox[1].set_value("Todas").run()
    assert not tablero.exception
    assert any("5,000 de 7,297 localidades" in texto.value for texto in tablero.caption)
    salud = pd.read_parquet(RAIZ / "datos_mvp/salud/accesibilidad_localidades.parquet")
    fila = salud[salud["secondary_time_min"].lt(salud["primary_facility_time_min"])].iloc[0]
    tablero.selectbox[3].set_value(fila["locality_id"]).run()
    assert not tablero.exception
    assert tablero.metric[2].value == tablero.metric[3].value == f"{fila['secondary_time_min']:.0f} min"
    assert any("Se usó el tiempo al hospital" in texto.value for texto in tablero.caption)
    publicada = tablero.dataframe[0].value.set_index("Clave INEGI").loc[fila["locality_id"]]
    assert publicada["CLUES de referencia para atención básica"] == fila["nearest_secondary_clues"]
    assert publicada["Método · atención básica"] == fila["secondary_method"]
    base, seleccionada = _comprobar_mapa_local(tablero, "scattermap")["data"]
    assert len(base["lat"]) == 5000
    assert seleccionada["name"] == "Localidad seleccionada"
    assert seleccionada["lat"] == [fila["latitude"]]
    assert seleccionada["lon"] == [fila["longitude"]]

    tablero.sidebar.radio[0].set_value("Ingreso y bienestar").run()
    assert not tablero.exception
    assert {"2020", "2022", "2024"}.issubset(tablero.selectbox[0].options)
    for vista in ("Evolución", "Bienestar"):
        tablero.radio(key="analisis_enigh").set_value(vista).run()
        assert not tablero.exception
        assert tablero.get("plotly_chart")
        assert any(s.label == "Año de la encuesta" for s in tablero.selectbox) == (vista == "Bienestar")

    tablero.sidebar.radio[0].set_value("Calidad y metodología").run()
    assert not tablero.exception
    tablas = [elemento.value for elemento in tablero.dataframe]
    resumen = next(tabla for tabla in tablas if {"servicio", "respuestas"}.issubset(tabla))
    assert {"buscalinea", "optima"}.issubset(resumen["servicio"])
    assert resumen["respuestas"].sum() > 0
    assert not intentos
