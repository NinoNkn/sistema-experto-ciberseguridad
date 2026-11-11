# -*- coding: utf-8 -*-
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from aplicacion.errores import ErrorNegocio, AccesoDenegado
from aplicacion.servicios import ROL_ANALISTA
from .seguridad import rol_requerido, usuario_sesion

bp = Blueprint("cita", __name__, url_prefix="/citas")


def _c():
    return current_app.contenedor()


@bp.route("/")
@rol_requerido(ROL_ANALISTA)
def lista():
    return render_template("citas_lista.html", citas=_c().citas.historial(usuario_sesion()))


@bp.route("/nueva", methods=["POST"])
@rol_requerido(ROL_ANALISTA)
def nueva():
    try:
        id_cita = _c().citas.iniciar(usuario_sesion(), request.form.get("descripcion"))
    except ErrorNegocio as e:
        flash(str(e), "error")
        return redirect(url_for("cita.lista"))
    return redirect(url_for("cita.ver", id_cita=id_cita))


@bp.route("/<int:id_cita>")
@rol_requerido(ROL_ANALISTA)
def ver(id_cita):
    try:
        v = _c().citas.vista(id_cita, usuario_sesion())
    except AccesoDenegado as e:
        from flask import abort
        abort(403, str(e))
    except ErrorNegocio as e:
        from flask import abort
        abort(404, str(e))
    return render_template("cita.html", v=v, solo_lectura=False)


def _volver(id_cita):
    return redirect(url_for("cita.ver", id_cita=id_cita))


@bp.route("/<int:id_cita>/responder", methods=["POST"])
@rol_requerido(ROL_ANALISTA)
def responder(id_cita):
    try:
        id_nodo = request.form.get("id_nodo", "")
        if request.form.get("accion") == "no_se":
            _c().citas.omitir_pregunta(id_cita, usuario_sesion(), id_nodo)
        else:
            _c().citas.responder_pregunta(id_cita, usuario_sesion(), id_nodo, int(request.form.get("id_hecho", "")))
    except (ErrorNegocio, ValueError) as e:
        flash(str(e) if isinstance(e, ErrorNegocio) else "Respuesta inválida.", "error")
    return _volver(id_cita)


@bp.route("/<int:id_cita>/cerrar", methods=["POST"])
@rol_requerido(ROL_ANALISTA)
def cerrar(id_cita):
    try:
        _c().citas.cerrar_cita(id_cita, usuario_sesion())
        flash("Consulta cerrada. El resultado quedó guardado; registre su retroalimentación.", "ok")
    except ErrorNegocio as e:
        flash(str(e), "error")
    return _volver(id_cita)


@bp.route("/<int:id_cita>/retroalimentacion", methods=["POST"])
@rol_requerido(ROL_ANALISTA)
def retroalimentacion(id_cita):
    try:
        _c().citas.registrar_retroalimentacion(id_cita, usuario_sesion(), int(request.form.get("id_hipotesis", "")),
                                               request.form.get("comentario"))
        flash("Retroalimentación guardada. Queda pendiente de revisión por el ingeniero del conocimiento.", "ok")
    except (ErrorNegocio, ValueError) as e:
        flash(str(e) if isinstance(e, ErrorNegocio) else "Seleccione una hipótesis.", "error")
    return _volver(id_cita)
