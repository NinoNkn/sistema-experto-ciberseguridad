# -*- coding: utf-8 -*-
"""Servicios de la capa de aplicación.

Reglas de negocio: autenticación y bloqueo, ciclo de la cita, mantenimiento del conocimiento
y administración de usuarios. Ninguno escribe SQL: usan los DAO.
"""
import re
from .errores import ErrorNegocio, AccesoDenegado
from .modelos import EstadoCita
from .motor_inferencia import MotorInferencia

MAX_INTENTOS = 5
CLAVE_MIN = 8
ROL_ANALISTA, ROL_INGENIERO, ROL_ADMIN = "Analista SOC", "Ingeniero del conocimiento", "Administrador del sistema"


class ServicioAutenticacion:
    def __init__(self, usuario_dao, bitacora_dao):
        self._usuarios, self._bitacora = usuario_dao, bitacora_dao

    def autenticar(self, correo, clave):
        """Devuelve el Usuario o None. Tras MAX_INTENTOS fallos consecutivos la cuenta se bloquea."""
        u = self._usuarios.por_correo(correo)
        if u is None:
            self._bitacora.registrar(None, "login_fallido", f"correo desconocido: {correo}")
            return None
        if not u.activo:
            self._bitacora.registrar(u.id_usuario, "login_bloqueado", "cuenta inactiva o bloqueada")
            return None
        if self._usuarios.clave_valida(u.id_usuario, clave):
            self._usuarios.registrar_intento(u.id_usuario, True)
            self._bitacora.registrar(u.id_usuario, "login_ok")
            return u
        self._usuarios.registrar_intento(u.id_usuario, False, MAX_INTENTOS)
        self._bitacora.registrar(u.id_usuario, "login_fallido", "clave incorrecta")
        return None

    def usuario(self, id_usuario):
        return self._usuarios.por_id(id_usuario)

    def cerrar_sesion(self, id_usuario):
        self._bitacora.registrar(id_usuario, "logout")


