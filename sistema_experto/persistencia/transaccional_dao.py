# -*- coding: utf-8 -*-
"""DAO del módulo transaccional: usuarios, citas, memoria de trabajo, resultado y retroalimentación."""
from .dao_base import DAO
from aplicacion.modelos import Usuario, Cita


class UsuarioDAO(DAO):
    def por_correo(self, correo):
        r = self._uno("""SELECT u.id_usuario, u.nombre, u.correo, u.id_rol, ro.nombre AS rol, u.activo, u.intentos_fallidos
                         FROM transaccional.usuario u JOIN transaccional.rol ro ON ro.id_rol = u.id_rol
                         WHERE u.correo=%s""", (correo,))
        return Usuario(**r) if r else None

    def clave_valida(self, id_usuario, clave):
        """Verifica la clave con bcrypt (pgcrypto) sin sacar el hash de la base."""
        return self._uno("SELECT clave_hash = crypt(%s, clave_hash) AS ok FROM transaccional.usuario WHERE id_usuario=%s",
                         (clave, id_usuario))["ok"]

    def registrar_intento(self, id_usuario, exitoso, maximo=5):
        if exitoso:
            self._escribir("UPDATE transaccional.usuario SET intentos_fallidos=0 WHERE id_usuario=%s", (id_usuario,))
        else:
            self._escribir("""UPDATE transaccional.usuario
                              SET intentos_fallidos=intentos_fallidos+1,
                                  activo = CASE WHEN intentos_fallidos+1 >= %s THEN FALSE ELSE activo END
                              WHERE id_usuario=%s""", (maximo, id_usuario))

    def crear(self, nombre, correo, clave, id_rol):
        return self._escribir("""INSERT INTO transaccional.usuario (nombre, correo, clave_hash, id_rol)
                                 VALUES (%s,%s,crypt(%s, gen_salt('bf',10)),%s) RETURNING id_usuario""",
                              (nombre, correo, clave, id_rol), retornar=True)["id_usuario"]

    def listar(self):
        return self._todos("""SELECT u.id_usuario, u.nombre, u.correo, ro.nombre AS rol, u.activo, u.intentos_fallidos
                              FROM transaccional.usuario u JOIN transaccional.rol ro ON ro.id_rol=u.id_rol ORDER BY 1""")

    def cambiar_estado(self, id_usuario, activo):
        self._escribir("UPDATE transaccional.usuario SET activo=%s, intentos_fallidos=0 WHERE id_usuario=%s",
                       (activo, id_usuario))

    def por_id(self, id_usuario):
        r = self._uno("""SELECT u.id_usuario, u.nombre, u.correo, u.id_rol, ro.nombre AS rol, u.activo, u.intentos_fallidos
                         FROM transaccional.usuario u JOIN transaccional.rol ro ON ro.id_rol = u.id_rol
                         WHERE u.id_usuario=%s""", (id_usuario,))
        return Usuario(**r) if r else None

    def restablecer_clave(self, id_usuario, clave):
        self._escribir("""UPDATE transaccional.usuario SET clave_hash=crypt(%s, gen_salt('bf',10)),
                          intentos_fallidos=0 WHERE id_usuario=%s""", (clave, id_usuario))

    def cambiar_rol(self, id_usuario, id_rol):
        self._escribir("UPDATE transaccional.usuario SET id_rol=%s WHERE id_usuario=%s", (id_rol, id_usuario))


class RolDAO(DAO):
    def listar(self):
        return self._todos("SELECT * FROM transaccional.rol ORDER BY id_rol")


