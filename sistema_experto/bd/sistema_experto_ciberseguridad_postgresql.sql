
-- =====================================================================
-- SISTEMA EXPERTO PARA LA CLASIFICACIÓN Y PRIORIZACIÓN DE INCIDENTES
-- DE CIBERSEGURIDAD | SGBD: PostgreSQL 16 (versión 6)
-- Dos módulos (esquemas): conocimiento y transaccional
-- Una regla = hechos + tabla débil (regla_premisa) + hipótesis
-- El motor devuelve las 5 hipótesis con mayor contador y peso probabilístico
-- =====================================================================
CREATE EXTENSION IF NOT EXISTS pgcrypto;
DROP SCHEMA IF EXISTS transaccional CASCADE;
DROP SCHEMA IF EXISTS conocimiento CASCADE;
CREATE SCHEMA conocimiento;
CREATE SCHEMA transaccional;

-- ---------------------------------------------------------------------
-- MÓDULO 1: BASE DE CONOCIMIENTO (lo que sabe el experto)
-- ---------------------------------------------------------------------
CREATE TABLE conocimiento.experto (
    id_experto SMALLINT     PRIMARY KEY,
    nombre     VARCHAR(100) NOT NULL,
    cargo      VARCHAR(80)  NOT NULL,
    fuente     VARCHAR(150) NOT NULL
);

CREATE TABLE conocimiento.prioridad (
    id_prioridad       SMALLINT    PRIMARY KEY,
    nombre             VARCHAR(10) NOT NULL UNIQUE,
    nivel              SMALLINT    NOT NULL UNIQUE,
    accion_recomendada TEXT        NOT NULL
);

CREATE TABLE conocimiento.hipotesis (
    id_hipotesis SMALLINT     PRIMARY KEY,
    nombre       VARCHAR(100) NOT NULL UNIQUE,
    descripcion  TEXT         NOT NULL
);

CREATE TABLE conocimiento.hecho (
    id_hecho      SMALLINT    PRIMARY KEY,
    atributo      VARCHAR(50) NOT NULL,
    valor         VARCHAR(20) NOT NULL,
    descripcion   TEXT        NOT NULL,
    fuente_tipica VARCHAR(20) NOT NULL
        CHECK (fuente_tipica IN ('respuesta_usuario','consulta_bd','valor_defecto')),
    UNIQUE (atributo, valor)
);

CREATE TABLE conocimiento.regla (
    id_regla           CHAR(3)  PRIMARY KEY,
    id_hipotesis       SMALLINT NOT NULL UNIQUE REFERENCES conocimiento.hipotesis(id_hipotesis),
    id_prioridad       SMALLINT NOT NULL REFERENCES conocimiento.prioridad(id_prioridad),
    id_experto         SMALLINT NOT NULL REFERENCES conocimiento.experto(id_experto),
    accion_recomendada TEXT     NOT NULL,
    fecha_registro     DATE     NOT NULL
);

-- Tabla débil: no tiene identificador propio; su llave es la
-- combinación de las llaves de regla y hecho.
CREATE TABLE conocimiento.regla_premisa (
    id_regla CHAR(3)  NOT NULL REFERENCES conocimiento.regla(id_regla) ON DELETE CASCADE,
    id_hecho SMALLINT NOT NULL REFERENCES conocimiento.hecho(id_hecho),
    orden    SMALLINT NOT NULL CHECK (orden > 0),
    PRIMARY KEY (id_regla, id_hecho),
    UNIQUE (id_regla, orden)
);

-- Parámetros del motor probabilístico (prior y fiabilidad por hipótesis).
-- Son valores iniciales heurísticos, editables por el ingeniero del conocimiento.
CREATE TABLE conocimiento.parametro_inferencia (
    id_hipotesis SMALLINT      PRIMARY KEY REFERENCES conocimiento.hipotesis(id_hipotesis),
    prior        NUMERIC(6,5)  NOT NULL CHECK (prior > 0 AND prior < 1),
    fiabilidad   NUMERIC(4,3)  NOT NULL CHECK (fiabilidad > 0.5 AND fiabilidad < 1),
    version      SMALLINT      NOT NULL DEFAULT 1,
    nota         VARCHAR(120)  NOT NULL DEFAULT 'valor inicial heurístico; calibrar con incidentes etiquetados'
);

CREATE TABLE conocimiento.nodo_arbol (
    id_nodo  VARCHAR(5)  PRIMARY KEY,
    atributo VARCHAR(50) NOT NULL,
    pregunta TEXT        NOT NULL
);

CREATE TABLE conocimiento.rama (
    id_rama         SMALLINT   PRIMARY KEY,
    id_nodo_origen  VARCHAR(5) NOT NULL REFERENCES conocimiento.nodo_arbol(id_nodo),
    id_hecho        SMALLINT   NOT NULL REFERENCES conocimiento.hecho(id_hecho),
    id_nodo_destino VARCHAR(5) REFERENCES conocimiento.nodo_arbol(id_nodo),
    id_hipotesis    SMALLINT   REFERENCES conocimiento.hipotesis(id_hipotesis),
    UNIQUE (id_nodo_origen, id_hecho),
    CHECK ((id_nodo_destino IS NULL) <> (id_hipotesis IS NULL))
);

-- ---------------------------------------------------------------------
-- MÓDULO 2: SISTEMA TRANSACCIONAL (citas de atención sistema-usuario)
-- ---------------------------------------------------------------------
CREATE TABLE transaccional.rol (
    id_rol      SMALLINT    PRIMARY KEY,
    nombre      VARCHAR(40) NOT NULL UNIQUE,
    descripcion TEXT        NOT NULL
);

CREATE TABLE transaccional.usuario (
    id_usuario        INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre            VARCHAR(100) NOT NULL,
    correo            VARCHAR(120) NOT NULL UNIQUE,
    clave_hash        VARCHAR(100) NOT NULL,
    id_rol            SMALLINT     NOT NULL REFERENCES transaccional.rol(id_rol),
    intentos_fallidos SMALLINT     NOT NULL DEFAULT 0,
    activo            BOOLEAN      NOT NULL DEFAULT TRUE,
    fecha_creacion    TIMESTAMP    NOT NULL DEFAULT now()
);

-- Cita: cada atención del sistema experto a un analista
CREATE TABLE transaccional.cita (
    id_cita                INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_usuario             INTEGER     NOT NULL REFERENCES transaccional.usuario(id_usuario),
    fecha_inicio           TIMESTAMP   NOT NULL DEFAULT now(),
    fecha_fin              TIMESTAMP,
    descripcion_caso       TEXT,
    estado                 VARCHAR(15) NOT NULL DEFAULT 'en_curso'
        CHECK (estado IN ('en_curso','finalizada','confirmada','corregida')),
    id_hipotesis_resultado SMALLINT REFERENCES conocimiento.hipotesis(id_hipotesis),
    id_prioridad_resultado SMALLINT REFERENCES conocimiento.prioridad(id_prioridad)
);

-- Memoria de trabajo: hechos afirmados durante la cita
CREATE TABLE transaccional.hecho_cita (
    id_cita    INTEGER     NOT NULL REFERENCES transaccional.cita(id_cita),
    id_hecho   SMALLINT    NOT NULL REFERENCES conocimiento.hecho(id_hecho),
    origen     VARCHAR(20) NOT NULL
        CHECK (origen IN ('respuesta_usuario','consulta_bd','valor_defecto')),
    id_nodo    VARCHAR(5) REFERENCES conocimiento.nodo_arbol(id_nodo),
    fecha_hora TIMESTAMP   NOT NULL DEFAULT now(),
    PRIMARY KEY (id_cita, id_hecho)
);

