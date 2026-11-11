# -*- coding: utf-8 -*-
from flask import Blueprint, render_template, request, redirect, session, flash, current_app, url_for
from .seguridad import inicio_por_rol, usuario_sesion
from fabrica import Contenedor

bp = Blueprint("acceso", __name__)


@bp.route("/")
def inicio():
    if session.get("uid"):
        return redirect(inicio_por_rol(session["rol"]))
    return redirect(url_for("acceso.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # El inicio de sesión usa la conexión de servicio (aún no hay rol): solo toca usuario y bitácora.
        c = Contenedor(current_app.config["DSN"])
        try:
            u = c.auth.autenticar(request.form.get("correo", "").strip().lower(), request.form.get("clave", ""))
        finally:
            c.cerrar()
        if u is None:
            flash("Credenciales inválidas o cuenta bloqueada. Tras 5 intentos fallidos la cuenta se bloquea; "
                  "solicite al administrador que la reactive.", "error")
            return render_template("login.html"), 401
        session.clear()                                   # evita la fijación de sesión
        session.update(uid=u.id_usuario, nombre=u.nombre, correo=u.correo, id_rol=u.id_rol, rol=u.rol)
        session.permanent = True
        siguiente = request.args.get("siguiente", "")
        if siguiente.startswith("/") and not siguiente.startswith("//"):
            return redirect(siguiente)
        return redirect(inicio_por_rol(u.rol))
    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    if session.get("uid"):
        c = current_app.contenedor()
        try:
            c.auth.cerrar_sesion(session["uid"])
        except Exception:
            pass
    session.clear()
    flash("Sesión cerrada.", "ok")
    return redirect(url_for("acceso.login"))