class CitaDAO(DAO):
    def crear(self, id_usuario, descripcion):
        r = self._escribir("""INSERT INTO transaccional.cita (id_usuario, descripcion_caso)
                              VALUES (%s,%s) RETURNING id_cita""", (id_usuario, descripcion), retornar=True)
        return r["id_cita"]

    def obtener(self, id_cita):
        r = self._uno("""SELECT id_cita, id_usuario, estado, descripcion_caso, id_hipotesis_resultado, id_prioridad_resultado
                         FROM transaccional.cita WHERE id_cita=%s""", (id_cita,))
        return Cita(**r) if r else None

    def detalle(self, id_cita):
        """Cabecera de la cita para la interfaz: usuario, fechas, resultado y retroalimentación."""
        return self._uno("""SELECT c.id_cita, c.id_usuario, c.estado, c.descripcion_caso, c.fecha_inicio, c.fecha_fin,
                                   c.id_hipotesis_resultado, h.nombre AS hipotesis, pr.nombre AS prioridad,
                                   pr.accion_recomendada AS accion_prioridad
                            FROM transaccional.cita c
                            LEFT JOIN conocimiento.hipotesis h ON h.id_hipotesis=c.id_hipotesis_resultado
                            LEFT JOIN conocimiento.prioridad pr ON pr.id_prioridad=c.id_prioridad_resultado
                            WHERE c.id_cita=%s""", (id_cita,))

    def cerrar(self, id_cita, id_hipotesis, id_prioridad):
        self._escribir("""UPDATE transaccional.cita SET estado='finalizada', fecha_fin=now(),
                          id_hipotesis_resultado=%s, id_prioridad_resultado=%s WHERE id_cita=%s""",
                       (id_hipotesis, id_prioridad, id_cita))

    def cambiar_estado(self, id_cita, estado):
        self._escribir("UPDATE transaccional.cita SET estado=%s WHERE id_cita=%s", (estado, id_cita))

    def historial(self, id_usuario=None):
        sql = """SELECT c.id_cita, c.fecha_inicio, c.estado, h.nombre AS hipotesis, pr.nombre AS prioridad,
                        COALESCE(hc.nombre,'-') AS hipotesis_corregida
                 FROM transaccional.cita c
                 LEFT JOIN conocimiento.hipotesis h ON h.id_hipotesis=c.id_hipotesis_resultado
                 LEFT JOIN conocimiento.prioridad pr ON pr.id_prioridad=c.id_prioridad_resultado
                 LEFT JOIN transaccional.retroalimentacion ra ON ra.id_cita=c.id_cita
                 LEFT JOIN conocimiento.hipotesis hc ON hc.id_hipotesis=ra.id_hipotesis_corregida"""
        if id_usuario:
            return self._todos(sql + " WHERE c.id_usuario=%s ORDER BY c.id_cita", (id_usuario,))
        return self._todos(sql + " ORDER BY c.id_cita")


class HechoCitaDAO(DAO):
    def agregar(self, id_cita, id_hecho, origen, id_nodo):
        self._escribir("""INSERT INTO transaccional.hecho_cita (id_cita, id_hecho, origen, id_nodo)
                          VALUES (%s,%s,%s,%s)""", (id_cita, id_hecho, origen, id_nodo))

    def listar(self, id_cita):
        """Memoria de trabajo de la cita: respuestas en el orden en que se dieron."""
        return self._todos("""SELECT hc.id_hecho, f.atributo, f.valor, hc.origen, hc.id_nodo
                              FROM transaccional.hecho_cita hc JOIN conocimiento.hecho f ON f.id_hecho=hc.id_hecho
                              WHERE hc.id_cita=%s ORDER BY hc.fecha_hora, hc.id_hecho""", (id_cita,))


class OmisionCitaDAO(DAO):
    def agregar(self, id_cita, id_nodo):
        self._escribir("INSERT INTO transaccional.omision_cita (id_cita, id_nodo) VALUES (%s,%s)", (id_cita, id_nodo))

    def listar(self, id_cita):
        return self._todos("""SELECT o.id_nodo, n.atributo FROM transaccional.omision_cita o
                              JOIN conocimiento.nodo_arbol n ON n.id_nodo=o.id_nodo WHERE o.id_cita=%s""", (id_cita,))