-- Preguntas que el analista no pudo responder («No sé»): se tratan como desconocidas.
CREATE TABLE transaccional.omision_cita (
    id_cita    INTEGER    NOT NULL REFERENCES transaccional.cita(id_cita),
    id_nodo    VARCHAR(5) NOT NULL REFERENCES conocimiento.nodo_arbol(id_nodo),
    fecha_hora TIMESTAMP  NOT NULL DEFAULT now(),
    PRIMARY KEY (id_cita, id_nodo)
);

-- Resultado de la cita: las cinco hipótesis con su contador y su peso
CREATE TABLE transaccional.resultado_hipotesis (
    id_cita         INTEGER      NOT NULL REFERENCES transaccional.cita(id_cita),
    id_hipotesis    SMALLINT     NOT NULL REFERENCES conocimiento.hipotesis(id_hipotesis),
    posicion        SMALLINT     NOT NULL CHECK (posicion BETWEEN 1 AND 5),
    contador        SMALLINT     NOT NULL CHECK (contador >= 0),
    contradicciones SMALLINT     NOT NULL CHECK (contradicciones >= 0),
    peso            NUMERIC(6,3) NOT NULL CHECK (peso BETWEEN 0 AND 100),
    PRIMARY KEY (id_cita, id_hipotesis),
    UNIQUE (id_cita, posicion)
);

-- Retroalimentación guardada: el analista confirma o corrige el
-- resultado de la cita; el ingeniero del conocimiento la revisa.
CREATE TABLE transaccional.retroalimentacion (
    id_retroalimentacion   INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_cita                INTEGER     NOT NULL UNIQUE REFERENCES transaccional.cita(id_cita),
    id_usuario             INTEGER     NOT NULL REFERENCES transaccional.usuario(id_usuario),
    resultado              VARCHAR(10) NOT NULL CHECK (resultado IN ('confirmada','corregida')),
    id_hipotesis_corregida SMALLINT    REFERENCES conocimiento.hipotesis(id_hipotesis),
    comentario             TEXT,
    revisada               BOOLEAN     NOT NULL DEFAULT FALSE,
    fecha_hora             TIMESTAMP   NOT NULL DEFAULT now(),
    CHECK ((resultado = 'corregida') = (id_hipotesis_corregida IS NOT NULL))
);

CREATE TABLE transaccional.bitacora (
    id_evento  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_usuario INTEGER     REFERENCES transaccional.usuario(id_usuario),
    accion     VARCHAR(40) NOT NULL,
    detalle    TEXT,
    fecha_hora TIMESTAMP   NOT NULL DEFAULT now()
);


