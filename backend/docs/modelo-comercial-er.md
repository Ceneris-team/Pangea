# Modelo comercial: diagrama entidad-relación (PP-322)

Modelo de datos comercial de Pangea después del flujo multiempresa (commit `b948aac`)
y de PP-320/PP-321. GitHub dibuja el diagrama Mermaid directamente.

```mermaid
erDiagram
    clnt ||--o{ sd : "tiene"
    sd ||--o{ ubccn : "agrupa"
    ubccn ||--o{ dspstv : "tiene"
    clnt ||--o{ usr_clnt : "miembros"
    usr ||--o{ usr_clnt : "pertenece a"
    rl ||--o{ usr : "rol global"
    usr_clnt ||--o{ usr_pryct_ubccn : "accede a"
    ubccn ||--o{ usr_pryct_ubccn : "proyecto"
    pln_sscrpcn ||--o| lmt_pln : "límites"
    pln_sscrpcn ||--o{ sscrpcn : "se contrata en"
    clnt ||--o{ sscrpcn : "contrata"
    sscrpcn ||--o{ cbr : "cobros"
    clnt ||--o{ solicitud_suscripcion : "solicita"
    usr ||--o{ solicitud_suscripcion : "solicitante / aceptante"
    sscrpcn |o--o| solicitud_suscripcion : "resulta de"
    pln_sscrpcn }o..o{ funcionalidad_comercial : "funcionalidades (JSONB)"
    complemento_comercial }o..o{ funcionalidad_comercial : "funcionalidades (JSONB)"

    clnt {
        int id_clnt PK
        string rzn_scl "razón social"
        string rc UK "RUC"
        string crr_cntct
        string estd
    }
    sd {
        int id_sd PK
        int id_clnt FK
        string nmbr "se crea sola: Sede principal"
        string estd
    }
    ubccn {
        int id_ubccn PK
        int id_sd FK
        string nmbr "se muestra como Proyecto"
        string estd
    }
    dspstv {
        int id_dspstv PK
        int id_ubccn FK
        string estd
    }
    usr {
        int id_usr PK
        int id_rl FK
        string crr UK
        string scp "global / por_sede"
        string estd
    }
    rl {
        int id_rl PK
        string nmbr UK "p. ej. Administrador Comercial"
    }
    usr_clnt {
        int id_mmb PK
        int id_usr FK
        int id_clnt FK
        string rol_emp "Administrador / Tecnico / Lector"
        string estd
    }
    usr_pryct_ubccn {
        int id_usr_pryct PK
        int id_mmb FK
        int id_ubccn FK
    }
    pln_sscrpcn {
        int id_pln PK
        string nmbr UK
        decimal prc_mnsl
        string moneda
        int revision
        jsonb funcionalidades
        string estd
    }
    lmt_pln {
        int id_lmt PK
        int id_pln FK, UK
        int mx_sds "sin uso desde multiempresa"
        int mx_ubccns
        int mx_dspstvs
        int mx_usrs
    }
    sscrpcn {
        int id_sscrpcn PK
        int id_clnt FK
        int id_pln FK
        date fch_inc
        date fch_vncmnt
        string estd
        jsonb condiciones "precio, límites y gracia fijados al contratar"
        string clave_idempotencia
    }
    cbr {
        int id_cbr PK
        int id_sscrpcn FK
        decimal mnt
        date fch_cbr
        string mtd_pg
    }
    solicitud_suscripcion {
        int id PK
        int id_clnt FK
        int solicitante_id FK
        int aceptante_id FK
        int suscripcion_resultante_id FK
        string estado
        jsonb solicitud
        jsonb propuesta
    }
    complemento_comercial {
        int id PK
        string nombre UK
        string tipo "Recurrente / Servicio"
        decimal precio
        jsonb cupos
        jsonb funcionalidades
    }
    funcionalidad_comercial {
        string codigo PK
        string nombre
        int disponible
    }
```

## Reglas que el diagrama no muestra

- **Una empresa (`clnt`) tiene a lo sumo un contrato `Activa` y uno `Programada`**
  (índices únicos parciales `uq_sscrpcn_clnt_activa` y `uq_suscripcion_programada`).
- **Los cupos se cuentan por empresa**, sumando todas sus sedes: proyectos (`ubccn`),
  dispositivos y usuarios. Se validan con `comprobar_cupo()` en
  `app/services/limites_plan.py`, con los límites guardados en `sscrpcn.condiciones`
  y no con los del plan actual, para que editar el catálogo no cambie un contrato vigente.
- **La sede es un detalle interno.** El primer proyecto de una empresa crea la
  «Sede principal» (`_resolver_sede` en `routers/ubicaciones.py`); por eso `lmt_pln.mx_sds`
  ya no se usa como cupo.
- `pryct` y las tablas de permisos `prms_usr_sd` y `prms_ubccn` se conservan como
  histórico o para usuarios antiguos, y no se dibujan.

## Estados de `sscrpcn.estd`

```mermaid
stateDiagram-v2
    [*] --> Programada: fecha de inicio futura
    [*] --> Activa: fecha de inicio hoy
    Programada --> Activa: llega la fecha (beat cada minuto)
    Programada --> Anulada: se cancela antes de empezar
    Programada --> Reemplazada: se contrata otro con inicio hoy
    Activa --> Suspendida: Suspender
    Suspendida --> Activa: Reactivar
    Activa --> Cancelada: Cancelar
    Suspendida --> Cancelada: Cancelar
    Activa --> Reemplazada: nuevo contrato o renovación
    Suspendida --> Reemplazada: nuevo contrato o renovación
    Activa --> Vencida: PP-320, fin de la gracia sin cobro (beat diario 00:30)
```

Además del estado guardado, `estado_contrato()` calcula lo que ve el usuario según la fecha:
**Vigente** (hasta `fch_vncmnt`), **En gracia** (hasta `fch_vncmnt + dias_gracia`) y
**Vencida** (después). Al vencer, la empresa queda en modo consulta: ve su histórico y la
telemetría se sigue recibiendo, pero no puede crear recursos.

PP-320 deja guardado ese «Vencida» cuando no hay cobro registrado en `cbr` y PP-321 avisa
por correo a los usuarios activos con rol «Administrador Comercial»
(`app/tasks/suscripciones.py` y `app/tasks/notificaciones.py`).
