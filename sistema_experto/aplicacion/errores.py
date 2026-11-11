# -*- coding: utf-8 -*-
"""Errores de negocio: se muestran al usuario como mensajes, no como fallas del sistema."""


class ErrorNegocio(Exception):
    pass


class AccesoDenegado(ErrorNegocio):
    pass
