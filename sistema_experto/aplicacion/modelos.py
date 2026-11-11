# -*- coding: utf-8 -*-
"""Capa de aplicación: entidades de dominio (sin acceso a datos)."""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class Hecho:
    id_hecho: int
    atributo: str
    valor: str
    descripcion: str = ""
    fuente_tipica: str = "respuesta_usuario"


@dataclass(frozen=True)
class Premisa:
    """Fila de la tabla débil regla_premisa unida a su hecho."""
    id_regla: str
    id_hecho: int
    orden: int
    atributo: str
    valor: str


@dataclass
class Granulo:
    """Unidad mínima de conocimiento: hipótesis + regla + premisas + parámetros."""
    id_hipotesis: int
    nombre: str
    id_regla: str
    prioridad: str
    nivel: int
    accion: str
    prior: float
    fiabilidad: float
    premisas: List[Premisa] = field(default_factory=list)
    descripcion: str = ""


@dataclass
class Evaluacion:
    """Estado de una hipótesis frente a la evidencia: contador y peso."""
    granulo: Granulo
    contador: int = 0            # premisas que coinciden con las respuestas
    contradicciones: int = 0     # premisas que las respuestas contradicen
    pendientes: int = 0          # premisas aún sin respuesta
    log_puntaje: float = 0.0
    peso: float = 0.0            # peso relativo en % (suma 100 entre las 25)
    evidencia: List[tuple] = field(default_factory=list)  # (premisa, estado)

    @property
    def id_hipotesis(self):
        return self.granulo.id_hipotesis


@dataclass
class Usuario:
    id_usuario: int
    nombre: str
    correo: str
    id_rol: int
    rol: str = ""
    activo: bool = True
    intentos_fallidos: int = 0


@dataclass
class Cita:
    id_cita: int
    id_usuario: int
    estado: str
    descripcion_caso: Optional[str] = None
    id_hipotesis_resultado: Optional[int] = None
    id_prioridad_resultado: Optional[int] = None


@dataclass
class EstadoCita:
    """Lo que la interfaz necesita en cada paso de la cita."""
    top5: List[Evaluacion]
    siguiente_nodo: Optional[str]
    siguiente_pregunta: Optional[str]
    respondidas: int
