# -*- coding: utf-8 -*-
from functools import wraps
from flask import session, redirect, url_for, abort, flash, request


def rol_requerido(*roles):
    """Exige sesión iniciada y uno de los roles indicados (control de acceso por rol)."""
    def deco(f):
        @wraps(f)
        def interno(*a, **k):
            if not session.get("uid"):
                flash("Inicie sesión para continuar.", "aviso")
                return redirect(url_for("acceso.login", siguiente=request.path))
            if session.get("rol") not in roles:
                abort(403, "Su rol no tiene permiso para esta función.")
            return f(*a, **k)
        return interno
    return deco


def usuario_sesion():
    from aplicacion.modelos import Usuario
    return Usuario(id_usuario=session["uid"], nombre=session["nombre"], correo=session["correo"],
                   id_rol=session["id_rol"], rol=session["rol"])


def inicio_por_rol(rol):
    destino = {"Analista SOC": "cita.lista", "Ingeniero del conocimiento": "conocimiento.lista",
               "Administrador del sistema": "admin.usuarios"}.get(rol, "acceso.login")
    return url_for(destino)
