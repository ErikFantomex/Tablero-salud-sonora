"""Prepara y verifica la copia pública del tablero a partir de los productos locales."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd

from health_data import config, territorio
from health_data.ingestion.sakbe import ARCHIVO_CACHE

RAIZ = config.PROJECT_ROOT
DESTINO = RAIZ / "datos_mvp"
ESQUEMA = 1
ANIOS_MVP = (2020, 2022, 2024)

SALUD = {
    "accesibilidad_localidades.parquet": (
        (
            "locality_id", "locality_name", "municipality_name", "population",
            "latitude", "longitude", "nearest_primary_clues", "primary_time_min", "primary_method",
            "nearest_secondary_clues", "secondary_time_min", "secondary_method",
            "routing_status", "routing_consulted_at", "disponibilidad", "pct_viviendas_sin_auto_ni_moto",
            "poblacion_60_y_mas", "pct_60_y_mas", "poblacion_con_discapacidad", "pct_con_discapacidad",
            "poblacion_sin_afiliacion", "pct_sin_afiliacion", "poblacion_lengua_indigena", "pct_lengua_indigena",
        ),
        ("INEGI-POP-001", "SALUD-001", "INEGI-ROUTE-001", "CONEVAL-ACC-001"),
    ),
    "conapo-marg-001_localidades.parquet": (("cvegeo", "grado_marginacion"), ("CONAPO-MARG-001",)),
    "inegi-resloc-001_localidades.parquet": (("cvegeo", "transporte_foraneo"), ("INEGI-RESLOC-001",)),
    "salud-001_establecimientos.parquet": (("clues", "nombre_unidad"), ("SALUD-001",)),
}
AGREGADOS_ENIGH = ("bienestar_sonora", "deciles_nacionales", "deciles_sonora", "municipios_sonora")
SERIES_ENIGH = ("serie_deciles_sonora", "serie_desigualdad")
ESTIMACION_MUNICIPAL = ("ing_pc", "ing_pc_ic_inferior", "ing_pc_ic_superior", "ing_pc_cv")


def huella(ruta: Path) -> str:
    with ruta.open("rb") as archivo:
        return hashlib.file_digest(archivo, "sha256").hexdigest()


def leer_json(ruta: Path):
    return json.loads(ruta.read_text(encoding="utf-8"))


def escribir_json(ruta: Path, datos) -> None:
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8", newline="\n")


def inventario() -> dict[str, tuple[str, ...]]:
    return {
        **{f"salud/{nombre}": fuentes for nombre, (_, fuentes) in SALUD.items()},
        "salud/sakbe_resumen.json": ("INEGI-ROUTE-001",),
        "enigh/manifiesto.json": ("INEGI-ENIGH",),
        "enigh/geografia/sonora_municipios.geojson": ("INEGI-GEO-001",),
        **{f"enigh/agregados/{nombre}.parquet": ("INEGI-ENIGH",) for nombre in SERIES_ENIGH},
        **{
            f"enigh/agregados/ano={anio}/{nombre}.parquet": ("INEGI-ENIGH",)
            for anio in ANIOS_MVP for nombre in AGREGADOS_ENIGH
        },
    }


def exportar_municipios(origen: Path, ruta: Path, minimo: int) -> None:
    tabla = pd.read_parquet(origen)
    estimaciones = [c for c in ESTIMACION_MUNICIPAL if c in tabla]
    obligatorias = ["clave_cvegeo", "n_hogares", "n_upm", "fiable"]
    calidad = ["ing_pc_fiable"] if "ing_pc_fiable" in tabla else []
    tabla = tabla[obligatorias + calidad + estimaciones].copy()
    publicar = tabla["n_hogares"].ge(minimo) & tabla["fiable"].eq(True)
    if calidad:
        publicar &= ~tabla["ing_pc_fiable"].eq(False).fillna(False)
    # El archivo público aplica la supresión de la vista también a la descarga directa.
    tabla.loc[~publicar.fillna(False), estimaciones] = None
    tabla.to_parquet(ruta, index=False)


def fuentes_publicas(enigh_cfg, geo, auditoria: pd.DataFrame) -> dict:
    salud_cfg = config.cargar_configuracion()
    with (RAIZ / "catalog" / "ingestions.csv").open(encoding="utf-8-sig", newline="") as archivo:
        descargas = {
            (fila["dataset_id"], Path(fila["raw_path"]).name): fila
            for fila in sorted(csv.DictReader(archivo), key=lambda item: item["retrieved_at"])
            if fila["status"] == "ok"
        }
    fuentes = {}
    for clave in ("INEGI-POP-001", "SALUD-001", "CONEVAL-ACC-001", "INEGI-RESLOC-001", "CONAPO-MARG-001"):
        fuente = salud_cfg.fuente(clave)
        descarga = descargas.get((clave, fuente.nombre_archivo), {})
        fuentes[clave] = {
            "institucion": fuente.institucion,
            "producto": fuente.nombre,
            "url": fuente.url,
            "archivo_origen": fuente.nombre_archivo,
            "descargado_en": descarga.get("retrieved_at"),
        }
    fuentes["CONEVAL-ACC-001"]["licencia"] = "CC BY-NC 2.5 MX"
    fuentes["INEGI-ROUTE-001"] = {
        "institucion": "INEGI",
        "producto": "SAKBÉ Sistema de Ruteo de México, API versión 3.1",
        "url": salud_cfg.fuente("INEGI-ROUTE-001").api_base,
        "condiciones": "https://antares.inegi.org.mx/analisis/red_hidro/PDF/SAKBE_Interfaz_de_Programacion_de_Aplicaciones_para_Ruteo.pdf",
        "consultas_desde": auditoria["primera_consulta"].min(),
        "consultas_hasta": auditoria["ultima_consulta"].max(),
    }
    fuentes["INEGI-GEO-001"] = {
        "institucion": "INEGI",
        "producto": "Marco Geoestadístico, municipios de Sonora",
        "url": "https://www.inegi.org.mx/temas/mg/",
        "url_copia": geo.URL_MUNICIPIOS_SONORA,
        "sha256_copia": geo.SHA256_MUNICIPIOS_SONORA,
    }
    fuentes["INEGI-ENIGH"] = {
        "institucion": "INEGI",
        "producto": "Encuesta Nacional de Ingresos y Gastos de los Hogares",
        "levantamientos": {str(anio): enigh_cfg.fuente(anio).url for anio in ANIOS_MVP},
        "transformacion": "Agregados estadísticos del proyecto ENIGH Sonora",
    }
    return fuentes


def preparar_copia(directorio: Path, version: str) -> None:
    # ENIGH conserva sus rutas de procesamiento en su propio proyecto.
    sys.path.insert(0, str(RAIZ / "enigh-sonora-main"))
    try:
        from enigh import config as enigh
        from enigh import geografia as geo
    finally:
        sys.path.pop(0)

    enigh_cfg = enigh.cargar_configuracion()
    manifiesto_enigh = leer_json(enigh.ARCHIVO_MANIFIESTO)
    argumentos = manifiesto_enigh["argumentos"]
    anios = {entrada["anio"]: entrada for entrada in manifiesto_enigh["anios"]}
    if argumentos.get("muestra") is not None or not set(ANIOS_MVP).issubset(anios):
        raise ValueError("Genera los tres levantamientos ENIGH sin modo demostración.")
    manifiesto_publico_enigh = {
        "version_proyecto": manifiesto_enigh["version_proyecto"],
        "generado_en": manifiesto_enigh["generado_en"],
        "argumentos": {"muestra": None, "sin_bootstrap": argumentos["sin_bootstrap"]},
        "anios": [
            {campo: anios[anio][campo] for campo in ("anio", "hogares_en_muestra", "hogares_sonora_muestra")}
            for anio in ANIOS_MVP
        ],
    }

    auditoria = territorio.auditar_cache(ARCHIVO_CACHE)
    if auditoria.empty:
        raise ValueError("El caché de ruteo no contiene respuestas para resumir.")
    archivos = {}
    for relativa, fuentes in inventario().items():
        ruta = directorio / relativa
        ruta.parent.mkdir(parents=True, exist_ok=True)
        if ruta.name == "sakbe_resumen.json":
            origen = ARCHIVO_CACHE
            escribir_json(ruta, auditoria.to_dict(orient="records"))
        elif relativa.startswith("salud/"):
            origen = config.PROCESSED_DATA_DIR / ruta.name
            columnas, _ = SALUD[ruta.name]
            pd.read_parquet(origen, columns=list(columnas)).to_parquet(ruta, index=False)
        else:
            origen = enigh.DIR_PROCESSED / relativa.removeprefix("enigh/")
            if ruta.name == "manifiesto.json":
                escribir_json(ruta, manifiesto_publico_enigh)
            elif ruta.name == "municipios_sonora.parquet":
                exportar_municipios(origen, ruta, enigh_cfg.umbrales.hogares_min_municipio)
            else:
                if ruta.suffix == ".geojson" and huella(origen) != geo.SHA256_MUNICIPIOS_SONORA:
                    raise ValueError("La cartografía municipal no coincide con la copia documentada en ENIGH.")
                shutil.copyfile(origen, ruta)
        archivos[relativa] = {
            "bytes": ruta.stat().st_size, "sha256": huella(ruta),
            "fuentes": fuentes, "origen": origen.relative_to(RAIZ).as_posix(),
        }

    escribir_json(directorio / "manifest.json", {
        "schema_version": ESQUEMA,
        "version": version,
        "generado_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "archivos": archivos,
        "fuentes": fuentes_publicas(enigh_cfg, geo, auditoria),
    })


def verificar(directorio: Path = DESTINO) -> None:
    manifiesto = leer_json(directorio / "manifest.json")
    if manifiesto["schema_version"] != ESQUEMA:
        raise ValueError("Versión de esquema de datos MVP incompatible.")
    archivos = manifiesto["archivos"]
    esperados = set(inventario())
    presentes = {p.relative_to(directorio).as_posix() for p in directorio.rglob("*") if p.is_file()}
    if set(archivos) != esperados or presentes != esperados | {"manifest.json"}:
        raise ValueError("El inventario de datos MVP no coincide con los archivos requeridos.")
    for nombre, registro in archivos.items():
        ruta = directorio / nombre
        if ruta.stat().st_size != registro["bytes"] or huella(ruta) != registro["sha256"]:
            raise ValueError(f"No coincide la suma de verificación: {nombre}")


def generar(version: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", version):
        raise ValueError("Indica una versión de hasta 64 caracteres, por ejemplo 0.1.0.")
    respaldo = RAIZ / ".datos_mvp-anterior"
    candado = RAIZ / ".datos_mvp-lock"
    # Impide que dos procesos de publicación sustituyan la versión a la vez.
    candado.touch(exist_ok=False)
    try:
        if respaldo.exists() or respaldo.is_symlink():
            raise ValueError(f"Recupera o conserva la copia pendiente en {respaldo} antes de regenerar.")
        if DESTINO.is_symlink() or DESTINO.resolve().parent != RAIZ:
            raise ValueError("La carpeta de datos MVP debe estar dentro de la raíz del proyecto.")
        # Hereda los permisos del proyecto incluso después de renombrar la carpeta.
        copia = RAIZ / f".datos_mvp-preparar-{uuid4().hex}"
        copia.mkdir()
        try:
            preparar_copia(copia, version)
            verificar(copia)
            if DESTINO.exists():
                DESTINO.rename(respaldo)
            try:
                copia.rename(DESTINO)
            except BaseException:
                if respaldo.exists() and not DESTINO.exists():
                    respaldo.rename(DESTINO)
                raise
            if respaldo.is_dir() and respaldo.resolve().parent == RAIZ:
                shutil.rmtree(respaldo)
        finally:
            if copia.is_dir() and copia.resolve().parent == RAIZ:
                shutil.rmtree(copia)
    finally:
        candado.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    accion = parser.add_mutually_exclusive_group(required=True)
    accion.add_argument("--version", metavar="VERSIÓN", help="Prepara una copia con esta versión.")
    accion.add_argument("--verificar", action="store_true", help="Verifica el inventario y los archivos existentes.")
    args = parser.parse_args()
    try:
        if args.verificar:
            verificar()
        else:
            generar(args.version)
    except (KeyError, ValueError, OSError) as exc:
        parser.exit(1, f"Error de datos MVP: {exc}\n")
    print(f"Datos MVP verificados en {DESTINO.relative_to(RAIZ)}.")


if __name__ == "__main__":
    main()
