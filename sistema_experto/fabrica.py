# -*- coding: utf-8 -*-
"""Ensambla las tres capas (inyección de dependencias manual).

Cada solicitud web crea un Contenedor con el rol del SGBD que corresponde al usuario
autenticado, de modo que los privilegios (GRANT) se aplican también en la base de datos.
"""
from persistencia.conexion import ConexionBD
from persistencia.conocimiento_dao import HechoDAO, NodoArbolDAO, GranuloDAO, ConocimientoAdminDAO
from persistencia.transaccional_dao import (UsuarioDAO, RolDAO, CitaDAO, HechoCitaDAO, OmisionCitaDAO,
                                            ResultadoHipotesisDAO, RetroalimentacionDAO, BitacoraDAO)
from aplicacion.motor_inferencia import MotorInferencia
from aplicacion.servicios import (ServicioAutenticacion, ServicioCita, ServicioConocimiento,
                                  ServicioAdministracion, ROL_ANALISTA, ROL_INGENIERO, ROL_ADMIN)

ROL_BD = {ROL_ANALISTA: "rol_analista_soc", ROL_INGENIERO: "rol_ing_conocimiento", ROL_ADMIN: "rol_admin_sistema"}


class Contenedor:
    def __init__(self, dsn=None, rol_bd=None):
        bd = ConexionBD(dsn, rol_bd)
        self.bd = bd
        self.hecho, self.nodo, self.granulo = HechoDAO(bd), NodoArbolDAO(bd), GranuloDAO(bd)
        self.usuario, self.rol, self.cita = UsuarioDAO(bd), RolDAO(bd), CitaDAO(bd)
        self.hecho_cita, self.omision = HechoCitaDAO(bd), OmisionCitaDAO(bd)
        self.resultado, self.retro, self.bitacora = ResultadoHipotesisDAO(bd), RetroalimentacionDAO(bd), BitacoraDAO(bd)
        self.conocimiento_admin = ConocimientoAdminDAO(bd)
        self.motor = MotorInferencia(self.granulo, self.hecho, self.nodo)
        self.auth = ServicioAutenticacion(self.usuario, self.bitacora)
        self.citas = ServicioCita(self.motor, self.cita, self.hecho_cita, self.omision, self.resultado,
                                  self.retro, self.bitacora, self.hecho, self.nodo, self.granulo)
        self.conocimiento = ServicioConocimiento(self.granulo, self.conocimiento_admin, self.hecho, self.retro, self.bitacora)
        self.admin = ServicioAdministracion(self.usuario, self.rol, self.bitacora)

    def cerrar(self):
        self.bd.cerrar()
