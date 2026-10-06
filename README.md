# Petroff Amshen LLP - Legal OCR Cleaning, pgvector & Claude Agent API

Sistema integral de limpieza documental especializada, almacenamiento vectorial en **PostgreSQL (pgvector)** y asistente jurídico con **Anthropic Claude**, diseñado específicamente para litigios de:
- **NY Foreclosure Defense** (RPAPL § 1304, CPLR § 3408, FAPA CPLR 203/213).
- **FCRA** (15 U.S.C. § 1681, Disputas a CRAs, Furnishers, Metro 2).
- **RESPA / TILA / Reg X** (12 CFR § 1024, QWR, NOE, RFI).
- **FDCPA** (15 U.S.C. § 1692, Debt Validation Letter § 1692g).
- **Robo de Identidad y Auditoría Bancaria**.

---

## 🗂️ Estructura del Proyecto

```
rag_petroff_app/
├── app/
│   ├── main.py                  # Crea la app FastAPI y registra los routers
│   ├── core/
│   │   ├── config.py            # Settings (variables de entorno / .env)
│   │   └── constantes.py        # Constantes de dominio compartidas
│   ├── api/                     # Capa HTTP: sin lógica de negocio
│   │   ├── esquemas.py          # Modelos Pydantic de las peticiones
│   │   └── rutas/               # salud, ingesta, consulta, casos, interfaz
│   ├── servicios/               # Casos de uso
│   │   ├── ingesta.py           # Limpieza → JSONL limpio → chunks → embeddings → BD
│   │   └── consulta.py          # Retrieval semántico → dictamen
│   ├── limpieza/                # Las 5 reglas de limpieza OCR
│   │   ├── patrones.py          # Expresiones regulares precompiladas
│   │   ├── terminos_legales.py  # Catálogo de normalización (Regla 4)
│   │   ├── reglas.py            # Una función por regla
│   │   └── procesador.py        # Orquesta las reglas sobre un registro
│   ├── rag/
│   │   ├── chunking.py          # División por párrafos
│   │   └── embeddings.py        # sentence-transformers con respaldo por hashing
│   ├── llm/
│   │   ├── prompts.py           # Prompt de sistema y armado del mensaje
│   │   ├── cliente_claude.py    # Cliente de la API de Anthropic
│   │   └── dictamen_local.py    # Dictamen de demostración sin API key
│   ├── persistencia/
│   │   ├── almacen.py           # Fachada: PostgreSQL + respaldo SQLite
│   │   ├── modelos.py           # Dataclasses, tablas y mapeo a filas
│   │   ├── repositorio_base.py  # Escritura SQL común
│   │   ├── repositorio_postgres.py
│   │   └── repositorio_sqlite.py
│   └── web/index.html           # Portal web de consulta
├── scripts/
│   ├── ejecutar_limpieza.py     # Pipeline completo por CLI
│   └── ver_tablas.py            # Inspector de la base de datos
├── data/                        # JSONL de entrada
├── salida/                      # JSONL limpio y base SQLite local
├── pyproject.toml               # Configuración del linter (Ruff)
├── requirements.txt
└── requirements-dev.txt
```

---

## 📋 Las 5 Reglas de Limpieza Implementadas

1. **Regla 1 (Filtro de Descarte):**
   - Descarta si `confianza_promedio < 45.0` o `total_caracteres < 25` o más del 40% son símbolos no alfanuméricos.
   - Previene el fenómeno *"Garbage In, Garbage Out"*.

2. **Regla 2 (Eliminación de Artefactos de PaddleOCR y Unicode Roto):**
   - Elimina caracteres chinos/asiáticos accidentales.
   - Limpia caracteres de sustitución (`�`) y caracteres de control ASCII.
   - Elimina líneas de relleno visual (`###`, `***`, `---`).

3. **Regla 3 (Des-guionado y Unificación de Párrafos):**
   - Une palabras cortadas al final de línea (`juris-\ndiction` → `jurisdiction`).
   - Unifica renglones dentro de oraciones continuas pero preserva listas legales (`1.`, `(a)`, `Section`, `Article`) y tablas Markdown.

4. **Regla 4 (Normalización de Términos Legales Críticos):**
   - Estandariza citas de leyes: `RPAPL § 1304`, `CPLR § 3408`, `FAPA`, `Allonge`, `Promissory Note`, `Lis Pendens`.
   - Agencias de crédito: `TransUnion`, `Experian`, `Equifax`, `Innovis`, `Metro 2`.
   - Cartas regulatorias: `Qualified Written Request (QWR)`, `Notice of Error (NOE)`, `Request for Information (RFI)`, `Debt Validation Letter`.

5. **Regla 5 (Anonimización de PII Preservando Búsqueda):**
   - SSN: `056-88-1775` → `[SSN-REDACTED-1775]`.
   - Cuentas bancarias y préstamos: `Loan No.: 195786063` → `Loan No.[REDACTED-6063]`.
   - Permite que el abogado consulte por los últimos 4 dígitos manteniendo cumplimiento de privacidad.

---

## 🚀 Cómo Ejecutar

Todos los comandos se ejecutan desde la raíz del proyecto.

### 1. Instalar dependencias
```bash
pip install -r requirements-dev.txt
```

### 2. Ejecutar Limpieza e Indexación por CLI
```bash
python -m scripts.ejecutar_limpieza
```

### 3. Inspeccionar la base de datos
```bash
python -m scripts.ver_tablas
```

### 4. Levantar el Servidor FastAPI
```bash
uvicorn app.main:app --reload --port 8000
```

La documentación interactiva Swagger estará disponible en `http://localhost:8000/docs`.

### 5. Linter
```bash
ruff check .
```

```bash
ruff format .
```

La configuración está en `pyproject.toml`. Entre otras, detecta imports y variables sin usar (`F`), números mágicos (`PLR2004`), código comentado (`ERA`), complejidad excesiva (`C90`) y `print` fuera de los scripts (`T20`).

---

## 🔌 Endpoints Principales

* **`POST /api/limpiar-e-ingerir`**:
  Ejecuta las 5 reglas sobre `data/pruebaocr.jsonl` (o la ruta enviada en `ruta_jsonl`), crea `salida/pruebaocr_limpio.jsonl`, fragmenta en chunks y guarda en la base vectorial. Devuelve 404 si el archivo no existe.
* **`POST /api/consulta`**:
  Consulta semántica al Agente Claude. Con `?formato=texto` devuelve solo el dictamen en texto plano.
  ```json
  {
    "caso": "Morris - Closed - 602074 - 21155-2012",
    "pregunta": "¿Qué ordenó el juez en la conferencia de estatus sobre la moción de ejecución hipotecaria?",
    "top_k": 5
  }
  ```
* **`GET /api/casos`**:
  Lista los expedientes y volúmenes almacenados en la base de datos.
* **`GET /health`**:
  Estado del motor vectorial, modelo de embeddings y conexión con Claude.
* **`GET /`**:
  Portal web de consulta.
