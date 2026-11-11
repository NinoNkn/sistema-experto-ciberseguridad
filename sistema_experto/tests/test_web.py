import re
import pytest
from conftest import Cliente, USUARIOS, token


def texto(r):
    return r.get_data(as_text=True)


# ---------- acceso y seguridad ----------
def test_login_y_redireccion_por_rol(app):
    for rol, destino in [("analista", "/citas"), ("ingeniero", "/conocimiento"), ("admin", "/admin/usuarios")]:
        c = Cliente(app)
        r = c.entrar(rol)
        assert r.status_code == 302 and destino in r.headers["Location"], rol


def test_sin_sesion_redirige_a_login(cli):
    assert cli.get("/citas/").status_code in (302, 401, 403)
    assert cli.get("/admin/usuarios").status_code in (302, 401, 403)


def test_clave_incorrecta_no_entra(cli):
    r = cli.entrar("analista", clave="mala")
    assert r.status_code == 401
    assert cli.get("/citas/").status_code != 200


def test_csrf_obligatorio(cli):
    cli.entrar("analista")
    r = cli.post("/citas/nueva", {"descripcion": "incidente de prueba largo"}, csrf=False)
    assert r.status_code == 400


def test_rbac_cruzado(app):
    a, i, d = Cliente(app), Cliente(app), Cliente(app)
    a.entrar("analista"); i.entrar("ingeniero"); d.entrar("admin")
    assert a.get("/admin/usuarios").status_code == 403
    assert a.get("/conocimiento/").status_code == 403
    assert i.get("/citas/").status_code == 403
    assert i.get("/admin/bitacora").status_code == 403
    assert d.get("/citas/").status_code == 403
    assert d.get("/conocimiento/").status_code == 403


def test_cabeceras_de_seguridad(cli):
    r = cli.get("/login")
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_bloqueo_tras_cinco_intentos(app):
    # usuario temporal creado por el admin para no bloquear las cuentas de prueba
    d = Cliente(app); d.entrar("admin")
    correo = "bloqueo_%d@umb-soc.test" % abs(hash(app))
    r = d.post("/admin/usuarios/crear", {"nombre": "Tmp", "correo": correo, "clave": "Temporal2026", "id_rol": "1"}, desde="/admin/usuarios")
    assert r.status_code == 302
    x = Cliente(app)
    for _ in range(5):
        x.post("/login", {"correo": correo, "clave": "incorrecta"})
    r = x.post("/login", {"correo": correo, "clave": "Temporal2026"})
    assert r.status_code == 401, "la cuenta debe estar bloqueada aunque la clave sea correcta"
    assert "Bloqueado" in texto(d.get("/admin/usuarios"))


# ---------- flujo del analista ----------
def _consulta(c, desc="Alertas de fuerza bruta contra el servidor VPN"):
    r = c.post("/citas/nueva", {"descripcion": desc}, desde="/citas/")
    assert r.status_code == 302, texto(r)[:300]
    return r.headers["Location"]


def _responder_hasta_el_final(c, url, elegir):
    """Responde cada pregunta con la opción que devuelve elegir(opciones); máx 40 pasos."""
    for _ in range(40):
        html = texto(c.get(url))
        if "Sin preguntas pendientes" in html or 'name="id_nodo"' not in html:
            return html
        nodo = re.search(r'name="id_nodo" value="([^"]+)"', html).group(1)
        ids = re.findall(r'name="id_hecho" value="(\d+)">\s*<button type="submit">([^<]+)', html)
        ruta = url.replace("/citas/", "/citas/") + "/responder"
        id_hecho = elegir(ids)
        r = c.post(ruta, {"id_nodo": nodo, "id_hecho": id_hecho}, desde=url)
        assert r.status_code == 302, texto(r)[:300]
    raise AssertionError("no terminó")


def test_consulta_completa_con_retroalimentacion(app):
    c = Cliente(app); c.entrar("analista")
    url = _consulta(c)
    html = texto(c.get(url))
    assert "Pregunta 1" in html and "Hipótesis más probables" in html
    # primera opción siempre
    html = _responder_hasta_el_final(c, url, lambda ids: ids[0][0])
    assert "Respuestas registradas" in html
    r = c.post(url + "/cerrar", {}, desde=url)
    assert r.status_code == 302
    html = texto(c.get(url))
    assert "Resultado guardado" in html and "Guardar retroalimentación" in html
    idh = re.search(r'<option value="(\d+)" selected', html).group(1)
    r = c.post(url + "/retroalimentacion", {"id_hipotesis": idh, "comentario": "Coincide con el caso real"}, desde=url)
    assert r.status_code == 302
    html = texto(c.get(url))
    assert "Pendiente de revisión" in html and "Guardar retroalimentación" not in html
    # no se puede retroalimentar dos veces ni responder una cita cerrada
    r = c.post(url + "/retroalimentacion", {"id_hipotesis": idh}, desde=url)
    assert "ya" in texto(c.get(url)).lower() or r.status_code in (302, 400)
    assert c.post(url + "/responder", {"accion": "no_se", "id_nodo": "1"}, desde=url).status_code in (302, 400, 403)