class ServicioCita:
    def __init__(self, motor: MotorInferencia, cita_dao, hecho_cita_dao, omision_dao,
                 resultado_dao, retro_dao, bitacora_dao, hecho_dao, nodo_dao, granulo_dao=None):
        self._motor, self._citas, self._hc, self._om = motor, cita_dao, hecho_cita_dao, omision_dao
        self._res, self._retro, self._bit = resultado_dao, retro_dao, bitacora_dao
        self._hechos, self._nodos, self._granulos = hecho_dao, nodo_dao, granulo_dao

    # ---- operaciones básicas (usadas también por las pruebas) --------------
    def abrir(self, id_usuario, descripcion):
        c = self._citas.crear(id_usuario, descripcion)
        self._bit.registrar(id_usuario, "cita_abierta", f"cita {c}")
        return c

    def responder(self, id_cita, id_nodo, id_hecho, origen="respuesta_usuario"):
        self._hc.agregar(id_cita, id_hecho, origen, id_nodo)

    def omitir(self, id_cita, id_nodo):
        self._om.agregar(id_cita, id_nodo)

    def estado(self, id_cita) -> EstadoCita:
        resp = [(r["atributo"], r["valor"]) for r in self._hc.listar(id_cita)]
        omit = [o["atributo"] for o in self._om.listar(id_cita)]
        ranking = self._motor.evaluar(resp)
        top = self._motor.top5(ranking)
        for e in top:
            self._motor.explicar(e, resp, omit)
        nodo = self._motor.siguiente_nodo(ranking, resp, omit)
        preg = self._nodos.obtener(nodo)["pregunta"] if nodo else None
        return EstadoCita(top5=top, siguiente_nodo=nodo, siguiente_pregunta=preg, respondidas=len(resp))

    def cerrar(self, id_cita, id_usuario):
        est = self.estado(id_cita)
        self._res.guardar_top(id_cita, est.top5)
        lider = est.top5[0]
        prio = self._prioridad_id(lider.granulo.nivel)
        self._citas.cerrar(id_cita, lider.id_hipotesis, prio)
        self._bit.registrar(id_usuario, "cita_cerrada", f"cita {id_cita}: {lider.granulo.nombre}")
        return est

    def retroalimentar(self, id_cita, id_usuario, id_hipotesis_correcta, comentario=""):
        cita = self._citas.obtener(id_cita)
        if id_hipotesis_correcta == cita.id_hipotesis_resultado:
            self._retro.crear(id_cita, id_usuario, "confirmada", None, comentario)
            self._citas.cambiar_estado(id_cita, "confirmada")
        else:
            self._retro.crear(id_cita, id_usuario, "corregida", id_hipotesis_correcta, comentario)
            self._citas.cambiar_estado(id_cita, "corregida")
        self._bit.registrar(id_usuario, "retroalimentacion", f"cita {id_cita}")

    @staticmethod
    def _prioridad_id(nivel):
        return nivel   # en la base id_prioridad = nivel (1 Baja … 4 Crítica)

    # ---- operaciones para la interfaz web (validan propiedad y estado) -----
    def _cita_del_usuario(self, id_cita, usuario, permitir_lectura_ajena=False):
        c = self._citas.detalle(id_cita)
        if c is None:
            raise ErrorNegocio("La cita no existe.")
        if c["id_usuario"] != usuario.id_usuario and not permitir_lectura_ajena:
            raise AccesoDenegado("La cita pertenece a otro analista.")
        return c

    def historial(self, usuario):
        return self._citas.historial(usuario.id_usuario if usuario.rol == ROL_ANALISTA else None)

    def iniciar(self, usuario, descripcion):
        descripcion = (descripcion or "").strip()
        if len(descripcion) < 5:
            raise ErrorNegocio("Describa brevemente el incidente (mínimo 5 caracteres).")
        if len(descripcion) > 500:
            raise ErrorNegocio("La descripción no puede superar 500 caracteres.")
        return self.abrir(usuario.id_usuario, descripcion)

    def vista(self, id_cita, usuario):
        """Todo lo que necesita la pantalla de la cita en un solo objeto."""
        c = self._cita_del_usuario(id_cita, usuario, permitir_lectura_ajena=usuario.rol != ROL_ANALISTA)
        respuestas = self._hc.listar(id_cita)
        omitidas = self._om.listar(id_cita)
        est = self.estado(id_cita)
        opciones = self._nodos.opciones(est.siguiente_nodo) if est.siguiente_nodo and c["estado"] == "en_curso" else []
        nodo = self._nodos.obtener(est.siguiente_nodo) if est.siguiente_nodo else None
        return {"cita": c, "estado": est, "respuestas": respuestas, "omitidas": omitidas, "nodo": nodo,
                "opciones": opciones, "retro": self._retro.por_cita(id_cita),
                "top_guardado": self._res.listar(id_cita) if c["estado"] != "en_curso" else [],
                "hipotesis": self._granulos.catalogo() if self._granulos else []}

    def responder_pregunta(self, id_cita, usuario, id_nodo, id_hecho):
        c = self._cita_del_usuario(id_cita, usuario)
        if c["estado"] != "en_curso":
            raise ErrorNegocio("La cita ya está cerrada.")
        actual = self.estado(id_cita).siguiente_nodo
        if id_nodo != actual:
            raise ErrorNegocio("Esa pregunta ya no es la pregunta pendiente; la pantalla se actualizó.")
        validas = {o["id_hecho"]: o for o in self._nodos.opciones(id_nodo)}
        if id_hecho not in validas:
            raise ErrorNegocio("La respuesta no corresponde a la pregunta.")
        self.responder(id_cita, id_nodo, id_hecho, validas[id_hecho]["fuente_tipica"])

    def omitir_pregunta(self, id_cita, usuario, id_nodo):
        c = self._cita_del_usuario(id_cita, usuario)
        if c["estado"] != "en_curso":
            raise ErrorNegocio("La cita ya está cerrada.")
        if id_nodo != self.estado(id_cita).siguiente_nodo:
            raise ErrorNegocio("Esa pregunta ya no es la pregunta pendiente; la pantalla se actualizó.")
        self.omitir(id_cita, id_nodo)

    def cerrar_cita(self, id_cita, usuario):
        c = self._cita_del_usuario(id_cita, usuario)
        if c["estado"] != "en_curso":
            raise ErrorNegocio("La cita ya está cerrada.")
        if not self._hc.listar(id_cita):
            raise ErrorNegocio("Responda al menos una pregunta antes de cerrar la consulta.")
        return self.cerrar(id_cita, usuario.id_usuario)

    def registrar_retroalimentacion(self, id_cita, usuario, id_hipotesis, comentario):
        c = self._cita_del_usuario(id_cita, usuario)
        if c["estado"] == "en_curso":
            raise ErrorNegocio("Cierre la consulta antes de registrar la retroalimentación.")
        if self._retro.por_cita(id_cita):
            raise ErrorNegocio("Esta cita ya tiene retroalimentación guardada.")
        if id_hipotesis not in {g.id_hipotesis for g in self._granulos.catalogo()}:
            raise ErrorNegocio("Seleccione una hipótesis válida.")
        comentario = (comentario or "").strip()[:500]
        self.retroalimentar(id_cita, usuario.id_usuario, id_hipotesis, comentario)


