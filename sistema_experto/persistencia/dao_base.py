# -*- coding: utf-8 -*-
from abc import ABC
from .conexion import ConexionBD


class DAO(ABC):
    """Clase base de los objetos de acceso a datos (DAO)."""

    def __init__(self, conexion: ConexionBD):
        self._bd = conexion

    def _todos(self, sql, params=()):
        with self._bd.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def _uno(self, sql, params=()):
        with self._bd.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def _escribir(self, sql, params=(), retornar=False):
        with self._bd.cursor(commit=True) as cur:
            cur.execute(sql, params)
            return cur.fetchone() if retornar else None