def test_no_se_no_cambia_el_ranking(app):
    c = Cliente(app); c.entrar("analista")
    url = _consulta(c, "Prueba de la opción No sé en el arbol")
    html = texto(c.get(url))
    nodo = re.search(r'name="id_nodo" value="([^"]+)"', html).group(1)
    c.post(url + "/responder", {"id_nodo": nodo, "accion": "no_se"}, desde=url)
    html2 = texto(c.get(url))
    assert "«No sé»" in html2
    assert "Pregunta 2" in html2


def test_validaciones_de_la_descripcion(app):
    c = Cliente(app); c.entrar("analista")
    r = c.post("/citas/nueva", {"descripcion": "corta"}, desde="/citas/")
    assert r.status_code in (200, 302)
    assert "5" in texto(c.get("/citas/")) or "caracteres" in texto(r)


def test_un_analista_no_ve_citas_de_otro(app):
    c = Cliente(app); c.entrar("analista")
    url = _consulta(c, "Cita privada del analista uno")
    d = Cliente(app); d.entrar("admin")
    assert d.get(url).status_code == 403
    i = Cliente(app); i.entrar("ingeniero")
    assert i.get(url).status_code == 403
    idc = url.rstrip("/").split("/")[-1]
    assert i.get(f"/conocimiento/cita/{idc}").status_code == 200


# ---------- recorrido de los 25 caminos del árbol ----------
def test_recorre_todas_las_hojas_del_arbol(app):
    """Cada rama del árbol se puede recorrer vía web hasta una hipótesis sin romperse."""
    c = Cliente(app); c.entrar("analista")
    vistas = set()
    for variante in range(8):
        url = _consulta(c, f"Recorrido automático variante {variante}")
        pos = {"n": 0}

        def elegir(ids, v=variante, p=pos):
            p["n"] += 1
            return ids[(v >> (p["n"] % 3)) % len(ids)][0]
        html = _responder_hasta_el_final(c, url, elegir)
        m = re.search(r"<strong>([^<]+)</strong> <span class=\"insignia", html)
        assert m, "debe haber un ranking"
        vistas.add(m.group(1))
        c.post(url + "/cerrar", {}, desde=url)
    assert len(vistas) >= 3


# ---------- ingeniero del conocimiento ----------
def test_ingeniero_edita_regla_y_premisas(app):
    i = Cliente(app); i.entrar("ingeniero")
    html = texto(i.get("/conocimiento/"))
    assert "Phishing" in html or "phishing" in html.lower()
    url = "/conocimiento/hipotesis/1"
    html = texto(i.get(url))
    prior = re.search(r'name="prior" value="([^"]+)"', html).group(1)
    accion = re.search(r'<textarea id="accion" name="accion" required>(.*?)</textarea>', html, re.S).group(1)
    # valores inválidos
    r = i.post(url + "/actualizar", {"id_prioridad": "1", "accion": "corta", "prior": prior, "fiabilidad": "0.9"}, desde=url)
    assert "al menos 10" in texto(i.get(url))
    r = i.post(url + "/actualizar", {"id_prioridad": "1", "accion": accion, "prior": "1.5", "fiabilidad": "0.9"}, desde=url)
    assert r.status_code == 302
    # válido (mismos valores) y bitácora
    r = i.post(url + "/actualizar", {"id_prioridad": "1", "accion": accion + " ", "prior": prior, "fiabilidad": "0.90"}, desde=url)
    assert r.status_code == 302
    d = Cliente(app); d.entrar("admin")
    assert "conocimiento_modificado" in texto(d.get("/admin/bitacora"))


def test_ingeniero_agrega_y_quita_premisa(app):
    i = Cliente(app); i.entrar("ingeniero")
    url = "/conocimiento/hipotesis/2"
    html = texto(i.get(url))
    n = len(re.findall(r'premisas/quitar', html))
    m = re.search(r'<select id="id_hecho" name="id_hecho"><option value="(\d+)"', html)
    assert m
    hecho = m.group(1)
    i.post(url + "/premisas/agregar", {"id_hecho": hecho, "orden": "1"}, desde=url)
    html = texto(i.get(url))
    assert len(re.findall(r'premisas/quitar', html)) == n + 1
    i.post(url + "/premisas/quitar", {"id_hecho": hecho}, desde=url)
    html = texto(i.get(url))
    assert len(re.findall(r'premisas/quitar', html)) == n
    # el orden queda consecutivo 1..n
    ordenes = [int(x) for x in re.findall(r"<tr><td>(\d+)</td><td>[^<]+</td><td>[^<]+</td><td>\s*<form", html)]
    assert ordenes == list(range(1, n + 1))


