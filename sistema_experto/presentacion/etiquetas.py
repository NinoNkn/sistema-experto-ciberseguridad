# -*- coding: utf-8 -*-
"""Textos de interfaz para los valores de los hechos."""
VECTOR = {"correo": "Correo o mensaje", "archivo_proceso": "Archivo o proceso anómalo", "trafico_red": "Tráfico de red",
          "autenticacion": "Autenticación", "app_web": "Aplicación web", "infraestructura": "Configuración o infraestructura",
          "reporte_usuario": "Reporte de usuario"}
FUENTE = {"respuesta_usuario": "Respuesta del analista", "consulta_bd": "Dato de seguridad (consulta a base de datos)",
          "valor_defecto": "Valor por defecto (ausencia de evidencia)"}
ESTADO = {"en_curso": "En curso", "finalizada": "Finalizada", "confirmada": "Confirmada", "corregida": "Corregida"}


def etiqueta_valor(valor):
    if valor == "verdadero":
        return "Sí"
    if valor == "falso":
        return "No"
    return VECTOR.get(valor, valor)
