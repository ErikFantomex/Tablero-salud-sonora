"""Arranque del tablero publicado sin consultar las fuentes originales."""

import json
import socket
from pathlib import Path

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

    tablero.sidebar.radio[0].set_value("Municipios").run()
    assert not tablero.exception
    assert len(tablero.dataframe[0].value) == 72
    _comprobar_mapa_local(tablero, "choroplethmap")

    tablero.sidebar.radio[0].set_value("Localidades").run()
    assert not tablero.exception
    assert not tablero.dataframe[0].value.empty
    _comprobar_mapa_local(tablero, "scattermap")

    tablero.sidebar.radio[0].set_value("Ingreso y bienestar").run()
    assert not tablero.exception
    assert {"2020", "2022", "2024"}.issubset(tablero.selectbox[0].options)
    for vista in ("Evolución", "Bienestar"):
        tablero.radio(key="analisis_enigh").set_value(vista).run()
        assert not tablero.exception
        assert tablero.get("plotly_chart")

    tablero.sidebar.radio[0].set_value("Calidad y metodología").run()
    assert not tablero.exception
    tablas = [elemento.value for elemento in tablero.dataframe]
    resumen = next(tabla for tabla in tablas if {"servicio", "respuestas"}.issubset(tabla))
    assert {"buscalinea", "optima"}.issubset(resumen["servicio"])
    assert resumen["respuestas"].sum() > 0
    assert not intentos