class ServicioConocimiento:
    """Mantenimiento del conocimiento del experto (rol: ingeniero del conocimiento)."""

    def __init__(self, granulo_dao, admin_dao, hecho_dao, retro_dao, bitacora_dao):
        self._g, self._a, self._hechos, self._retro, self._bit = granulo_dao, admin_dao, hecho_dao, retro_dao, bitacora_dao

    # --- consultas (CU07)
    def granulos(self):
        """Catálogo de gránulos con el número de premisas de cada regla."""
        n = self._g.conteo_premisas()
        return [(g, n.get(g.id_regla, 0)) for g in self._g.catalogo()]

    def granulo(self, id_hipotesis):
        g = self._g.obtener(id_hipotesis)
        if g is None:
            raise ErrorNegocio("La hipótesis no existe.")
        return g

    def prioridades(self):
        return self._a.prioridades()

    def hechos(self):
        return self._a.hechos()

    def retroalimentacion(self, solo_pendientes=False):
        return self._retro.listar(solo_pendientes)

    def marcar_revisada(self, usuario, id_retro):
        self._retro.marcar_revisada(id_retro)
        self._bit.registrar(usuario.id_usuario, "retroalimentacion_revisada", f"retroalimentación {id_retro}")

    # --- modificación (CU06)
    def actualizar_regla(self, usuario, id_hipotesis, id_prioridad, accion, prior, fiabilidad):
        g = self.granulo(id_hipotesis)
        accion = (accion or "").strip()
        if len(accion) < 10:
            raise ErrorNegocio("La acción recomendada debe tener al menos 10 caracteres.")
        if id_prioridad not in {p["id_prioridad"] for p in self._a.prioridades()}:
            raise ErrorNegocio("Prioridad inválida.")
        self._validar_parametros(prior, fiabilidad)
        self._a.actualizar_regla(g.id_regla, id_prioridad, accion)
        self._a.actualizar_parametros(id_hipotesis, prior, fiabilidad)
        self._bit.registrar(usuario.id_usuario, "conocimiento_modificado", f"regla {g.id_regla} ({g.nombre}) actualizada")

    def agregar_premisa(self, usuario, id_hipotesis, id_hecho, orden):
        g = self.granulo(id_hipotesis)
        hecho = self._hechos.obtener(id_hecho)
        if hecho is None:
            raise ErrorNegocio("El hecho no existe.")
        if any(p.atributo == hecho.atributo for p in g.premisas):
            raise ErrorNegocio(f"La regla {g.id_regla} ya tiene una premisa sobre «{hecho.atributo}».")
        n = len(g.premisas)
        if not 1 <= orden <= n + 1:
            raise ErrorNegocio(f"El orden debe estar entre 1 y {n + 1}.")
        self._a.agregar_premisa(g.id_regla, id_hecho, orden)
        self._bit.registrar(usuario.id_usuario, "conocimiento_modificado",
                            f"regla {g.id_regla}: premisa {hecho.atributo} = {hecho.valor} en la posición {orden}")

    def quitar_premisa(self, usuario, id_hipotesis, id_hecho):
        g = self.granulo(id_hipotesis)
        if len(g.premisas) <= 1:
            raise ErrorNegocio("Una regla debe conservar al menos una premisa.")
        if id_hecho not in {p.id_hecho for p in g.premisas}:
            raise ErrorNegocio("La premisa no pertenece a la regla.")
        self._a.quitar_premisa(g.id_regla, id_hecho)
        self._bit.registrar(usuario.id_usuario, "conocimiento_modificado", f"regla {g.id_regla}: premisa H{id_hecho} eliminada")

    def crear_hipotesis(self, usuario, nombre, descripcion, id_prioridad, accion, prior, fiabilidad, premisas):
        """premisas: lista de id_hecho en orden. Crea hipótesis + regla + parámetros + premisas."""
        nombre, descripcion, accion = (nombre or "").strip(), (descripcion or "").strip(), (accion or "").strip()
        if len(nombre) < 3 or len(descripcion) < 10 or len(accion) < 10:
            raise ErrorNegocio("Complete nombre, descripción y acción recomendada.")
        if nombre.lower() in {g.nombre.lower() for g in self._g.catalogo()}:
            raise ErrorNegocio("Ya existe una hipótesis con ese nombre.")
        if id_prioridad not in {p["id_prioridad"] for p in self._a.prioridades()}:
            raise ErrorNegocio("Prioridad inválida.")
        self._validar_parametros(prior, fiabilidad)
        hechos = [self._hechos.obtener(i) for i in premisas]
        if not hechos or any(h is None for h in hechos):
            raise ErrorNegocio("Indique al menos una premisa válida.")
        if len({h.atributo for h in hechos}) != len(hechos):
            raise ErrorNegocio("Una regla no puede tener dos premisas sobre el mismo atributo.")
        id_h, id_r = self._a.crear_hipotesis(nombre, descripcion, id_prioridad, accion, prior, fiabilidad, self._a.experto_por_defecto())
        for orden, h in enumerate(hechos, 1):
            self._a.agregar_premisa(id_r, h.id_hecho, orden)
        self._bit.registrar(usuario.id_usuario, "conocimiento_modificado", f"hipótesis creada: {nombre} ({id_r})")
        return id_h

    @staticmethod
    def _validar_parametros(prior, fiabilidad):
        if not 0 < prior < 1:
            raise ErrorNegocio("El prior debe estar entre 0 y 1 (sin incluirlos).")
        if not 0.5 < fiabilidad < 1:
            raise ErrorNegocio("La fiabilidad debe estar entre 0,5 y 1 (sin incluirlos).")


