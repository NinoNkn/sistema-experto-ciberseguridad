# -*- coding: utf-8 -*-
"""DAO del módulo de conocimiento: consultas granulares de solo lectura."""
from .dao_base import DAO
from aplicacion.modelos import Granulo, Premisa, Hecho


class HechoDAO(DAO):
    def obtener(self, id_hecho):
        r = self._uno("SELECT * FROM conocimiento.hecho WHERE id_hecho=%s", (id_hecho,))
        return Hecho(**r) if r else None

    def buscar(self, atributo, valor):
        r = self._uno("SELECT * FROM conocimiento.hecho WHERE atributo=%s AND valor=%s", (atributo, valor))
        return Hecho(**r) if r else None

    def tamano_dominio(self, atributo):
        """Número de valores posibles del atributo (para la verosimilitud)."""
        return self._uno("SELECT COUNT(*) AS k FROM conocimiento.hecho WHERE atributo=%s", (atributo,))["k"]


class NodoArbolDAO(DAO):
    def obtener(self, id_nodo):
        return self._uno("SELECT * FROM conocimiento.nodo_arbol WHERE id_nodo=%s", (id_nodo,))

    def por_atributo(self, atributo):
        return self._uno("SELECT * FROM conocimiento.nodo_arbol WHERE atributo=%s", (atributo,))

    def opciones(self, id_nodo):
        """Hechos (respuestas posibles) que salen del nodo."""
        return self._todos(
            """SELECT h.id_hecho, h.atributo, h.valor, h.fuente_tipica
               FROM conocimiento.rama r JOIN conocimiento.hecho h ON h.id_hecho = r.id_hecho
               WHERE r.id_nodo_origen=%s ORDER BY h.id_hecho""", (id_nodo,))


class GranuloDAO(DAO):
    """Consulta el conocimiento por gránulos: una regla, sus premisas y su hipótesis."""

    _CAB = """SELECT h.id_hipotesis, h.nombre, h.descripcion, r.id_regla, pr.nombre AS prioridad, pr.nivel,
                     r.accion_recomendada AS accion, pi.prior::float AS prior, pi.fiabilidad::float AS fiabilidad
              FROM conocimiento.hipotesis h
              JOIN conocimiento.regla r ON r.id_hipotesis = h.id_hipotesis
              JOIN conocimiento.prioridad pr ON pr.id_prioridad = r.id_prioridad
              JOIN conocimiento.parametro_inferencia pi ON pi.id_hipotesis = h.id_hipotesis"""

    def catalogo(self):
        """Consulta 1: hipótesis, regla, prioridad, acción y parámetros (sin premisas)."""
        return [Granulo(**r) for r in self._todos(self._CAB + " ORDER BY h.id_hipotesis")]

    def conteo_premisas(self):
        return {r["id_regla"]: r["n"] for r in self._todos(
            "SELECT id_regla, COUNT(*) AS n FROM conocimiento.regla_premisa GROUP BY id_regla")}

    def obtener(self, id_hipotesis):
        """Consulta granular: el gránulo completo de UNA hipótesis, premisas por orden."""
        r = self._uno(self._CAB + " WHERE h.id_hipotesis=%s", (id_hipotesis,))
        if not r:
            return None
        g = Granulo(**r)
        g.premisas = [Premisa(**p) for p in self._todos(
            """SELECT rp.id_regla, rp.id_hecho, rp.orden, f.atributo, f.valor
               FROM conocimiento.regla_premisa rp JOIN conocimiento.hecho f ON f.id_hecho = rp.id_hecho
               WHERE rp.id_regla=%s ORDER BY rp.orden""", (g.id_regla,))]
        return g

    def premisas_por_atributo(self, atributo):
        """Consulta por respuesta: qué hipótesis tienen una premisa sobre el atributo y con qué valor."""
        return self._todos(
            """SELECT r.id_hipotesis, rp.id_hecho, rp.orden, f.valor
               FROM conocimiento.regla_premisa rp
               JOIN conocimiento.regla r ON r.id_regla = rp.id_regla
               JOIN conocimiento.hecho f ON f.id_hecho = rp.id_hecho
               WHERE f.atributo=%s""", (atributo,))


