"""Validación de tablas territoriales y comparación de cortes del MVP."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

TABLA_SALUD = "salud/accesibilidad_localidades.parquet"
TABLAS_CONTEXTO = {
    "RESLOC": "salud/inegi-resloc-001_localidades.parquet",
    "CONAPO": "salud/conapo-marg-001_localidades.parquet",
}
NIVELES = {"Unidad de primer nivel": "primary_method", "Hospital": "secondary_method"}
COLUMNAS_SALUD = {
    "locality_id", "locality_name", "municipality_name", "population", "primary_time_min",
    "secondary_time_min", *NIVELES.values(),
}
CLAVES_ENIGH = {
    "deciles_sonora": (["decil"], {"ing_pc", "gini_global", "ing_pc_media_global", "ing_pc_mediana_global"}),
    "deciles_nacionales": (["decil"], {"ing_pc"}),
    "bienestar_sonora": (["indicador", "grupo"], {"dominio", "etiqueta", "unidad", "valor"}),
    "municipios_sonora": (["clave_cvegeo"], {"ing_pc", "n_hogares", "n_upm", "fiable"}),
    "serie_deciles_sonora": (["decil", "anio"], {"ing_pc"}),
    "serie_desigualdad": (["anio", "ambito"], {"gini"}),
}


def leer_claves(ruta: Path, campo: str, requeridas: set[str]) -> pd.DataFrame:
    tabla = pd.read_parquet(ruta)
    faltantes = requeridas - set(tabla)
    if faltantes:
        raise ValueError(f"{ruta.name}: faltan columnas obligatorias: {', '.join(sorted(faltantes))}.")
    claves = tabla[campo].astype("string")
    if not claves.str.fullmatch(r"26\d{7}", na=False).all():
        raise ValueError(f"{ruta.name}: hay claves inválidas en {campo}.")
    if claves.duplicated().any():
        raise ValueError(f"{ruta.name}: hay claves duplicadas en {campo}.")
    return tabla.assign(**{campo: claves})


def leer_salud(directorio: Path) -> pd.DataFrame:
    tabla = leer_claves(directorio / TABLA_SALUD, "locality_id", COLUMNAS_SALUD)
    for campo in ("primary_time_min", "secondary_time_min", "primary_facility_time_min", "population"):
        if campo in tabla:
            valores = pd.to_numeric(tabla[campo], errors="coerce")
            invalidos = (tabla[campo].notna() & ~np.isfinite(valores)) | valores.lt(0)
            if invalidos.any() or (campo == "population" and valores.isna().any()):
                raise ValueError(f"{TABLA_SALUD}: {campo} contiene valores negativos o inválidos.")
            tabla[campo] = valores
    return tabla


def cruces(directorio: Path, localidades: set[str]) -> dict[str, tuple[int, int]]:
    resultados = {}
    for nombre, ruta in TABLAS_CONTEXTO.items():
        campo = "transporte_foraneo" if nombre == "RESLOC" else "grado_marginacion"
        claves = set(leer_claves(directorio / ruta, "cvegeo", {"cvegeo", campo})["cvegeo"])
        resultados[nombre] = (len(localidades - claves), len(claves - localidades))
    municipios = {clave[:5] for clave in localidades}
    for ruta in sorted((directorio / "enigh/agregados").glob("ano=*/municipios_sonora.parquet")):
        claves = set(pd.read_parquet(ruta, columns=["clave_cvegeo"])["clave_cvegeo"].astype("string").dropna())
        resultados[f"ENIGH municipal {ruta.parent.name.removeprefix('ano=')}"] = (
            len(municipios - claves), len(claves - municipios),
        )
    return resultados


def validar_enigh(directorio: Path) -> None:
    for ruta in sorted((directorio / "enigh/agregados").rglob("*.parquet")):
        claves, campos = CLAVES_ENIGH[ruta.stem]
        tabla = pd.read_parquet(ruta)
        faltantes = (set(claves) | campos) - set(tabla)
        if faltantes:
            raise ValueError(f"{ruta.name}: faltan columnas obligatorias: {', '.join(sorted(faltantes))}.")
        if tabla[claves].isna().any().any() or tabla.duplicated(claves).any():
            raise ValueError(f"{ruta.name}: hay claves vacías o duplicadas en {', '.join(claves)}.")


def cobertura(tabla: pd.DataFrame) -> dict[tuple[str, str], tuple[int, int, float]]:
    resultados = {}
    poblacion = tabla["population"].sum()
    for nivel, columna in NIVELES.items():
        campo_tiempo = "secondary_time_min" if columna == "secondary_method" else "primary_facility_time_min"
        if campo_tiempo not in tabla:
            campo_tiempo = "primary_time_min"
        metodo = tabla[columna].where(tabla[campo_tiempo].notna()).fillna("Sin dato")
        for categoria, filas in tabla.groupby(metodo):
            personas = int(filas["population"].sum())
            resultados[nivel, categoria] = (len(filas), personas, 100 * personas / poblacion if poblacion else 0)
    return resultados


def comparar(anterior: Path, candidato: Path) -> str:
    cortes = [json.loads((ruta / "manifest.json").read_text(encoding="utf-8")) for ruta in (anterior, candidato)]
    base, nuevo = cortes
    salud_base, salud_nueva = leer_salud(anterior), leer_salud(candidato)
    claves_base, claves_nuevas = set(salud_base["locality_id"]), set(salud_nueva["locality_id"])
    cruces_base, cruces_nuevos = cruces(anterior, claves_base), cruces(candidato, claves_nuevas)
    metodos_base, metodos_nuevos = cobertura(salud_base), cobertura(salud_nueva)
    salida = [
        "# Comparación de datos MVP", "",
        f"Publicado: **{base['version']}** ({base['generado_en']}). "
        f"Candidato: **{nuevo['version']}** ({nuevo['generado_en']}).", "",
        "## Fuentes y archivos", "",
    ]
    fuentes = sorted(k for k in base["fuentes"].keys() | nuevo["fuentes"].keys()
                     if base["fuentes"].get(k) != nuevo["fuentes"].get(k))
    salida += ["Fuentes con metadatos modificados: " + (", ".join(fuentes) if fuentes else "ninguna") + ".", ""]
    for nombre in sorted(base["archivos"].keys() | nuevo["archivos"].keys()):
        previo, actual = base["archivos"].get(nombre), nuevo["archivos"].get(nombre)
        if (previo or {}).get("sha256") != (actual or {}).get("sha256"):
            estado = "añadido" if previo is None else "retirado" if actual is None else "modificado"
            salida.append(f"- `{nombre}` ({estado}) · {', '.join((actual or previo)['fuentes'])}")
    if salida[-1] == "":
        salida.append("Los archivos tienen las mismas sumas SHA-256.")
    salida += ["", "## Localidades", "",
               f"Total: {len(claves_base):,} → {len(claves_nuevas):,}.", ""]
    for etiqueta, claves in (("Añadidas", claves_nuevas - claves_base), ("Retiradas", claves_base - claves_nuevas)):
        salida.append(f"- {etiqueta}: {len(claves):,}" + (f" · {', '.join(sorted(claves))}" if claves else ""))
    salida += [
        "", "## Claves sin correspondencia", "",
        "RESLOC y CONAPO se comparan por localidad. ENIGH se compara por municipio. Un municipio sin fila ENIGH puede no tener muestra.",
        "",
        "| Fuente | Claves de salud sin cruce (publicado → candidato) | Claves externas sin fila en salud (publicado → candidato) |",
        "|---|---:|---:|",
    ]
    for fuente, (sin_cruce, sin_salud) in cruces_nuevos.items():
        previo_cruce, previo_salud = cruces_base.get(fuente, (0, 0))
        salida.append(f"| {fuente} | {previo_cruce:,} → {sin_cruce:,} | {previo_salud:,} → {sin_salud:,} |")
    salida += [
        "", "## Cobertura de ruteo", "",
        "| Nivel | Método | Localidades (publicado → candidato) | Personas (publicado → candidato) | % de población (publicado → candidato) |",
        "|---|---|---:|---:|---:|",
    ]
    alertas = []
    for nivel, metodo in sorted(metodos_base.keys() | metodos_nuevos.keys()):
        a, p, antes = metodos_base.get((nivel, metodo), (0, 0, 0))
        b, q, despues = metodos_nuevos.get((nivel, metodo), (0, 0, 0))
        salida.append(f"| {nivel} | {metodo} | {a:,} → {b:,} | {p:,} → {q:,} | {antes:.2f} % → {despues:.2f} % |")
        if metodo == "sakbe" and (despues < antes or q < p or b < a):
            alertas.append(f"Revisar la caída en cobertura SAKBÉ para {nivel.lower()}.")
        if metodo == "Sin dato" and (despues > antes or q > p or b > a):
            alertas.append(f"Revisar el aumento de localidades o personas sin tiempo de traslado para {nivel.lower()}.")
    for fuente, (sin_cruce, _) in cruces_nuevos.items():
        previo = cruces_base.get(fuente, (0, 0))[0]
        if sin_cruce > previo:
            alertas.append(f"Revisar el aumento de claves sin cruce con {fuente}.")
    salida += ["", "## Alertas para revisión", ""]
    salida += [f"- {alerta}" for alerta in alertas] or ["No se detectaron caídas en la cobertura de tiempos, SAKBÉ ni cruces territoriales."]
    return "\n".join(salida) + "\n"