class ServicioAdministracion:
    """Usuarios, roles y bitácora (rol: administrador del sistema)."""

    def __init__(self, usuario_dao, rol_dao, bitacora_dao):
        self._u, self._r, self._b = usuario_dao, rol_dao, bitacora_dao

    def usuarios(self):
        return self._u.listar()

    def roles(self):
        return self._r.listar()

    def bitacora(self, limite=100, accion=None):
        return self._b.listar(limite, accion or None)

    def acciones_bitacora(self):
        return self._b.acciones()

    @staticmethod
    def validar_clave(clave):
        if len(clave or "") < CLAVE_MIN:
            raise ErrorNegocio(f"La clave debe tener al menos {CLAVE_MIN} caracteres.")
        if not (re.search(r"[A-Za-z]", clave) and re.search(r"\d", clave)):
            raise ErrorNegocio("La clave debe combinar letras y números.")

    def crear_usuario(self, admin, nombre, correo, clave, id_rol):
        nombre, correo = (nombre or "").strip(), (correo or "").strip().lower()
        if len(nombre) < 3:
            raise ErrorNegocio("Escriba el nombre completo.")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo):
            raise ErrorNegocio("Correo inválido.")
        if self._u.por_correo(correo):
            raise ErrorNegocio("Ya existe un usuario con ese correo.")
        if id_rol not in {r["id_rol"] for r in self._r.listar()}:
            raise ErrorNegocio("Rol inválido.")
        self.validar_clave(clave)
        nuevo = self._u.crear(nombre, correo, clave, id_rol)
        self._b.registrar(admin.id_usuario, "usuario_creado", f"{correo} (rol {id_rol})")
        return nuevo

    def cambiar_estado(self, admin, id_usuario, activo):
        if id_usuario == admin.id_usuario and not activo:
            raise ErrorNegocio("No puede desactivar su propia cuenta.")
        if self._u.por_id(id_usuario) is None:
            raise ErrorNegocio("El usuario no existe.")
        self._u.cambiar_estado(id_usuario, activo)
        self._b.registrar(admin.id_usuario, "usuario_activado" if activo else "usuario_desactivado", f"usuario {id_usuario}")

    def cambiar_rol(self, admin, id_usuario, id_rol):
        if id_usuario == admin.id_usuario:
            raise ErrorNegocio("No puede cambiar su propio rol.")
        if id_rol not in {r["id_rol"] for r in self._r.listar()}:
            raise ErrorNegocio("Rol inválido.")
        self._u.cambiar_rol(id_usuario, id_rol)
        self._b.registrar(admin.id_usuario, "usuario_rol_cambiado", f"usuario {id_usuario} → rol {id_rol}")

    def restablecer_clave(self, admin, id_usuario, clave):
        self.validar_clave(clave)
        self._u.restablecer_clave(id_usuario, clave)
        self._b.registrar(admin.id_usuario, "clave_restablecida", f"usuario {id_usuario}")
