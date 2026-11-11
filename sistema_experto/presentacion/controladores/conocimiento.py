# -*- coding: utf-8 -*-
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, abort
from aplicacion.errores import ErrorNegocio
from aplicacion.servicios import ROL_INGENIERO
from .seguridad import rol_requerido, usuario_sesion

bp = Blueprint("conocimiento", __name__, url_prefix="/conocimiento")
SOLO = rol_requerido(ROL_INGENIERO)


def _c():
    return current_app.contenedor()


def _flotante(nombre):
    try:
        return float(request.form.get(nombre, "").replace(",", "."))
    except ValueError:
        raise ErrorNegocio(f"Valor numérico inválido en «{nombre}».")


def _entero(nombre):
    try:
        return int(request.form.get(nombre, ""))
    except ValueError:
        raise ErrorNegocio(f"Valor inválido en «{nombre}».")


@bp.route("/")
@SOLO
def lista():
    return render_template("conocimiento_lista.html", granulos=_c().conocimiento.granulos())


@bp.route("/hechos")
@SOLO
def hechos():
    return render_template("hechos.html", hechos=_c().conocimiento.hechos())


@bp.route("/hipotesis/<int:id_h>")
@SOLO
def hipotesis(id_h):
    s = _c().conocimiento
    try:
        g = s.granulo(id_h)
    except ErrorNegocio as e:
        abort(404, str(e))
    usados = {p.atributo for p in g.premisas}
    disponibles = [h for h in s.hechos() if h["atributo"] not in usados]
    return render_template("hipotesis.html", g=g, prioridades=s.prioridades(), disponibles=disponibles)


@bp.route("/hipotesis/<int:id_h>/actualizar", methods=["POST"])
@SOLO
def actualizar(id_h):
    try:
        _c().conocimiento.actualizar_regla(usuario_sesion(), id_h, _entero("id_prioridad"), request.form.get("accion"),
                                           _flotante("prior"), _flotante("fiabilidad"))
        flash("Regla y parámetros actualizados. Se aplican desde la próxima consulta.", "ok")
    except ErrorNegocio as e:
        flash(str(e), "error")
    return redirect(url_for("conocimiento.hipotesis", id_h=id_h))


@bp.route("/hipotesis/<int:id_h>/premisas/agregar", methods=["POST"])
@SOLO
def agregar_premisa(id_h):
    try:
        _c().conocimiento.agregar_premisa(usuario_sesion(), id_h, _entero("id_hecho"), _entero("orden"))
        flash("Premisa agregada.", "ok")
    except ErrorNegocio as e:
        flash(str(e), "error")
    return redirect(url_for("conocimiento.hipotesis", id_h=id_h))


@bp.route("/hipotesis/<int:id_h>/premisas/quitar", methods=["POST"])
@SOLO
def quitar_premisa(id_h):
    try:
        _c().conocimiento.quitar_premisa(usuario_sesion(), id_h, _entero("id_hecho"))
        flash("Premisa eliminada.", "ok")
    except ErrorNegocio as e:
        flash(str(e), "error")
    return redirect(url_for("conocimiento.hipotesis", id_h=id_h))


@bp.route("/hipotesis/nueva", methods=["GET", "POST"])
@SOLO
def nueva():
    s = _c().conocimiento
    if request.method == "POST":
        try:
            premisas = [int(x) for x in request.form.getlist("premisa") if x]
            id_h = s.crear_hipotesis(usuario_sesion(), request.form.get("nombre"), request.form.get("descripcion"),
                                     _entero("id_prioridad"), request.form.get("accion"), _flotante("prior"),
                                     _flotante("fiabilidad"), premisas)
            flash("Hipótesis creada con su regla y sus premisas.", "ok")
            return redirect(url_for("conocimiento.hipotesis", id_h=id_h))
        except (ErrorNegocio, ValueError) as e:
            flash(str(e) if isinstance(e, ErrorNegocio) else "Premisa inválida.", "error")
    return render_template("hipotesis_nueva.html", prioridades=s.prioridades(), hechos=s.hechos(), form=request.form)


@bp.route("/retroalimentacion")
@SOLO
def retroalimentacion():
    solo = request.args.get("todas") != "1"
    return render_template("retro_lista.html", filas=_c().conocimiento.retroalimentacion(solo), solo_pendientes=solo)


@bp.route("/retroalimentacion/<int:id_retro>/revisar", methods=["POST"])
@SOLO
def revisar(id_retro):
    _c().conocimiento.marcar_revisada(usuario_sesion(), id_retro)
    flash("Retroalimentación marcada como revisada.", "ok")
    return redirect(url_for("conocimiento.retroalimentacion"))


@bp.route("/cita/<int:id_cita>")
@SOLO
def ver_cita(id_cita):
    """Vista de solo lectura de una cita, para revisar la retroalimentación."""
    try:
        v = _c().citas.vista(id_cita, usuario_sesion())
    except ErrorNegocio as e:
        abort(404, str(e))
    return render_template("cita.html", v=v, solo_lectura=True)
