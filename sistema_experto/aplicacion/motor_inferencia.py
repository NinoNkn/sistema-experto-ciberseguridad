# -*- coding: utf-8 -*-
"""Motor de inferencia granular y probabilístico.

No contiene reglas de incidentes: cada respuesta dispara consultas al conocimiento
(GranuloDAO) y el motor solo suma contadores y calcula pesos de forma genérica.
"""
import math
from typing import List, Optional, Sequence, Tuple
from .modelos import Evaluacion, Granulo


class MotorInferencia:
    TOP = 5

    def __init__(self, granulo_dao, hecho_dao, nodo_dao):
        self._granulos = granulo_dao
        self._hechos = hecho_dao
        self._nodos = nodo_dao
        self._catalogo: Optional[List[Granulo]] = None
        self._dominio = {}

    # ---- Consulta 1: catálogo (una vez) -----------------------------------
    def _catalogo_hipotesis(self):
        if self._catalogo is None:
            self._catalogo = self._granulos.catalogo()
        return self._catalogo

    def _k(self, atributo):
        if atributo not in self._dominio:
            self._dominio[atributo] = self._hechos.tamano_dominio(atributo)
        return self._dominio[atributo]

    # ---- Consultas sucesivas: una por respuesta ---------------------------
    def evaluar(self, respuestas: Sequence[Tuple[str, str]]) -> List[Evaluacion]:
        """respuestas: [(atributo, valor)] en orden. Devuelve las 25 hipótesis ordenadas."""
        ev = {g.id_hipotesis: Evaluacion(granulo=g, log_puntaje=math.log(g.prior)) for g in self._catalogo_hipotesis()}
        for atributo, valor in respuestas:
            k = self._k(atributo)
            premisas = {p["id_hipotesis"]: p for p in self._granulos.premisas_por_atributo(atributo)}
            for e in ev.values():
                r = e.granulo.fiabilidad
                p = premisas.get(e.id_hipotesis)
                if p is None:                       # la hipótesis no tiene premisa sobre este atributo
                    e.log_puntaje += math.log(1.0 / k)
                elif p["valor"] == valor:           # coincide: se incrementa el contador de la hoja
                    e.contador += 1
                    e.log_puntaje += math.log(r)
                else:                               # contradice
                    e.contradicciones += 1
                    e.log_puntaje += math.log((1.0 - r) / (k - 1))
        m = max(e.log_puntaje for e in ev.values())
        z = sum(math.exp(e.log_puntaje - m) for e in ev.values())
        for e in ev.values():
            e.peso = 100.0 * math.exp(e.log_puntaje - m) / z
        return sorted(ev.values(), key=lambda e: (-e.contador, -round(e.log_puntaje, 9), -e.granulo.nivel, e.id_hipotesis))

    def top5(self, ranking: List[Evaluacion]) -> List[Evaluacion]:
        return ranking[: self.TOP]

    # ---- Consultas por gránulo: evidencia y siguiente pregunta ------------
    def explicar(self, evaluacion: Evaluacion, respuestas, omitidos=()):
        """Carga el gránulo completo de la hipótesis y clasifica cada premisa."""
        g = self._granulos.obtener(evaluacion.id_hipotesis)
        dadas = dict(respuestas)
        evaluacion.granulo = g
        evaluacion.evidencia = []
        pend = 0
        for p in g.premisas:
            if p.atributo in dadas:
                estado = "coincide" if dadas[p.atributo] == p.valor else "contradice"
            elif p.atributo in omitidos:
                estado = "desconocida"
            else:
                estado = "pendiente"
                pend += 1
            evaluacion.evidencia.append((p, estado))
        evaluacion.pendientes = pend
        return evaluacion

    def siguiente_nodo(self, ranking: List[Evaluacion], respuestas, omitidos=()) -> Optional[str]:
        """Pregunta siguiente: premisa pendiente de menor orden de la hipótesis líder
        entre las que aún no tienen contradicciones."""
        dadas = {a for a, _ in respuestas}
        for e in ranking:
            if e.contradicciones:
                continue
            g = self._granulos.obtener(e.id_hipotesis)
            for p in g.premisas:                       # ya vienen ordenadas por regla_premisa.orden
                if p.atributo not in dadas and p.atributo not in omitidos:
                    return self._nodos.por_atributo(p.atributo)["id_nodo"]
        return None
