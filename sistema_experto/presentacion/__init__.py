# -*- coding: utf-8 -*-
"""Capa de presentación web (Flask): controladores y plantillas.

Cada solicitud crea un Contenedor con el rol del SGBD del usuario autenticado."""
import os
import secrets
from datetime import timedelta
from flask import Flask, g, session, request, render_template, abort
from fabrica import Contenedor, ROL_BD
from aplicacion.servicios import ROL_ANALISTA, ROL_INGENIERO, ROL_ADMIN
from . import etiquetas


def create_app(dsn=None, testing=False):
    app = Flask(__name__, template_folder="plantillas", static_folder="estaticos")
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=15),      # RNF03: cierre por inactividad
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SEGURA", "0") == "1",
        DSN=dsn or os.environ.get("DATABASE_URL"), TESTING=testing)

    # ---- acceso al contenedor de la solicitud ------------------------------
    def contenedor():
        if "c" not in g:
            rol_bd = ROL_BD.get(session.get("rol"))
            g.c = Contenedor(app.config["DSN"], rol_bd)
        return g.c
    app.contenedor = contenedor

    @app.teardown_appcontext
    def cerrar(_exc):
        c = g.pop("c", None)
        if c is not None:
            c.cerrar()

    # ---- CSRF, cabeceras de seguridad, filtros ------------------------------
    def csrf_token():
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        return session["csrf"]

    @app.before_request
    def verificar_csrf():
        session.permanent = True
        if request.method == "POST":
            enviado = request.form.get("csrf", "")
            if not enviado or not secrets.compare_digest(enviado, session.get("csrf", "")):
                abort(400, "Solicitud no válida (token CSRF).")

    @app.after_request
    def cabeceras(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; img-src 'self' data:"
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.template_filter("pct")
    def pct(v):
        return f"{float(v):.1f}".replace(".", ",") + " %"

    @app.template_filter("fecha")
    def fecha(v):
        return v.strftime("%d/%m/%Y %H:%M") if v else "—"

    app.jinja_env.globals.update(csrf_token=csrf_token, etiqueta=etiquetas.etiqueta_valor,
                                 FUENTE=etiquetas.FUENTE, ESTADO=etiquetas.ESTADO,
                                 ROL_ANALISTA=ROL_ANALISTA, ROL_INGENIERO=ROL_INGENIERO, ROL_ADMIN=ROL_ADMIN)

    @app.context_processor
    def usuario_actual():
        return {"sesion": {"nombre": session.get("nombre"), "rol": session.get("rol")} if session.get("uid") else None}

    # ---- controladores -------------------------------------------------------
    from .controladores import acceso, cita, conocimiento, admin
    for bp in (acceso.bp, cita.bp, conocimiento.bp, admin.bp):
        app.register_blueprint(bp)

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    def error_http(e):
        return render_template("error.html", codigo=e.code, mensaje=e.description), e.code

    @app.errorhandler(500)
    def error_interno(e):
        return render_template("error.html", codigo=500, mensaje="Ocurrió un error inesperado. Intente de nuevo."), 500

    return app