class ResultadoHipotesisDAO(DAO):
    def guardar_top(self, id_cita, evaluaciones):
        with self._bd.cursor(commit=True) as cur:
            for pos, e in enumerate(evaluaciones, 1):
                cur.execute("""INSERT INTO transaccional.resultado_hipotesis
                               (id_cita,id_hipotesis,posicion,contador,contradicciones,peso) VALUES (%s,%s,%s,%s,%s,%s)""",
                            (id_cita, e.id_hipotesis, pos, e.contador, e.contradicciones, round(e.peso, 3)))

    def listar(self, id_cita):
        return self._todos("""SELECT rh.posicion, h.nombre AS hipotesis, rh.contador, rh.contradicciones, rh.peso
                              FROM transaccional.resultado_hipotesis rh
                              JOIN conocimiento.hipotesis h ON h.id_hipotesis=rh.id_hipotesis
                              WHERE rh.id_cita=%s ORDER BY rh.posicion""", (id_cita,))


class RetroalimentacionDAO(DAO):
    def crear(self, id_cita, id_usuario, resultado, id_hipotesis_corregida, comentario):
        self._escribir("""INSERT INTO transaccional.retroalimentacion
                          (id_cita,id_usuario,resultado,id_hipotesis_corregida,comentario) VALUES (%s,%s,%s,%s,%s)""",
                       (id_cita, id_usuario, resultado, id_hipotesis_corregida, comentario))

    def listar(self, solo_pendientes=False):
        return self._todos("""SELECT ra.id_retroalimentacion AS id, ra.id_cita AS cita, h.nombre AS concluida,
                                     ra.resultado, COALESCE(hc.nombre,'-') AS corregida_a, ra.comentario, ra.revisada
                              FROM transaccional.retroalimentacion ra
                              JOIN transaccional.cita c ON c.id_cita=ra.id_cita
                              JOIN conocimiento.hipotesis h ON h.id_hipotesis=c.id_hipotesis_resultado
                              LEFT JOIN conocimiento.hipotesis hc ON hc.id_hipotesis=ra.id_hipotesis_corregida
                              """ + ("WHERE NOT ra.revisada " if solo_pendientes else "") + "ORDER BY ra.id_retroalimentacion")

    def por_cita(self, id_cita):
        return self._uno("""SELECT ra.id_retroalimentacion AS id, ra.resultado, ra.comentario, ra.revisada, ra.fecha_hora,
                                   COALESCE(hc.nombre,'-') AS corregida_a
                            FROM transaccional.retroalimentacion ra
                            LEFT JOIN conocimiento.hipotesis hc ON hc.id_hipotesis=ra.id_hipotesis_corregida
                            WHERE ra.id_cita=%s""", (id_cita,))

    def marcar_revisada(self, id_retroalimentacion):
        self._escribir("UPDATE transaccional.retroalimentacion SET revisada=TRUE WHERE id_retroalimentacion=%s",
                       (id_retroalimentacion,))


class BitacoraDAO(DAO):
    def registrar(self, id_usuario, accion, detalle=None):
        self._escribir("INSERT INTO transaccional.bitacora (id_usuario, accion, detalle) VALUES (%s,%s,%s)",
                       (id_usuario, accion, detalle))

    def listar(self, limite=100, accion=None):
        sql = """SELECT b.id_evento, b.fecha_hora, u.correo, b.accion, b.detalle
                 FROM transaccional.bitacora b LEFT JOIN transaccional.usuario u ON u.id_usuario=b.id_usuario"""
        if accion:
            return self._todos(sql + " WHERE b.accion=%s ORDER BY b.id_evento DESC LIMIT %s", (accion, limite))
        return self._todos(sql + " ORDER BY b.id_evento DESC LIMIT %s", (limite,))

    def acciones(self):
        return [r["accion"] for r in self._todos("SELECT DISTINCT accion FROM transaccional.bitacora ORDER BY 1")]