class ConocimientoAdminDAO(DAO):
    """Escritura del conocimiento (solo el rol del ingeniero tiene estos privilegios)."""

    def prioridades(self):
        return self._todos("SELECT id_prioridad, nombre, nivel, accion_recomendada FROM conocimiento.prioridad ORDER BY nivel DESC")

    def hechos(self):
        return self._todos("""SELECT f.id_hecho, f.atributo, f.valor, f.fuente_tipica,
                                     (SELECT COUNT(*) FROM conocimiento.regla_premisa rp WHERE rp.id_hecho=f.id_hecho) AS reglas
                              FROM conocimiento.hecho f ORDER BY f.id_hecho""")

    def experto_por_defecto(self):
        return self._uno("SELECT id_experto FROM conocimiento.experto ORDER BY id_experto LIMIT 1")["id_experto"]

    def hecho_de_regla_atributo(self, id_regla, atributo):
        return self._uno("""SELECT rp.id_hecho FROM conocimiento.regla_premisa rp
                            JOIN conocimiento.hecho f ON f.id_hecho=rp.id_hecho
                            WHERE rp.id_regla=%s AND f.atributo=%s""", (id_regla, atributo))

    def actualizar_regla(self, id_regla, id_prioridad, accion):
        self._escribir("""UPDATE conocimiento.regla SET id_prioridad=%s, accion_recomendada=%s WHERE id_regla=%s""",
                       (id_prioridad, accion, id_regla))

    def actualizar_parametros(self, id_hipotesis, prior, fiabilidad):
        self._escribir("""UPDATE conocimiento.parametro_inferencia SET prior=%s, fiabilidad=%s, version=version+1
                          WHERE id_hipotesis=%s""", (prior, fiabilidad, id_hipotesis))

    def agregar_premisa(self, id_regla, id_hecho, orden):
        """Inserta la premisa en la posición `orden`, corriendo las siguientes (UNIQUE id_regla, orden)."""
        with self._bd.cursor(commit=True) as cur:
            cur.execute("UPDATE conocimiento.regla_premisa SET orden=orden+1000 WHERE id_regla=%s AND orden>=%s", (id_regla, orden))
            cur.execute("INSERT INTO conocimiento.regla_premisa (id_regla,id_hecho,orden) VALUES (%s,%s,%s)", (id_regla, id_hecho, orden))
            cur.execute("UPDATE conocimiento.regla_premisa SET orden=orden-999 WHERE id_regla=%s AND orden>=1000", (id_regla,))

    def quitar_premisa(self, id_regla, id_hecho):
        with self._bd.cursor(commit=True) as cur:
            cur.execute("DELETE FROM conocimiento.regla_premisa WHERE id_regla=%s AND id_hecho=%s RETURNING orden", (id_regla, id_hecho))
            fila = cur.fetchone()
            if fila:
                cur.execute("UPDATE conocimiento.regla_premisa SET orden=orden+1000 WHERE id_regla=%s AND orden>%s", (id_regla, fila["orden"]))
                cur.execute("UPDATE conocimiento.regla_premisa SET orden=orden-1001 WHERE id_regla=%s AND orden>=1000", (id_regla,))

    def total_premisas(self, id_regla):
        return self._uno("SELECT COUNT(*) AS n FROM conocimiento.regla_premisa WHERE id_regla=%s", (id_regla,))["n"]

    def crear_hipotesis(self, nombre, descripcion, id_prioridad, accion, prior, fiabilidad, id_experto):
        """Crea la hipótesis, su regla (cabecera) y sus parámetros en una sola transacción."""
        with self._bd.cursor(commit=True) as cur:
            cur.execute("SELECT COALESCE(MAX(id_hipotesis),0)+1 AS n FROM conocimiento.hipotesis")
            id_h = cur.fetchone()["n"]
            cur.execute("SELECT COALESCE(MAX(SUBSTRING(id_regla FROM 2)::int),0)+1 AS n FROM conocimiento.regla")
            id_r = "R%02d" % cur.fetchone()["n"]
            cur.execute("INSERT INTO conocimiento.hipotesis (id_hipotesis,nombre,descripcion) VALUES (%s,%s,%s)", (id_h, nombre, descripcion))
            cur.execute("""INSERT INTO conocimiento.regla (id_regla,id_hipotesis,id_prioridad,id_experto,accion_recomendada,fecha_registro)
                           VALUES (%s,%s,%s,%s,%s,CURRENT_DATE)""", (id_r, id_h, id_prioridad, id_experto, accion))
            cur.execute("INSERT INTO conocimiento.parametro_inferencia (id_hipotesis,prior,fiabilidad) VALUES (%s,%s,%s)", (id_h, prior, fiabilidad))
        return id_h, id_r
