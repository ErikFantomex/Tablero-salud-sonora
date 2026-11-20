import shutil
from pathlib import Path

import pandas as pd
import pytest

from health_data import publicar_mvp
from health_data.comparar_mvp import TABLA_SALUD


@pytest.fixture
def cortes_mvp(tmp_path, monkeypatch):
    publicada = tmp_path / "datos_mvp"
    shutil.copytree(Path(__file__).resolve().parents[1] / "datos_mvp", publicada)
    monkeypatch.setattr(publicar_mvp, "RAIZ", tmp_path)
    monkeypatch.setattr(publicar_mvp, "DESTINO", publicada)
    return publicada


def preparar_candidato(publicada, carpeta, version, transformar):
    shutil.copytree(publicada, carpeta, dirs_exist_ok=True)
    manifiesto = publicar_mvp.leer_json(carpeta / "manifest.json")
    manifiesto["version"] = version
    ruta = carpeta / TABLA_SALUD
    transformar(pd.read_parquet(ruta)).to_parquet(ruta, index=False)
    manifiesto["archivos"][TABLA_SALUD].update(bytes=ruta.stat().st_size, sha256=publicar_mvp.huella(ruta))
    publicar_mvp.escribir_json(carpeta / "manifest.json", manifiesto)


def test_previa_compara_y_deja_la_version_publicada(cortes_mvp, monkeypatch, tmp_path):
    def quitar_ruta(tabla):
        indice = tabla[tabla["secondary_method"].eq("sakbe") & tabla["population"].gt(0)].index[0]
        tabla.loc[indice, "secondary_method"] = "estimado"
        return tabla

    monkeypatch.setattr(publicar_mvp, "preparar_copia",
                        lambda carpeta, version: preparar_candidato(cortes_mvp, carpeta, version, quitar_ruta))
    ruta = tmp_path / "comparacion.md"
    previo = publicar_mvp.huella(cortes_mvp / "manifest.json")
    publicar_mvp.generar("candidato", solo_reporte=True, reporte=ruta)
    informe = ruta.read_text(encoding="utf-8")
    assert "Revisar la caída en cobertura SAKBÉ para hospital" in informe
    assert "Claves sin correspondencia" in informe
    assert publicar_mvp.huella(cortes_mvp / "manifest.json") == previo


@pytest.mark.parametrize(("transformar", "error"), [
    (lambda t: pd.concat([t, t.iloc[:1]], ignore_index=True), "duplicadas"),
    (lambda t: t.drop(columns="secondary_time_min"), "columnas obligatorias"),
    (lambda t: t.assign(secondary_time_min=-1), "negativos"),
])
def test_datos_invalidos_bloquean_publicacion(cortes_mvp, monkeypatch, tmp_path, transformar, error):
    monkeypatch.setattr(publicar_mvp, "preparar_copia",
                        lambda carpeta, version: preparar_candidato(cortes_mvp, carpeta, version, transformar))
    previo = publicar_mvp.huella(cortes_mvp / "manifest.json")
    with pytest.raises(ValueError, match=error):
        publicar_mvp.generar("candidato", reporte=tmp_path / "comparacion.md")
    assert publicar_mvp.huella(cortes_mvp / "manifest.json") == previo
