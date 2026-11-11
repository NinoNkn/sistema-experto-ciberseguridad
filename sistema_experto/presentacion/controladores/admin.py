# -*- coding: utf-8 -*-
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from aplicacion.errores import ErrorNegocio
from aplicacion.servicios import ROL_ADMIN
from .seguridad import rol_requerido, usuario_sesion

bp = Blueprint("admin", __name__, url_prefix="/admin")
SOLO = rol_requerido(ROL_ADMIN)


def _c():
    return current_app.contenedor()


def _entero(nombre):
    try:
        return int(request.form.get(nombre, ""))
    except ValueError:
        raise ErrorNegocio("Valor inválido.")


@bp.route("/usuarios")
@SOLO
def usuarios():
    s = _c().admin
    return render_template("admin_usuarios.html", usuarios=s.usuarios(), roles=s.roles())


@bp.route("/usuarios/crear", methods=["POST"])
@SOLO
def crear():
    try:
        _c().admin.crear_usuario(usuario_sesion(), request.form.get("nombre"), request.form.get("correo"),
                                 request.form.get("clave"), _entero("id_rol"))
        flash("Usuario creado.", "ok")
    except ErrorNegocio as e:
        flash(str(e), "error")
    return redirect(url_for("admin.usuarios"))


def _accion(f, ok):
    try:
        f()
        flash(ok, "ok")
    except ErrorNegocio as e:
        flash(str(e), "error")
    return redirect(url_for("admin.usuarios"))


@bp.route("/usuarios/<int:id_u>/estado", methods=["POST"])
@SOLO
def estado(id_u):
    activo = request.form.get("activo") == "1"
    return _accion(lambda: _c().admin.cambiar_estado(usuario_sesion(), id_u, activo),
                   "Usuario activado." if activo else "Usuario desactivado.")


@bp.route("/usuarios/<int:id_u>/rol", methods=["POST"])
@SOLO
def rol(id_u):
    return _accion(lambda: _c().admin.cambiar_rol(usuario_sesion(), id_u, _entero("id_rol")), "Rol actualizado.")


@bp.route("/usuarios/<int:id_u>/clave", methods=["POST"])
@SOLO
def clave(id_u):
    return _accion(lambda: _c().admin.restablecer_clave(usuario_sesion(), id_u, request.form.get("clave")), "Clave restablecida.")


@bp.route("/bitacora")
@SOLO
def bitacora():
    s = _c().admin
    accion = request.args.get("accion", "")
    return render_template("admin_bitacora.html", eventos=s.bitacora(200, accion), acciones=s.acciones_bitacora(), accion=accion)