-- ---------------------------------------------------------------------
-- CARGA DEL CONOCIMIENTO DEL EXPERTO HUMANO (Coordinador del SOC)
-- ---------------------------------------------------------------------
INSERT INTO conocimiento.experto VALUES (1,'Coordinador del Centro de Operaciones de Seguridad (SOC)','Coordinador del SOC','Entrevista semiestructurada del 3 de marzo de 2026');
INSERT INTO conocimiento.prioridad VALUES (1,'Baja',1,'Registrar el incidente y monitorear; sin acción inmediata.');
INSERT INTO conocimiento.prioridad VALUES (2,'Media',2,'Atender dentro del turno; verificar el indicador y aplicar la contención básica.');
INSERT INTO conocimiento.prioridad VALUES (3,'Alta',3,'Atender de inmediato; aislar el activo afectado y notificar al responsable de seguridad.');
INSERT INTO conocimiento.prioridad VALUES (4,'Crítica',4,'Escalar de inmediato; activar el protocolo de respuesta a incidentes y preservar evidencia.');
INSERT INTO conocimiento.hipotesis VALUES (1,'Phishing','Correo masivo y genérico que busca engañar al usuario para obtener credenciales o inducirlo a abrir enlaces o adjuntos maliciosos.');
INSERT INTO conocimiento.hipotesis VALUES (2,'Spear phishing','Correo dirigido y personalizado (nombre, cargo o proyecto interno) hacia una persona o grupo específico.');
INSERT INTO conocimiento.hipotesis VALUES (3,'Ransomware','Malware que cifra los archivos de la víctima y exige un rescate para restaurar el acceso.');
INSERT INTO conocimiento.hipotesis VALUES (4,'Malware genérico','Software malicioso sin un comportamiento específico identificado.');
INSERT INTO conocimiento.hipotesis VALUES (5,'Spyware','Software que recolecta información del usuario y la envía periódicamente a un destino externo.');
INSERT INTO conocimiento.hipotesis VALUES (6,'Troyano','Programa camuflado como legítimo que habilita el acceso remoto del atacante.');
INSERT INTO conocimiento.hipotesis VALUES (7,'Gusano informático (Worm)','Malware que se autorreplica y se propaga por la red sin intervención del usuario.');
INSERT INTO conocimiento.hipotesis VALUES (8,'Denegación de servicio (DoS)','Agotamiento de los recursos de un servicio mediante solicitudes repetidas desde un único origen.');
INSERT INTO conocimiento.hipotesis VALUES (9,'Denegación de servicio distribuido (DDoS)','Saturación coordinada de un servicio desde múltiples orígenes simultáneos.');
INSERT INTO conocimiento.hipotesis VALUES (10,'Ataque de fuerza bruta','Intentos repetidos de autenticación para adivinar credenciales.');
INSERT INTO conocimiento.hipotesis VALUES (11,'Inyección SQL','Entradas manipuladas que alteran las consultas a la base de datos de una aplicación web.');
INSERT INTO conocimiento.hipotesis VALUES (12,'Cross-Site Scripting (XSS)','Inyección de scripts que se ejecutan en el navegador de otros usuarios.');
INSERT INTO conocimiento.hipotesis VALUES (13,'Cross-Site Request Forgery (CSRF)','Solicitudes no deseadas ejecutadas con la sesión autenticada de la víctima.');
INSERT INTO conocimiento.hipotesis VALUES (14,'Ataque de intermediario (Man-in-the-Middle)','Interceptación o alteración de la comunicación entre dos partes.');
INSERT INTO conocimiento.hipotesis VALUES (15,'Fuga de datos / exfiltración de información','Transferencia no autorizada de información sensible hacia el exterior.');
INSERT INTO conocimiento.hipotesis VALUES (16,'Ingeniería social','Manipulación de personas, reportada por el usuario, para obtener información o acciones indebidas.');
INSERT INTO conocimiento.hipotesis VALUES (17,'Suplantación de identidad (Spoofing)','Falsificación de identidad o de dirección para hacerse pasar por una entidad legítima.');
INSERT INTO conocimiento.hipotesis VALUES (18,'Explotación de vulnerabilidad Zero-day','Explotación de una vulnerabilidad sin parche conocido.');
INSERT INTO conocimiento.hipotesis VALUES (19,'Acceso no autorizado / escalamiento de privilegios','Acceso a recursos o privilegios sin autorización, sin otro indicador específico.');
INSERT INTO conocimiento.hipotesis VALUES (20,'Robo o relleno de credenciales (Credential stuffing)','Uso de credenciales filtradas previamente para acceder a cuentas.');
INSERT INTO conocimiento.hipotesis VALUES (21,'Rootkit','Software que oculta su presencia y conserva privilegios de sistema.');
INSERT INTO conocimiento.hipotesis VALUES (22,'Equipo comprometido / Botnet','Equipo comprometido que participa en una red de orígenes coordinados.');
INSERT INTO conocimiento.hipotesis VALUES (23,'Ataque a la cadena de suministro (Supply chain attack)','Compromiso de un componente o proveedor externo del que depende la organización.');
INSERT INTO conocimiento.hipotesis VALUES (24,'Secuestro de sesión (Session hijacking)','Robo de una cookie o token para tomar el control de una sesión activa.');
INSERT INTO conocimiento.hipotesis VALUES (25,'Configuración insegura / exposición de servicios','Servicios expuestos o mal configurados que amplían la superficie de ataque.');
INSERT INTO conocimiento.hecho VALUES (1,'vector','correo','El incidente ingresa por el vector «Correo o mensaje».','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (2,'vector','archivo_proceso','El incidente ingresa por el vector «Archivo o proceso anómalo».','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (3,'vector','trafico_red','El incidente ingresa por el vector «Tráfico de red».','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (4,'vector','autenticacion','El incidente ingresa por el vector «Autenticación».','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (5,'vector','app_web','El incidente ingresa por el vector «Aplicación web».','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (6,'vector','infraestructura','El incidente ingresa por el vector «Configuración o infraestructura».','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (7,'vector','reporte_usuario','El incidente ingresa por el vector «Reporte de usuario».','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (8,'mensaje_dirigido','verdadero','¿Mensaje dirigido y personalizado? Respuesta: Sí.','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (9,'mensaje_dirigido','falso','¿Mensaje dirigido y personalizado? Respuesta: No.','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (10,'archivos_cifrados_rescate','verdadero','¿Archivos cifrados y piden rescate? Respuesta: Sí.','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (11,'archivos_cifrados_rescate','falso','¿Archivos cifrados y piden rescate? Respuesta: No.','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (12,'autorreplicacion_red','verdadero','¿Se replica solo por la red? Respuesta: Sí.','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (13,'autorreplicacion_red','falso','¿Se replica solo por la red? Respuesta: No.','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (14,'privilegios_sistema_ocultos','verdadero','¿Privilegios de sistema y oculto? Respuesta: Sí.','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (15,'privilegios_sistema_ocultos','falso','¿Privilegios de sistema y oculto? Respuesta: No.','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (16,'exfiltracion_periodica_usuario','verdadero','¿Envía datos del usuario al exterior? Respuesta: Sí.','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (17,'exfiltracion_periodica_usuario','falso','¿Envía datos del usuario al exterior? Respuesta: No.','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (18,'camuflaje_acceso_remoto','verdadero','¿Camuflado y con acceso remoto? Respuesta: Sí.','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (19,'camuflaje_acceso_remoto','falso','¿Camuflado y con acceso remoto? Respuesta: No.','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (20,'vulnerabilidad_sin_parche','verdadero','¿Vulnerabilidad sin parche conocido? Respuesta: Sí.','consulta_bd');
INSERT INTO conocimiento.hecho VALUES (21,'vulnerabilidad_sin_parche','falso','¿Vulnerabilidad sin parche conocido? Respuesta: No.','valor_defecto');
INSERT INTO conocimiento.hecho VALUES (22,'origenes_multiples_coordinados','verdadero','¿Múltiples orígenes coordinados? Respuesta: Sí.','consulta_bd');
INSERT INTO conocimiento.hecho VALUES (23,'origenes_multiples_coordinados','falso','¿Múltiples orígenes coordinados? Respuesta: No.','consulta_bd');
INSERT INTO conocimiento.hecho VALUES (24,'objetivo_saturar_servicio','verdadero','¿Objetivo: saturar el servicio? Respuesta: Sí.','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (25,'objetivo_saturar_servicio','falso','¿Objetivo: saturar el servicio? Respuesta: No.','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (26,'solicitudes_repetidas_agotan_recursos','verdadero','¿Solicitudes repetidas de un origen? Respuesta: Sí.','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (27,'solicitudes_repetidas_agotan_recursos','falso','¿Solicitudes repetidas de un origen? Respuesta: No.','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (28,'interceptacion_comunicacion','verdadero','¿Intercepta la comunicación? Respuesta: Sí.','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (29,'interceptacion_comunicacion','falso','¿Intercepta la comunicación? Respuesta: No.','valor_defecto');
INSERT INTO conocimiento.hecho VALUES (30,'intentos_fallidos_repetidos','verdadero','¿Intentos fallidos repetidos? Respuesta: Sí.','consulta_bd');
INSERT INTO conocimiento.hecho VALUES (31,'intentos_fallidos_repetidos','falso','¿Intentos fallidos repetidos? Respuesta: No.','consulta_bd');
INSERT INTO conocimiento.hecho VALUES (32,'credenciales_filtracion_previa','verdadero','¿Credenciales de filtración previa? Respuesta: Sí.','consulta_bd');
INSERT INTO conocimiento.hecho VALUES (33,'credenciales_filtracion_previa','falso','¿Credenciales de filtración previa? Respuesta: No.','consulta_bd');
INSERT INTO conocimiento.hecho VALUES (34,'robo_cookie_token_sesion','verdadero','¿Robo de cookie o token de sesión? Respuesta: Sí.','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (35,'robo_cookie_token_sesion','falso','¿Robo de cookie o token de sesión? Respuesta: No.','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (36,'suplantacion_identidad','verdadero','¿Suplanta identidad o dirección? Respuesta: Sí.','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (37,'suplantacion_identidad','falso','¿Suplanta identidad o dirección? Respuesta: No.','valor_defecto');
INSERT INTO conocimiento.hecho VALUES (38,'entrada_manipula_bd','verdadero','¿La entrada manipula la base de datos? Respuesta: Sí.','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (39,'entrada_manipula_bd','falso','¿La entrada manipula la base de datos? Respuesta: No.','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (40,'script_ejecuta_navegador','verdadero','¿Script en el navegador de otros? Respuesta: Sí.','respuesta_usuario');
INSERT INTO conocimiento.hecho VALUES (41,'script_ejecuta_navegador','falso','¿Script en el navegador de otros? Respuesta: No.','valor_defecto');
INSERT INTO conocimiento.hecho VALUES (42,'componente_externo_comprometido','verdadero','¿Componente externo comprometido? Respuesta: Sí.','consulta_bd');
INSERT INTO conocimiento.hecho VALUES (43,'componente_externo_comprometido','falso','¿Componente externo comprometido? Respuesta: No.','valor_defecto');
INSERT INTO conocimiento.regla VALUES ('R01',2,3,1,'Retener el correo, verificar al remitente por un canal alternativo y revisar las cuentas afectadas.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R02',1,2,1,'Bloquear o retener el mensaje sospechoso, verificar la URL y advertir a los usuarios potencialmente afectados.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R03',3,4,1,'Aislar el equipo afectado, preservar evidencia y activar el protocolo de respuesta a incidentes.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R04',7,3,1,'Contener los segmentos afectados y bloquear indicadores de propagación.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R05',21,4,1,'Aislar el host y realizar análisis forense desde un medio confiable.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R06',5,3,1,'Aislar el host, revisar mecanismos de persistencia y cambiar credenciales posiblemente expuestas.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R07',6,3,1,'Aislar el equipo, detener la ejecución sospechosa y analizar las conexiones asociadas.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R08',18,4,1,'Aislar el activo vulnerable y aplicar mitigaciones recomendadas por el fabricante.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R09',4,2,1,'Aislar el host si hay actividad activa y ejecutar un análisis antimalware controlado.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R10',9,3,1,'Activar mitigación DDoS y coordinar la respuesta con el proveedor de red.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R11',22,3,1,'Aislar el equipo y bloquear indicadores de mando y control asociados.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R12',8,2,1,'Aplicar límites de tasa y comprobar la disponibilidad del servicio.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R13',14,3,1,'Validar certificados, revisar la red y renovar credenciales potencialmente expuestas.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R14',15,4,1,'Contener la transferencia, preservar registros y activar el protocolo de protección de datos.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R15',10,2,1,'Aplicar bloqueo progresivo, exigir MFA y revisar los registros de autenticación.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R16',20,3,1,'Cambiar las credenciales expuestas, invalidar sesiones y habilitar MFA.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R17',24,3,1,'Invalidar sesiones y tokens comprometidos y revisar el dispositivo de origen.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R18',17,2,1,'Validar el origen y aplicar los controles de autenticación del protocolo correspondiente.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R19',19,3,1,'Revocar sesiones sospechosas, revisar privilegios y conservar evidencia de auditoría.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R20',11,3,1,'Bloquear el patrón detectado, revisar consultas parametrizadas y analizar los registros de aplicación.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R21',12,2,1,'Aplicar codificación contextual de salida, sanear entradas y revisar la aplicación afectada.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R22',13,2,1,'Validar tokens anti-CSRF y los atributos de seguridad de las cookies.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R23',23,4,1,'Suspender el componente afectado y verificar la integridad de dependencias y proveedores.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R24',25,2,1,'Restringir la exposición y aplicar una configuración segura validada.','2026-03-03');
INSERT INTO conocimiento.regla VALUES ('R25',16,2,1,'Verificar el reporte, alertar a usuarios afectados y reforzar la validación por canal alternativo.','2026-03-03');
INSERT INTO conocimiento.regla_premisa VALUES ('R01',1,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R01',8,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R02',1,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R02',9,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R03',2,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R03',10,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R04',2,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R04',11,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R04',12,3);
INSERT INTO conocimiento.regla_premisa VALUES ('R05',2,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R05',11,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R05',13,3);
INSERT INTO conocimiento.regla_premisa VALUES ('R05',14,4);
INSERT INTO conocimiento.regla_premisa VALUES ('R06',2,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R06',11,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R06',13,3);
INSERT INTO conocimiento.regla_premisa VALUES ('R06',15,4);
INSERT INTO conocimiento.regla_premisa VALUES ('R06',16,5);
INSERT INTO conocimiento.regla_premisa VALUES ('R07',2,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R07',11,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R07',13,3);
INSERT INTO conocimiento.regla_premisa VALUES ('R07',15,4);
INSERT INTO conocimiento.regla_premisa VALUES ('R07',17,5);
INSERT INTO conocimiento.regla_premisa VALUES ('R07',18,6);
INSERT INTO conocimiento.regla_premisa VALUES ('R08',2,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R08',11,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R08',13,3);
INSERT INTO conocimiento.regla_premisa VALUES ('R08',15,4);
INSERT INTO conocimiento.regla_premisa VALUES ('R08',17,5);
INSERT INTO conocimiento.regla_premisa VALUES ('R08',19,6);
INSERT INTO conocimiento.regla_premisa VALUES ('R08',20,7);
INSERT INTO conocimiento.regla_premisa VALUES ('R09',2,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R09',11,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R09',13,3);
INSERT INTO conocimiento.regla_premisa VALUES ('R09',15,4);
INSERT INTO conocimiento.regla_premisa VALUES ('R09',17,5);
INSERT INTO conocimiento.regla_premisa VALUES ('R09',19,6);
INSERT INTO conocimiento.regla_premisa VALUES ('R09',21,7);
INSERT INTO conocimiento.regla_premisa VALUES ('R10',3,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R10',22,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R10',24,3);
INSERT INTO conocimiento.regla_premisa VALUES ('R11',3,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R11',22,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R11',25,3);
INSERT INTO conocimiento.regla_premisa VALUES ('R12',3,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R12',23,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R12',26,3);
INSERT INTO conocimiento.regla_premisa VALUES ('R13',3,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R13',23,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R13',27,3);
INSERT INTO conocimiento.regla_premisa VALUES ('R13',28,4);
INSERT INTO conocimiento.regla_premisa VALUES ('R14',3,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R14',23,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R14',27,3);
INSERT INTO conocimiento.regla_premisa VALUES ('R14',29,4);
INSERT INTO conocimiento.regla_premisa VALUES ('R15',4,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R15',30,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R16',4,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R16',31,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R16',32,3);
INSERT INTO conocimiento.regla_premisa VALUES ('R17',4,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R17',31,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R17',33,3);
INSERT INTO conocimiento.regla_premisa VALUES ('R17',34,4);
INSERT INTO conocimiento.regla_premisa VALUES ('R18',4,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R18',31,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R18',33,3);
INSERT INTO conocimiento.regla_premisa VALUES ('R18',35,4);
INSERT INTO conocimiento.regla_premisa VALUES ('R18',36,5);
INSERT INTO conocimiento.regla_premisa VALUES ('R19',4,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R19',31,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R19',33,3);
INSERT INTO conocimiento.regla_premisa VALUES ('R19',35,4);
INSERT INTO conocimiento.regla_premisa VALUES ('R19',37,5);
INSERT INTO conocimiento.regla_premisa VALUES ('R20',5,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R20',38,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R21',5,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R21',39,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R21',40,3);
INSERT INTO conocimiento.regla_premisa VALUES ('R22',5,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R22',39,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R22',41,3);
INSERT INTO conocimiento.regla_premisa VALUES ('R23',6,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R23',42,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R24',6,1);
INSERT INTO conocimiento.regla_premisa VALUES ('R24',43,2);
INSERT INTO conocimiento.regla_premisa VALUES ('R25',7,1);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (1,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (2,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (3,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (4,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (5,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (6,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (7,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (8,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (9,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (10,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (11,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (12,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (13,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (14,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (15,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (16,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (17,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (18,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (19,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (20,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (21,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (22,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (23,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (24,0.04000,0.900);
INSERT INTO conocimiento.parametro_inferencia (id_hipotesis, prior, fiabilidad) VALUES (25,0.04000,0.900);
INSERT INTO conocimiento.nodo_arbol VALUES ('N0','vector','¿Cuál es el vector principal del incidente?');
INSERT INTO conocimiento.nodo_arbol VALUES ('N1','mensaje_dirigido','¿Mensaje dirigido y personalizado?');
INSERT INTO conocimiento.nodo_arbol VALUES ('N2','archivos_cifrados_rescate','¿Archivos cifrados y piden rescate?');
INSERT INTO conocimiento.nodo_arbol VALUES ('N2.1','autorreplicacion_red','¿Se replica solo por la red?');
INSERT INTO conocimiento.nodo_arbol VALUES ('N2.2','privilegios_sistema_ocultos','¿Privilegios de sistema y oculto?');
INSERT INTO conocimiento.nodo_arbol VALUES ('N2.3','exfiltracion_periodica_usuario','¿Envía datos del usuario al exterior?');
INSERT INTO conocimiento.nodo_arbol VALUES ('N2.4','camuflaje_acceso_remoto','¿Camuflado y con acceso remoto?');
INSERT INTO conocimiento.nodo_arbol VALUES ('N2.5','vulnerabilidad_sin_parche','¿Vulnerabilidad sin parche conocido?');
INSERT INTO conocimiento.nodo_arbol VALUES ('N3','origenes_multiples_coordinados','¿Múltiples orígenes coordinados?');
INSERT INTO conocimiento.nodo_arbol VALUES ('N3.1','objetivo_saturar_servicio','¿Objetivo: saturar el servicio?');
INSERT INTO conocimiento.nodo_arbol VALUES ('N3.2','solicitudes_repetidas_agotan_recursos','¿Solicitudes repetidas de un origen?');
INSERT INTO conocimiento.nodo_arbol VALUES ('N3.3','interceptacion_comunicacion','¿Intercepta la comunicación?');
INSERT INTO conocimiento.nodo_arbol VALUES ('N4','intentos_fallidos_repetidos','¿Intentos fallidos repetidos?');
INSERT INTO conocimiento.nodo_arbol VALUES ('N4.1','credenciales_filtracion_previa','¿Credenciales de filtración previa?');
INSERT INTO conocimiento.nodo_arbol VALUES ('N4.2','robo_cookie_token_sesion','¿Robo de cookie o token de sesión?');
INSERT INTO conocimiento.nodo_arbol VALUES ('N4.3','suplantacion_identidad','¿Suplanta identidad o dirección?');
INSERT INTO conocimiento.nodo_arbol VALUES ('N5','entrada_manipula_bd','¿La entrada manipula la base de datos?');
INSERT INTO conocimiento.nodo_arbol VALUES ('N5.1','script_ejecuta_navegador','¿Script en el navegador de otros?');
INSERT INTO conocimiento.nodo_arbol VALUES ('N6','componente_externo_comprometido','¿Componente externo comprometido?');
INSERT INTO conocimiento.rama VALUES (1,'N0',1,'N1',NULL);
INSERT INTO conocimiento.rama VALUES (2,'N0',2,'N2',NULL);
INSERT INTO conocimiento.rama VALUES (3,'N0',3,'N3',NULL);
INSERT INTO conocimiento.rama VALUES (4,'N0',4,'N4',NULL);
INSERT INTO conocimiento.rama VALUES (5,'N0',5,'N5',NULL);
INSERT INTO conocimiento.rama VALUES (6,'N0',6,'N6',NULL);
INSERT INTO conocimiento.rama VALUES (7,'N0',7,NULL,16);
INSERT INTO conocimiento.rama VALUES (8,'N1',8,NULL,2);
INSERT INTO conocimiento.rama VALUES (9,'N1',9,NULL,1);
INSERT INTO conocimiento.rama VALUES (10,'N2',10,NULL,3);
INSERT INTO conocimiento.rama VALUES (11,'N2',11,'N2.1',NULL);
INSERT INTO conocimiento.rama VALUES (12,'N2.1',12,NULL,7);
INSERT INTO conocimiento.rama VALUES (13,'N2.1',13,'N2.2',NULL);
INSERT INTO conocimiento.rama VALUES (14,'N2.2',14,NULL,21);
INSERT INTO conocimiento.rama VALUES (15,'N2.2',15,'N2.3',NULL);
INSERT INTO conocimiento.rama VALUES (16,'N2.3',16,NULL,5);
INSERT INTO conocimiento.rama VALUES (17,'N2.3',17,'N2.4',NULL);
INSERT INTO conocimiento.rama VALUES (18,'N2.4',18,NULL,6);
INSERT INTO conocimiento.rama VALUES (19,'N2.4',19,'N2.5',NULL);
INSERT INTO conocimiento.rama VALUES (20,'N2.5',20,NULL,18);
INSERT INTO conocimiento.rama VALUES (21,'N2.5',21,NULL,4);
INSERT INTO conocimiento.rama VALUES (22,'N3',22,'N3.1',NULL);
INSERT INTO conocimiento.rama VALUES (23,'N3',23,'N3.2',NULL);
INSERT INTO conocimiento.rama VALUES (24,'N3.1',24,NULL,9);
INSERT INTO conocimiento.rama VALUES (25,'N3.1',25,NULL,22);
INSERT INTO conocimiento.rama VALUES (26,'N3.2',26,NULL,8);
INSERT INTO conocimiento.rama VALUES (27,'N3.2',27,'N3.3',NULL);
INSERT INTO conocimiento.rama VALUES (28,'N3.3',28,NULL,14);
INSERT INTO conocimiento.rama VALUES (29,'N3.3',29,NULL,15);
INSERT INTO conocimiento.rama VALUES (30,'N4',30,NULL,10);
INSERT INTO conocimiento.rama VALUES (31,'N4',31,'N4.1',NULL);
INSERT INTO conocimiento.rama VALUES (32,'N4.1',32,NULL,20);
INSERT INTO conocimiento.rama VALUES (33,'N4.1',33,'N4.2',NULL);
INSERT INTO conocimiento.rama VALUES (34,'N4.2',34,NULL,24);
INSERT INTO conocimiento.rama VALUES (35,'N4.2',35,'N4.3',NULL);
INSERT INTO conocimiento.rama VALUES (36,'N4.3',36,NULL,17);
INSERT INTO conocimiento.rama VALUES (37,'N4.3',37,NULL,19);
INSERT INTO conocimiento.rama VALUES (38,'N5',38,NULL,11);
INSERT INTO conocimiento.rama VALUES (39,'N5',39,'N5.1',NULL);
INSERT INTO conocimiento.rama VALUES (40,'N5.1',40,NULL,12);
INSERT INTO conocimiento.rama VALUES (41,'N5.1',41,NULL,13);
INSERT INTO conocimiento.rama VALUES (42,'N6',42,NULL,23);
INSERT INTO conocimiento.rama VALUES (43,'N6',43,NULL,25);

INSERT INTO transaccional.rol VALUES (1,'Analista SOC','Usuario final: abre citas, responde las preguntas, recibe el ranking y registra la retroalimentación.');
INSERT INTO transaccional.rol VALUES (2,'Ingeniero del conocimiento','Mantiene la base de conocimiento y revisa la retroalimentación guardada.');
INSERT INTO transaccional.rol VALUES (3,'Administrador del sistema','Administra usuarios, roles y consulta la bitácora de auditoría.');
-- Usuarios de prueba (clave con hash bcrypt de costo 10 mediante pgcrypto)
INSERT INTO transaccional.usuario (nombre, correo, clave_hash, id_rol) VALUES ('Ana Analista','analista@umb-soc.test',crypt('Analista#2026',gen_salt('bf',10)),1);
INSERT INTO transaccional.usuario (nombre, correo, clave_hash, id_rol) VALUES ('Iván Ingeniero','ingeniero@umb-soc.test',crypt('Ingeniero#2026',gen_salt('bf',10)),2);
INSERT INTO transaccional.usuario (nombre, correo, clave_hash, id_rol) VALUES ('Adriana Admin','admin@umb-soc.test',crypt('Admin#2026',gen_salt('bf',10)),3);

-- ---------------------------------------------------------------------
-- ROLES DEL SGBD Y PRIVILEGIOS (mínimo privilegio)
-- ---------------------------------------------------------------------
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='rol_analista_soc')      THEN CREATE ROLE rol_analista_soc NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='rol_ing_conocimiento')  THEN CREATE ROLE rol_ing_conocimiento NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='rol_admin_sistema')     THEN CREATE ROLE rol_admin_sistema NOLOGIN; END IF;
END $$;
GRANT USAGE ON SCHEMA conocimiento, transaccional TO rol_analista_soc, rol_ing_conocimiento, rol_admin_sistema;

-- Analista SOC
GRANT SELECT ON ALL TABLES IN SCHEMA conocimiento TO rol_analista_soc;
GRANT SELECT, INSERT, UPDATE ON transaccional.cita TO rol_analista_soc;
GRANT SELECT, INSERT ON transaccional.hecho_cita, transaccional.omision_cita,
      transaccional.resultado_hipotesis, transaccional.retroalimentacion TO rol_analista_soc;
GRANT INSERT ON transaccional.bitacora TO rol_analista_soc;

-- Ingeniero del conocimiento
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA conocimiento TO rol_ing_conocimiento;
GRANT SELECT ON transaccional.cita, transaccional.hecho_cita, transaccional.omision_cita,
      transaccional.resultado_hipotesis, transaccional.retroalimentacion TO rol_ing_conocimiento;
GRANT UPDATE (revisada) ON transaccional.retroalimentacion TO rol_ing_conocimiento;
GRANT INSERT ON transaccional.bitacora TO rol_ing_conocimiento;

-- Administrador del sistema
GRANT SELECT ON ALL TABLES IN SCHEMA conocimiento TO rol_admin_sistema;
GRANT SELECT, INSERT, UPDATE ON transaccional.usuario TO rol_admin_sistema;
GRANT SELECT ON transaccional.rol, transaccional.bitacora TO rol_admin_sistema;
GRANT INSERT ON transaccional.bitacora TO rol_admin_sistema;


-- ---------------------------------------------------------------------
-- DATOS DE PRUEBA DEL SISTEMA TRANSACCIONAL (5 citas, 2 retroalimentaciones)
-- ---------------------------------------------------------------------
INSERT INTO transaccional.bitacora (id_evento, id_usuario, accion, detalle, fecha_hora) OVERRIDING SYSTEM VALUE VALUES (1, 1, 'login_ok', NULL, '2026-11-10 22:23:52.676944');
INSERT INTO transaccional.bitacora (id_evento, id_usuario, accion, detalle, fecha_hora) OVERRIDING SYSTEM VALUE VALUES (2, 1, 'cita_abierta', 'cita 1', '2026-11-10 22:23:52.681089');
INSERT INTO transaccional.bitacora (id_evento, id_usuario, accion, detalle, fecha_hora) OVERRIDING SYSTEM VALUE VALUES (3, 1, 'cita_cerrada', 'cita 1: Spear phishing', '2026-11-10 22:23:52.697856');
INSERT INTO transaccional.bitacora (id_evento, id_usuario, accion, detalle, fecha_hora) OVERRIDING SYSTEM VALUE VALUES (4, 1, 'cita_abierta', 'cita 2', '2026-11-10 22:23:52.700103');
INSERT INTO transaccional.bitacora (id_evento, id_usuario, accion, detalle, fecha_hora) OVERRIDING SYSTEM VALUE VALUES (5, 1, 'cita_cerrada', 'cita 2: Ransomware', '2026-11-10 22:23:52.713486');
INSERT INTO transaccional.bitacora (id_evento, id_usuario, accion, detalle, fecha_hora) OVERRIDING SYSTEM VALUE VALUES (6, 1, 'cita_abierta', 'cita 3', '2026-11-10 22:23:52.714766');
INSERT INTO transaccional.bitacora (id_evento, id_usuario, accion, detalle, fecha_hora) OVERRIDING SYSTEM VALUE VALUES (7, 1, 'cita_cerrada', 'cita 3: Fuga de datos / exfiltración de información', '2026-11-10 22:23:52.724867');
INSERT INTO transaccional.bitacora (id_evento, id_usuario, accion, detalle, fecha_hora) OVERRIDING SYSTEM VALUE VALUES (8, 1, 'cita_abierta', 'cita 4', '2026-11-10 22:23:52.726309');
INSERT INTO transaccional.bitacora (id_evento, id_usuario, accion, detalle, fecha_hora) OVERRIDING SYSTEM VALUE VALUES (9, 1, 'cita_cerrada', 'cita 4: Ataque de fuerza bruta', '2026-11-10 22:23:52.735606');
INSERT INTO transaccional.bitacora (id_evento, id_usuario, accion, detalle, fecha_hora) OVERRIDING SYSTEM VALUE VALUES (10, 1, 'cita_abierta', 'cita 5', '2026-11-10 22:23:52.737368');
INSERT INTO transaccional.bitacora (id_evento, id_usuario, accion, detalle, fecha_hora) OVERRIDING SYSTEM VALUE VALUES (11, 1, 'cita_cerrada', 'cita 5: Cross-Site Scripting (XSS)', '2026-11-10 22:23:52.74864');
INSERT INTO transaccional.bitacora (id_evento, id_usuario, accion, detalle, fecha_hora) OVERRIDING SYSTEM VALUE VALUES (12, 1, 'retroalimentacion', 'cita 2', '2026-11-10 22:23:52.752346');
INSERT INTO transaccional.bitacora (id_evento, id_usuario, accion, detalle, fecha_hora) OVERRIDING SYSTEM VALUE VALUES (13, 1, 'retroalimentacion', 'cita 5', '2026-11-10 22:23:52.75463');
INSERT INTO transaccional.cita (id_cita, id_usuario, fecha_inicio, fecha_fin, descripcion_caso, estado, id_hipotesis_resultado, id_prioridad_resultado) OVERRIDING SYSTEM VALUE VALUES (1, 1, '2026-11-05 08:10:00', '2026-11-05 08:16:00', 'Correo con el nombre y el cargo del destinatario', 'finalizada', 2, 3);
INSERT INTO transaccional.cita (id_cita, id_usuario, fecha_inicio, fecha_fin, descripcion_caso, estado, id_hipotesis_resultado, id_prioridad_resultado) OVERRIDING SYSTEM VALUE VALUES (3, 1, '2026-11-05 10:40:00', '2026-11-05 10:46:00', 'Transferencia saliente inusual hacia un servidor externo', 'finalizada', 15, 4);
INSERT INTO transaccional.cita (id_cita, id_usuario, fecha_inicio, fecha_fin, descripcion_caso, estado, id_hipotesis_resultado, id_prioridad_resultado) OVERRIDING SYSTEM VALUE VALUES (4, 1, '2026-11-05 11:05:00', '2026-11-05 11:11:00', 'Múltiples intentos de acceso fallidos a la VPN', 'finalizada', 10, 2);
INSERT INTO transaccional.cita (id_cita, id_usuario, fecha_inicio, fecha_fin, descripcion_caso, estado, id_hipotesis_resultado, id_prioridad_resultado) OVERRIDING SYSTEM VALUE VALUES (2, 1, '2026-11-05 09:25:00', '2026-11-05 09:31:00', 'Equipos con archivos cifrados y nota de rescate', 'confirmada', 3, 4);
INSERT INTO transaccional.cita (id_cita, id_usuario, fecha_inicio, fecha_fin, descripcion_caso, estado, id_hipotesis_resultado, id_prioridad_resultado) OVERRIDING SYSTEM VALUE VALUES (5, 1, '2026-11-05 14:30:00', '2026-11-05 14:36:00', 'Comportamiento extraño en el portal web de la empresa', 'corregida', 12, 2);
INSERT INTO transaccional.hecho_cita (id_cita, id_hecho, origen, id_nodo, fecha_hora) VALUES (1, 1, 'respuesta_usuario', 'N0', '2026-11-10 22:23:52.68164');
INSERT INTO transaccional.hecho_cita (id_cita, id_hecho, origen, id_nodo, fecha_hora) VALUES (1, 8, 'respuesta_usuario', 'N1', '2026-11-10 22:23:52.68463');
INSERT INTO transaccional.hecho_cita (id_cita, id_hecho, origen, id_nodo, fecha_hora) VALUES (2, 2, 'respuesta_usuario', 'N0', '2026-11-10 22:23:52.700627');
INSERT INTO transaccional.hecho_cita (id_cita, id_hecho, origen, id_nodo, fecha_hora) VALUES (2, 10, 'respuesta_usuario', 'N2', '2026-11-10 22:23:52.702');
INSERT INTO transaccional.hecho_cita (id_cita, id_hecho, origen, id_nodo, fecha_hora) VALUES (3, 3, 'respuesta_usuario', 'N0', '2026-11-10 22:23:52.715178');
INSERT INTO transaccional.hecho_cita (id_cita, id_hecho, origen, id_nodo, fecha_hora) VALUES (3, 23, 'consulta_bd', 'N3', '2026-11-10 22:23:52.716207');
INSERT INTO transaccional.hecho_cita (id_cita, id_hecho, origen, id_nodo, fecha_hora) VALUES (3, 27, 'respuesta_usuario', 'N3.2', '2026-11-10 22:23:52.717121');
INSERT INTO transaccional.hecho_cita (id_cita, id_hecho, origen, id_nodo, fecha_hora) VALUES (3, 29, 'valor_defecto', 'N3.3', '2026-11-10 22:23:52.718338');
INSERT INTO transaccional.hecho_cita (id_cita, id_hecho, origen, id_nodo, fecha_hora) VALUES (4, 4, 'respuesta_usuario', 'N0', '2026-11-10 22:23:52.726979');
INSERT INTO transaccional.hecho_cita (id_cita, id_hecho, origen, id_nodo, fecha_hora) VALUES (4, 30, 'consulta_bd', 'N4', '2026-11-10 22:23:52.727729');
INSERT INTO transaccional.hecho_cita (id_cita, id_hecho, origen, id_nodo, fecha_hora) VALUES (5, 5, 'respuesta_usuario', 'N0', '2026-11-10 22:23:52.737877');
INSERT INTO transaccional.hecho_cita (id_cita, id_hecho, origen, id_nodo, fecha_hora) VALUES (5, 39, 'respuesta_usuario', 'N5', '2026-11-10 22:23:52.738671');
INSERT INTO transaccional.omision_cita (id_cita, id_nodo, fecha_hora) VALUES (5, 'N5.1', '2026-11-10 22:23:52.739621');
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (1, 2, 1, 2, 0, 74.198);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (1, 1, 2, 1, 1, 8.244);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (1, 3, 3, 0, 1, 0.763);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (1, 15, 4, 0, 1, 0.763);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (1, 18, 5, 0, 1, 0.763);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (2, 3, 1, 2, 0, 54.000);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (2, 18, 2, 1, 1, 6.000);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (2, 21, 3, 1, 1, 6.000);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (2, 5, 4, 1, 1, 6.000);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (2, 6, 5, 1, 1, 6.000);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (3, 15, 1, 4, 0, 76.632);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (3, 14, 2, 3, 1, 8.515);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (3, 8, 3, 2, 1, 4.730);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (3, 9, 4, 1, 1, 2.628);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (3, 22, 5, 1, 1, 2.628);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (4, 10, 1, 2, 0, 60.599);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (4, 19, 2, 1, 1, 6.733);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (4, 20, 3, 1, 1, 6.733);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (4, 24, 4, 1, 1, 6.733);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (4, 17, 5, 1, 1, 6.733);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (5, 12, 1, 2, 0, 42.782);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (5, 13, 2, 2, 0, 42.782);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (5, 11, 3, 1, 1, 4.754);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (5, 3, 4, 0, 1, 0.440);
INSERT INTO transaccional.resultado_hipotesis (id_cita, id_hipotesis, posicion, contador, contradicciones, peso) VALUES (5, 15, 5, 0, 1, 0.440);
INSERT INTO transaccional.retroalimentacion (id_retroalimentacion, id_cita, id_usuario, resultado, id_hipotesis_corregida, comentario, revisada, fecha_hora) OVERRIDING SYSTEM VALUE VALUES (1, 2, 1, 'confirmada', NULL, 'Confirmado por el equipo de respuesta.', false, '2026-11-10 22:23:52.749851');
INSERT INTO transaccional.retroalimentacion (id_retroalimentacion, id_cita, id_usuario, resultado, id_hipotesis_corregida, comentario, revisada, fecha_hora) OVERRIDING SYSTEM VALUE VALUES (2, 5, 1, 'corregida', 13, 'El análisis posterior mostró que era CSRF; la pregunta del script no pudo responderse.', false, '2026-11-10 22:23:52.753009');
SELECT pg_catalog.setval('transaccional.bitacora_id_evento_seq', 13, true);
SELECT pg_catalog.setval('transaccional.cita_id_cita_seq', 7, true);
SELECT pg_catalog.setval('transaccional.retroalimentacion_id_retroalimentacion_seq', 3, true);

-- ---------------------------------------------------------------------
-- CONSULTAS DE LOS GRÁNULOS DE CONOCIMIENTO Y DEL SISTEMA TRANSACCIONAL
-- ---------------------------------------------------------------------
-- Q1
SELECT h.nombre AS hipotesis, r.id_regla AS regla, pr.nombre AS prioridad,
       rp.orden, f.atributo || ' = ' || f.valor AS premisa, f.fuente_tipica AS fuente
FROM conocimiento.hipotesis h
JOIN conocimiento.regla r          ON r.id_hipotesis = h.id_hipotesis
JOIN conocimiento.prioridad pr     ON pr.id_prioridad = r.id_prioridad
JOIN conocimiento.regla_premisa rp ON rp.id_regla = r.id_regla
JOIN conocimiento.hecho f          ON f.id_hecho = rp.id_hecho
WHERE h.nombre = 'Spyware'
ORDER BY rp.orden;

-- Q2
SELECT h.id_hipotesis AS n, h.nombre AS hipotesis, r.id_regla AS regla,
       pr.nombre AS prioridad, COUNT(rp.id_hecho) AS premisas
FROM conocimiento.hipotesis h
JOIN conocimiento.regla r          ON r.id_hipotesis = h.id_hipotesis
JOIN conocimiento.prioridad pr     ON pr.id_prioridad = r.id_prioridad
JOIN conocimiento.regla_premisa rp ON rp.id_regla = r.id_regla
GROUP BY h.id_hipotesis, h.nombre, r.id_regla, pr.nombre, pr.nivel
ORDER BY pr.nivel DESC, h.id_hipotesis;

-- Q3
SELECT f.valor AS vector,
       COUNT(*)                                        AS hipotesis,
       COUNT(*) FILTER (WHERE pr.nombre = 'Crítica')   AS criticas,
       COUNT(*) FILTER (WHERE pr.nombre = 'Alta')      AS altas,
       COUNT(*) FILTER (WHERE pr.nombre = 'Media')     AS medias
FROM conocimiento.regla r
JOIN conocimiento.regla_premisa rp ON rp.id_regla = r.id_regla AND rp.orden = 1
JOIN conocimiento.hecho f          ON f.id_hecho = rp.id_hecho
JOIN conocimiento.prioridad pr     ON pr.id_prioridad = r.id_prioridad
GROUP BY f.valor, f.id_hecho
ORDER BY f.id_hecho;

-- Q4
SELECT f.id_hecho AS id, f.atributo || ' = ' || f.valor AS hecho,
       f.fuente_tipica AS fuente, COUNT(DISTINCT rp.id_regla) AS hipotesis_que_lo_usan
FROM conocimiento.hecho f
JOIN conocimiento.regla_premisa rp ON rp.id_hecho = f.id_hecho
GROUP BY f.id_hecho, f.atributo, f.valor, f.fuente_tipica
ORDER BY hipotesis_que_lo_usan DESC, f.id_hecho
LIMIT 6;

-- Q5
WITH RECURSIVE camino AS (
  SELECT r.id_nodo_origen, r.id_nodo_destino, r.id_hipotesis,
         ARRAY[r.id_nodo_origen::text] AS nodos, ARRAY[r.id_hecho::int] AS hechos
  FROM conocimiento.rama r WHERE r.id_nodo_origen = 'N0'
  UNION ALL
  SELECT r.id_nodo_origen, r.id_nodo_destino, r.id_hipotesis,
         c.nodos || r.id_nodo_origen::text, c.hechos || r.id_hecho::int
  FROM camino c JOIN conocimiento.rama r ON r.id_nodo_origen = c.id_nodo_destino
)
SELECT h.nombre AS hipotesis,
       array_to_string(c.nodos, ' > ') AS ruta_de_nodos,
       (SELECT string_agg(f.atributo || '=' || f.valor, ', ' ORDER BY ord)
          FROM unnest(c.hechos) WITH ORDINALITY AS u(idh, ord)
          JOIN conocimiento.hecho f ON f.id_hecho = u.idh) AS hechos_del_recorrido
FROM camino c JOIN conocimiento.hipotesis h ON h.id_hipotesis = c.id_hipotesis
WHERE h.nombre = 'Spyware';

-- Q6
WITH RECURSIVE camino AS (
  SELECT r.id_nodo_destino, r.id_hipotesis, ARRAY[r.id_hecho::int] AS hechos
  FROM conocimiento.rama r WHERE r.id_nodo_origen = 'N0'
  UNION ALL
  SELECT r.id_nodo_destino, r.id_hipotesis, c.hechos || r.id_hecho::int
  FROM camino c JOIN conocimiento.rama r ON r.id_nodo_origen = c.id_nodo_destino
), hojas AS (
  SELECT id_hipotesis, hechos FROM camino WHERE id_hipotesis IS NOT NULL
), premisas AS (
  SELECT r.id_hipotesis, ARRAY(SELECT rp.id_hecho::int FROM conocimiento.regla_premisa rp
                               WHERE rp.id_regla = r.id_regla ORDER BY rp.orden) AS hechos
  FROM conocimiento.regla r
)
SELECT COUNT(*) AS hipotesis_evaluadas,
       COUNT(*) FILTER (WHERE h.hechos = p.hechos) AS coinciden
FROM hojas h JOIN premisas p USING (id_hipotesis);

-- Q7
SELECT r.id_regla AS regla, h.nombre AS hipotesis,
       f.atributo || ' = ' || f.valor AS premisa_por_defecto
FROM conocimiento.regla r
JOIN conocimiento.hipotesis h      ON h.id_hipotesis = r.id_hipotesis
JOIN conocimiento.regla_premisa rp ON rp.id_regla = r.id_regla
JOIN conocimiento.hecho f          ON f.id_hecho = rp.id_hecho
                                  AND f.fuente_tipica = 'valor_defecto'
ORDER BY r.id_regla;

-- Q8
SELECT h.nombre AS hipotesis, r.id_regla AS regla, rp.orden,
       f.valor AS valor_esperado,
       CASE WHEN f.valor = 'falso' THEN 'coincide' ELSE 'contradice' END AS ante_respuesta_falso
FROM conocimiento.regla_premisa rp
JOIN conocimiento.regla r   ON r.id_regla = rp.id_regla
JOIN conocimiento.hipotesis h ON h.id_hipotesis = r.id_hipotesis
JOIN conocimiento.hecho f   ON f.id_hecho = rp.id_hecho
WHERE f.atributo = 'archivos_cifrados_rescate'
ORDER BY h.id_hipotesis;

-- Q9
SELECT pr.nombre AS prioridad, COUNT(*) AS hipotesis,
       ROUND(AVG(pi.prior), 5) AS prior_inicial, ROUND(AVG(pi.fiabilidad), 3) AS fiabilidad_inicial
FROM conocimiento.parametro_inferencia pi
JOIN conocimiento.regla r      ON r.id_hipotesis = pi.id_hipotesis
JOIN conocimiento.prioridad pr ON pr.id_prioridad = r.id_prioridad
GROUP BY pr.nombre, pr.nivel
ORDER BY pr.nivel DESC;

-- Q10
SELECT c.id_cita AS cita, to_char(c.fecha_inicio, 'HH24:MI') AS hora,
       h.nombre AS hipotesis, pr.nombre AS prioridad, c.estado,
       COALESCE(hc.nombre, '-') AS hipotesis_corregida
FROM transaccional.cita c
LEFT JOIN conocimiento.hipotesis h           ON h.id_hipotesis = c.id_hipotesis_resultado
LEFT JOIN conocimiento.prioridad pr          ON pr.id_prioridad = c.id_prioridad_resultado
LEFT JOIN transaccional.retroalimentacion ra ON ra.id_cita = c.id_cita
LEFT JOIN conocimiento.hipotesis hc          ON hc.id_hipotesis = ra.id_hipotesis_corregida
ORDER BY c.id_cita;

-- Q11
SELECT rh.posicion AS pos, h.nombre AS hipotesis, rh.contador,
       rh.contradicciones AS contra, rh.peso
FROM transaccional.resultado_hipotesis rh
JOIN conocimiento.hipotesis h ON h.id_hipotesis = rh.id_hipotesis
WHERE rh.id_cita = 5
ORDER BY rh.posicion;

-- Q12
SELECT ra.id_retroalimentacion AS id, ra.id_cita AS cita, h.nombre AS concluida,
       ra.resultado, COALESCE(hc.nombre, '-') AS corregida_a, ra.revisada
FROM transaccional.retroalimentacion ra
JOIN transaccional.cita c           ON c.id_cita = ra.id_cita
JOIN conocimiento.hipotesis h       ON h.id_hipotesis = c.id_hipotesis_resultado
LEFT JOIN conocimiento.hipotesis hc ON hc.id_hipotesis = ra.id_hipotesis_corregida
ORDER BY ra.id_retroalimentacion;
