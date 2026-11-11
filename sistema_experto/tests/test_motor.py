"""Pruebas del motor de inferencia contra la base de conocimiento cargada (25 caminos)."""
import pytest
from conftest import DSN
from fabrica import Contenedor


@pytest.fixture(scope="module")
def cont():
    c = Contenedor(DSN)
    yield c
    c.cerrar()


def test_los_25_caminos_llegan_a_su_hipotesis(cont):
    m = cont.motor
    granulos = [cont.conocimiento.granulo(g.id_hipotesis) for g, _ in cont.conocimiento.granulos() if g.id_hipotesis <= 25]
    assert len(granulos) == 25
    for g in granulos:
        mapa = {p.atributo: p.valor for p in g.premisas}
        resp = []
        nodo = m.siguiente_nodo(m.evaluar(resp), resp)
        pasos = 0
        while nodo and pasos < 30:
            att = cont.nodo.obtener(nodo)["atributo"]
            resp.append((att, mapa[att]))
            nodo = m.siguiente_nodo(m.evaluar(resp), resp)
            pasos += 1
        top = m.evaluar(resp)[0]
        assert top.id_hipotesis == g.id_hipotesis, g.nombre
        assert top.contador == len(g.premisas) and top.contradicciones == 0, g.nombre


def test_pesos_suman_100(cont):
    r = cont.motor.evaluar([("vector", cont.nodo.opciones("N0")[0]["valor"])])
    assert abs(sum(e.peso for e in r) - 100) < 0.01


def test_no_se_no_altera_contadores(cont):
    base = cont.motor.evaluar([])
    assert all(e.contador == 0 and e.contradicciones == 0 for e in base)
