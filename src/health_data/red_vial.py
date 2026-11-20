"""Rutas cerradas de una brigada sobre tiempos de viaje dirigidos."""

from itertools import pairwise, permutations

MAX_PARADAS = 8


def minutos_ruta(orden, conexiones):
    tiempos = [conexiones.get(f"{a}:{b}") for a, b in pairwise(orden)]
    if any(tramo is None for tramo in tiempos):
        return None
    return sum(tramo["minutos"] for tramo in tiempos)


def optimizar_brigada(base, paradas, conexiones):
    """Encuentra el mínimo exacto para la selección y regresa a la base."""
    paradas = tuple(paradas)
    if not 1 <= len(paradas) <= MAX_PARADAS or len(set(paradas)) != len(paradas) or base in paradas:
        raise ValueError("Selecciona de una a ocho localidades distintas de la base.")
    mejor, minimo = None, float("inf")
    for visita in permutations(paradas):
        orden = (base, *visita, base)
        tiempo = minutos_ruta(orden, conexiones)
        if tiempo is not None and tiempo < minimo:
            mejor, minimo = orden, tiempo
    return (mejor, minimo) if mejor is not None else (None, None)