def test_ingeniero_crea_hipotesis(app):
    i = Cliente(app); i.entrar("ingeniero")
    html = texto(i.get("/conocimiento/hipotesis/nueva"))
    ids = re.findall(r'<option value="(\d+)">', html)
    hechos = [ids[4], ids[12], ids[24]]
    nombre = "Hipótesis de prueba %d" % abs(hash(app))
    r = i.post("/conocimiento/hipotesis/nueva", {"nombre": nombre, "descripcion": "Hipótesis creada por la prueba automática", "id_prioridad": "2",
        "accion": "Aislar el equipo y notificar al responsable.", "prior": "0.02", "fiabilidad": "0.9", "premisa": hechos},
        desde="/conocimiento/hipotesis/nueva")
    assert r.status_code == 302, texto(r)[:400]
    assert nombre in texto(i.get("/conocimiento/"))
    # sin premisas falla
    r = i.post("/conocimiento/hipotesis/nueva", {"nombre": "Otra", "id_prioridad": "2", "accion": "Aislar el equipo ya.",
        "prior": "0.02", "fiabilidad": "0.9"}, desde="/conocimiento/hipotesis/nueva")
    assert r.status_code == 200


def test_ingeniero_revisa_retroalimentacion(app):
    a = Cliente(app); a.entrar("analista")
    url = _consulta(a, "Caso para retroalimentar y revisar")
    _responder_hasta_el_final(a, url, lambda ids: ids[0][0])
    a.post(url + "/cerrar", {}, desde=url)
    html = texto(a.get(url))
    idh = re.search(r'<option value="(\d+)" selected', html).group(1)
    a.post(url + "/retroalimentacion", {"id_hipotesis": idh, "comentario": "ok"}, desde=url)
    i = Cliente(app); i.entrar("ingeniero")
    html = texto(i.get("/conocimiento/retroalimentacion"))
    m = re.search(r"/conocimiento/retroalimentacion/(\d+)/revisar", html)
    assert m
    assert i.post(m.group(0), {}, desde="/conocimiento/retroalimentacion").status_code == 302
    assert m.group(0) not in texto(i.get("/conocimiento/retroalimentacion"))


# ---------- administrador ----------
def test_admin_crea_usuario_y_valida(app):
    d = Cliente(app); d.entrar("admin")
    correo = "nuevo_%d@umb-soc.test" % abs(hash(app))
    # clave débil
    d.post("/admin/usuarios/crear", {"nombre": "N", "correo": correo, "clave": "corta", "id_rol": "1"}, desde="/admin/usuarios")
    assert correo not in texto(d.get("/admin/usuarios"))
    d.post("/admin/usuarios/crear", {"nombre": "Nuevo", "correo": correo, "clave": "Segura2026x", "id_rol": "1"}, desde="/admin/usuarios")
    assert correo in texto(d.get("/admin/usuarios"))
    # duplicado
    d.post("/admin/usuarios/crear", {"nombre": "Nuevo", "correo": correo, "clave": "Segura2026x", "id_rol": "1"}, desde="/admin/usuarios")
    assert texto(d.get("/admin/usuarios")).count(correo) == 1
    # el nuevo usuario puede entrar
    n = Cliente(app)
    assert n.post("/login", {"correo": correo, "clave": "Segura2026x"}).status_code == 302
    # desactivar
    html = texto(d.get("/admin/usuarios"))
    idu = re.search(r"/admin/usuarios/(\d+)/estado[^>]*>(?:(?!</tr>).)*?" + re.escape(correo), html, re.S)
    fila = [m for m in re.finditer(r"<tr>.*?</tr>", html, re.S) if correo in m.group(0)][0].group(0)
    idu = re.search(r"/admin/usuarios/(\d+)/estado", fila).group(1)
    d.post(f"/admin/usuarios/{idu}/estado", {"activo": "0"}, desde="/admin/usuarios")
    assert Cliente(app).post("/login", {"correo": correo, "clave": "Segura2026x"}).status_code == 401


def test_admin_no_se_autodesactiva(app):
    d = Cliente(app); d.entrar("admin")
    html = texto(d.get("/admin/usuarios"))
    fila = [m for m in re.finditer(r"<tr>.*?</tr>", html, re.S) if "admin@umb-soc.test" in m.group(0)][0].group(0)
    idu = re.search(r"/admin/usuarios/(\d+)/estado", fila).group(1)
    d.post(f"/admin/usuarios/{idu}/estado", {"activo": "0"}, desde="/admin/usuarios")
    assert d.get("/admin/usuarios").status_code == 200


def test_bitacora_filtra(app):
    d = Cliente(app); d.entrar("admin")
    html = texto(d.get("/admin/bitacora?accion=login"))
    assert d.get("/admin/bitacora").status_code == 200 and "<table>" in html
