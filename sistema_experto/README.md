# Sistema experto para clasificar y priorizar incidentes de ciberseguridad

Proyecto de Ingeniería de Software (UMB) — Morales Orozco Santiago.
Aplicación web con arquitectura de tres capas (presentación / aplicación / persistencia, patrón DAO),
base de conocimiento separada del motor de inferencia y PostgreSQL 16.

## Funcionalidad
| Rol | Qué hace |
|---|---|
| **Analista SOC** | Abre consultas (citas), responde las preguntas del árbol de decisión (Sí/No/opciones/«No sé»), ve el top 5 de hipótesis con evidencia y acción recomendada, cierra la consulta y da retroalimentación (confirma o corrige). |
| **Ingeniero del conocimiento** | Consulta y edita reglas, premisas, prioridad, acción, prior y fiabilidad; crea hipótesis; revisa la retroalimentación de los analistas. |
| **Administrador** | Crea usuarios (no hay auto-registro), cambia rol, activa/desactiva, restablece claves y consulta la bitácora de auditoría. |

Procesos transaccionales: apertura/cierre de cita, registro de hechos y omisiones, resultado top 5, retroalimentación, gestión de usuarios y bitácora.

## Estructura
```
bd/        script SQL (esquemas conocimiento y transaccional, datos, roles y GRANTs)
persistencia/   DAOs (acceso a PostgreSQL, SET ROLE por rol)
aplicacion/     modelos, motor de inferencia y servicios (reglas de negocio)
presentacion/   Flask: controladores, plantillas Jinja y CSS
tests/          pruebas con pytest (motor + flujos web por rol + seguridad)
ejecutar.py     punto de entrada
```

## Instalación
1. PostgreSQL 16 con la extensión `pgcrypto` disponible.
2. Crear la base y cargar el script:
   ```bash
   createdb sistema_experto
   psql -d sistema_experto -f bd/sistema_experto_ciberseguridad_postgresql.sql
   ```
3. Crear el usuario de la aplicación y concederle los tres roles (la app hace `SET ROLE` según el rol del usuario web):
   ```sql
   CREATE ROLE app_se LOGIN PASSWORD 'CAMBIAR';
   GRANT rol_analista_soc, rol_ing_conocimiento, rol_admin_sistema TO app_se;
   GRANT CONNECT ON DATABASE sistema_experto TO app_se;
   ```
   Además, `app_se` necesita leer `transaccional.usuario` y `rol` para el inicio de sesión; si usa un superusuario local (desarrollo) no hace falta.
4. Entorno Python:
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env   # y exportar las variables
   export DATABASE_URL="..." SECRET_KEY="..."
   python ejecutar.py     # http://127.0.0.1:5000
   ```
   Producción: `gunicorn ejecutar:app` detrás de HTTPS y con `COOKIE_SEGURA=1`.

## Cuentas de demostración (cambiar en producción)
| Rol | Correo | Clave |
|---|---|---|
| Analista SOC | analista@umb-soc.test | Analista#2026 |
| Ingeniero del conocimiento | ingeniero@umb-soc.test | Ingeniero#2026 |
| Administrador | admin@umb-soc.test | Admin#2026 |

## Pruebas
```bash
TEST_DATABASE_URL="host=localhost dbname=sistema_experto user=postgres" python -m pytest tests -q
```
22 pruebas: los 25 caminos del árbol llegan a su hipótesis, RBAC cruzado (403), CSRF, bloqueo a 5 intentos, flujos completos de cada rol, validaciones y bitácora.

## Seguridad
bcrypt (pgcrypto), bloqueo tras 5 intentos fallidos, sesión de 15 min de inactividad, token CSRF en cada POST, CSP `default-src 'self'` y demás cabeceras, mínimo privilegio también en la BD (`SET ROLE` por petición), bitácora de auditoría.

## Limitaciones conocidas
- Probabilidades previas y fiabilidades son heurísticas del experto; deben calibrarse con casos reales.
- Los hechos de tipo `consulta_bd` (IDS/SIEM) los ingresa el analista manualmente: el conector es simulado.
- Una hipótesis nueva no modifica el árbol de decisión; se evalúa cuando sus hechos aparecen en las respuestas.
- TLS y cookies Secure dependen del despliegue.
