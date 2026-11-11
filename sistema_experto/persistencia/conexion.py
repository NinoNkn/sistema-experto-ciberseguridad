# -*- coding: utf-8 -*-
"""Capa de persistencia: conexión única al SGBD PostgreSQL."""
import os
from contextlib import contextmanager
import psycopg2
import psycopg2.extras


class ConexionBD:
    ROLES_PERMITIDOS = ("rol_analista_soc", "rol_ing_conocimiento", "rol_admin_sistema")

    def __init__(self, dsn=None, rol_bd=None):
        """rol_bd: rol del SGBD con el que se ejecutan las consultas (mínimo privilegio)."""
        if rol_bd is not None and rol_bd not in self.ROLES_PERMITIDOS:
            raise ValueError(f"rol de base de datos no permitido: {rol_bd}")
        self._dsn = dsn or os.environ.get("DATABASE_URL", "dbname=sistema_experto")
        self._rol_bd = rol_bd
        self._con = None

    def _abrir(self):
        if self._con is None or self._con.closed:
            self._con = psycopg2.connect(self._dsn)
            if self._rol_bd:
                with self._con.cursor() as cur:
                    cur.execute(f"SET ROLE {self._rol_bd}")   # nombre validado contra la lista blanca
                self._con.commit()
        return self._con

    @contextmanager
    def cursor(self, commit=False):
        con = self._abrir()
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield cur
            if commit:
                con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            cur.close()

    def cerrar(self):
        if self._con is not None and not self._con.closed:
            self._con.close()
