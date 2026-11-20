from health_data.red_vial import minutos_ruta, optimizar_brigada


def test_circuito_dirigido_respeta_el_regreso_y_detecta_desconexion():
    tiempos = {"B:A": 30, "A:C": 30, "C:B": 30, "B:C": 10, "C:A": 5, "A:B": 8}
    conexiones = {arco: {"minutos": minutos} for arco, minutos in tiempos.items()}
    assert minutos_ruta(("B", "A", "C", "B"), conexiones) == 90
    assert optimizar_brigada("B", ["A", "C"], conexiones) == (("B", "C", "A", "B"), 23)
    assert optimizar_brigada("B", ["A", "X"], conexiones) == (None, None)
