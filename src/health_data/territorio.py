"""Indicadores territoriales del tablero integrado."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd

from health_data import analisis

SALUD_REQUERIDA = {
    "locality_id", "locality_name", "municipality_name", "population",
    "primary_time_min", "secondary_time_min",
}


def auditar_cache(ruta: Path) -> pd.DataFrame:
    """Consulta solo los conteos operativos, sin exponer parámetros ni tokens."""
    with closing(sqlite3.connect(ruta.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        return pd.read_sql_query(
            """SELECT endpoint AS servicio, count(*) AS respuestas,
                      sum(exito) AS exitosas, min(consultado_en) AS primera_consulta,
                      max(consultado_en) AS ultima_consulta
                 FROM respuestas GROUP BY endpoint ORDER BY endpoint""",
            db,
        )


def preparar_localidades(
    salud: pd.DataFrame, marginacion: pd.DataFrame, transporte: pd.DataFrame,
    *, umbral_centro: int, umbral_hospital: int,
) -> pd.DataFrame:
    """Añade contexto censal sin perder localidades con fuentes incompletas."""
    faltantes = SALUD_REQUERIDA - set(salud.columns)
    if faltantes:
        raise ValueError(f"Faltan columnas de salud: {', '.join(sorted(faltantes))}")
    t = analisis.preparar_tabla(salud)
    if not t["population"].between(0, float("inf"), inclusive="left").all():
        raise ValueError("La población debe ser finita y no negativa.")
    for campo in ("primary_time_min", "secondary_time_min", "primary_facility_time_min"):
        if campo in t:
            tiempo = pd.to_numeric(t[campo], errors="coerce")
            t[campo] = tiempo.where(tiempo.between(0, float("inf"), inclusive="left"))
    hospital = t["secondary_time_min"]
    basica = t["primary_time_min"]
    if "primary_facility_time_min" in t:
        centro = t["primary_facility_time_min"]
        usar_hospital = basica.notna() & hospital.lt(centro)
        usar_centro = basica.notna() & centro.le(hospital)
    else:
        # En las tablas anteriores solo se guardaba el mínimo. Un empate no
        # permite identificar qué destino aportó el tiempo.
        usar_centro = basica.notna() & (hospital.isna() | basica.lt(hospital))
        usar_hospital = pd.Series(False, index=t.index)
    for nombre, campo_centro, campo_hospital in (
        ("basic_clues", "nearest_primary_clues", "nearest_secondary_clues"),
        ("basic_method", "primary_method", "secondary_method"),
    ):
        valores = pd.Series(pd.NA, index=t.index, dtype="string")
        if campo_centro in t:
            valores.loc[usar_centro] = t.loc[usar_centro, campo_centro].astype("string")
        if campo_hospital in t:
            valores.loc[usar_hospital] = t.loc[usar_hospital, campo_hospital].astype("string")
        t[nombre] = valores
    t["basic_destination"] = pd.Series(pd.NA, index=t.index, dtype="string")
    t.loc[usar_centro, "basic_destination"] = "Unidad de primer nivel"
    t.loc[usar_hospital, "basic_destination"] = "Hospital"
    t["locality_id"] = t["locality_id"].astype("string")
    if not t["locality_id"].str.fullmatch(r"26\d{7}", na=False).all() or t["locality_id"].duplicated().any():
        raise ValueError("La tabla de salud debe contener claves únicas de localidades de Sonora.")
    t["cvegeo"] = t["locality_id"].str[:5]
    for origen, campo in ((marginacion, "grado_marginacion"), (transporte, "transporte_foraneo")):
        if not origen.empty:
            contexto = origen[["cvegeo", campo]].copy()
            contexto["cvegeo"] = contexto["cvegeo"].astype("string")
            t = t.merge(contexto, left_on="locality_id", right_on="cvegeo", how="left",
                        suffixes=("", "_localidad"), validate="one_to_one").drop(columns="cvegeo_localidad")
        else:
            t[campo] = pd.NA
        t[campo] = t[campo].astype("string").str.strip().str.upper()
    lejos = analisis.acceso_comprometido(
        t, umbral_primer=umbral_centro, umbral_segundo=umbral_hospital
    )
    t["evaluada"] = lejos | t[["primary_time_min", "secondary_time_min"]].notna().all(axis=1)
    t["comprometida"] = lejos
    t["doble_barrera"] = t["secondary_time_min"].gt(umbral_hospital) & t["transporte_foraneo"].eq("NO").fillna(False)
    t["marginacion_alta"] = t["grado_marginacion"].isin(["ALTO", "MUY ALTO"])
    return t


def resumir_municipios(t: pd.DataFrame) -> pd.DataFrame:
    """Construye indicadores con denominadores explícitos por fuente."""
    poblacion = t["population"]
    tiempos = t["secondary_time_min"]
    columnas = t.assign(
        poblacion_evaluada=poblacion.where(t["evaluada"], 0),
        acceso_comprometido=poblacion.where(t["comprometida"], 0),
        doble_barrera=poblacion.where(t["doble_barrera"], 0),
        poblacion_doble_evaluable=poblacion.where(tiempos.notna() & t["transporte_foraneo"].isin(["SI", "SÍ", "NO"]), 0),
        marginacion_alta=poblacion.where(t["marginacion_alta"], 0),
        poblacion_con_marginacion=poblacion.where(t["grado_marginacion"].isin(["MUY BAJO", "BAJO", "MEDIO", "ALTO", "MUY ALTO"]), 0),
        poblacion_sakbe=poblacion.where(
            t.get("secondary_method", pd.Series("", index=t.index)).eq("sakbe"), 0
        ),
        poblacion_con_tiempo=poblacion.where(tiempos.notna(), 0),
        minutos_persona=(poblacion * tiempos).fillna(0),
    )
    grupos = columnas.groupby("cvegeo", sort=True)
    totales = [
        "population", "poblacion_evaluada", "acceso_comprometido", "doble_barrera",
        "poblacion_doble_evaluable", "marginacion_alta", "poblacion_con_marginacion",
        "poblacion_sakbe", "poblacion_con_tiempo", "minutos_persona",
    ]
    m = grupos[totales].sum()
    m["doble_barrera"] = m["doble_barrera"].where(m["poblacion_doble_evaluable"].gt(0))
    m["municipio"] = grupos["municipality_name"].first()
    for nombre, numerador, denominador in (
        ("pct_comprometido", "acceso_comprometido", "poblacion_evaluada"),
        ("pct_doble_barrera", "doble_barrera", "poblacion_doble_evaluable"),
        ("pct_doble_evaluable", "poblacion_doble_evaluable", "population"),
        ("pct_sakbe", "poblacion_sakbe", "population"),
        ("pct_marginacion_alta", "marginacion_alta", "poblacion_con_marginacion"),
    ):
        m[nombre] = 100 * m[numerador].div(m[denominador].where(m[denominador].gt(0)))
    m["minutos_hospital"] = m.pop("minutos_persona").div(m["poblacion_con_tiempo"].where(m["poblacion_con_tiempo"].gt(0)))
    return m.reset_index()


def integrar_ingreso(municipios: pd.DataFrame, ingreso: pd.DataFrame, minimo: int) -> pd.DataFrame:
    """Cruza ENIGH por clave INEGI y suprime el ingreso antes de mostrarlo o exportarlo."""
    if ingreso.empty:
        return municipios.assign(estado_enigh="Sin datos ENIGH")
    campos = ["clave_cvegeo", "n_hogares", "n_upm", "ing_pc", "fiable"]
    opcionales = ["ing_pc_ic_inferior", "ing_pc_ic_superior", "ing_pc_cv", "ing_pc_fiable"]
    e = ingreso[campos + [c for c in opcionales if c in ingreso]].rename(
        columns={"clave_cvegeo": "cvegeo"}
    ).copy()
    e["cvegeo"] = e["cvegeo"].astype("string")
    e = e[e["cvegeo"].str.fullmatch(r"26\d{3}", na=False)]
    m = municipios.merge(e, on="cvegeo", how="left", validate="one_to_one")
    suficiente = m["n_hogares"].ge(minimo) & m["fiable"].eq(True)
    valor = pd.to_numeric(m["ing_pc"], errors="coerce").replace([float("inf"), -float("inf")], float("nan"))
    precisa = m.get("ing_pc_fiable", pd.Series(pd.NA, index=m.index))
    baja_precision = precisa.eq(False).fillna(False).astype(bool)
    publicable = suficiente & valor.notna() & ~baja_precision
    m["estado_enigh"] = "Sin muestra"
    m.loc[m["n_hogares"].notna(), "estado_enigh"] = "Muestra insuficiente"
    m.loc[suficiente, "estado_enigh"] = "Sin estimación"
    m.loc[suficiente & baja_precision, "estado_enigh"] = "Precisión insuficiente"
    m.loc[publicable, "estado_enigh"] = "Exploratoria · sin precisión validada"
    m.loc[publicable & precisa.eq(True).fillna(False).astype(bool), "estado_enigh"] = "Exploratoria · con precisión reportada"
    m["ing_pc"] = valor.where(publicable)
    for campo in ("ing_pc_ic_inferior", "ing_pc_ic_superior", "ing_pc_cv"):
        if campo in m:
            m[campo] = m[campo].where(publicable)
    return m.drop(columns=["fiable", "ing_pc_fiable"], errors="ignore")
