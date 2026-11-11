import os, re, sys
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from presentacion import create_app

DSN = os.environ.get("TEST_DATABASE_URL", "host=/tmp/pg port=5433 user=postgres dbname=sistema_experto")
USUARIOS = {"analista": ("analista@umb-soc.test", "Analista#2026"),
            "ingeniero": ("ingeniero@umb-soc.test", "Ingeniero#2026"),
            "admin": ("admin@umb-soc.test", "Admin#2026")}


@pytest.fixture()
def app():
    return create_app(dsn=DSN, testing=True)


def token(html):
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


class Cliente:
    def __init__(self, app):
        self.c = app.test_client()

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, datos=None, csrf=True, desde="/login"):
        datos = dict(datos or {})
        if csrf:
            datos["csrf"] = token(self.c.get(desde).get_data(as_text=True))
        return self.c.post(url, data=datos)

    def entrar(self, rol, clave=None):
        correo, cl = USUARIOS[rol]
        return self.post("/login", {"correo": correo, "clave": clave or cl})


@pytest.fixture()
def cli(app):
    return Cliente(app)


def _limpiar_hipotesis_de_prueba():
    """Elimina las hipótesis creadas por las pruebas (id > 25) para no contaminar el motor."""
    import psycopg2
    with psycopg2.connect(DSN) as cx, cx.cursor() as cur:
        cur.execute("""DELETE FROM conocimiento.regla_premisa WHERE id_regla IN
                       (SELECT id_regla FROM conocimiento.regla WHERE id_hipotesis > 25)""")
        cur.execute("DELETE FROM transaccional.resultado_hipotesis WHERE id_hipotesis > 25")
        cur.execute("DELETE FROM transaccional.retroalimentacion WHERE id_hipotesis_corregida > 25")
        cur.execute("DELETE FROM conocimiento.parametro_inferencia WHERE id_hipotesis > 25")
        cur.execute("DELETE FROM conocimiento.regla WHERE id_hipotesis > 25")
        cur.execute("DELETE FROM conocimiento.hipotesis WHERE id_hipotesis > 25")


@pytest.fixture(scope="session", autouse=True)
def limpieza_global():
    _limpiar_hipotesis_de_prueba()
    yield
    _limpiar_hipotesis_de_prueba()
