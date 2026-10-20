# Adaptación a casos judiciales

## Ubicación de los documentos

El motor lee la carpeta indicada por `RAG_CORPUS`. Si no se configura, usa
`corpus` relativo a la carpeta desde donde se inicia el servicio. En este
repositorio, el corpus demostrativo está en:

```text
C:\Users\Charlis Vinci\RAG\corpus
```

Para expedientes reales se recomienda una carpeta separada, por ejemplo:

```text
D:\DatosLegales\expedientes
├── caso-0001
│   ├── demanda.pdf
│   ├── sentencia.pdf
│   └── pruebas.docx
└── caso-0002
    ├── contestacion.pdf
    └── resolucion.pdf
```

Configúrala sin modificar el código:

```env
RAG_CORPUS=D:\DatosLegales\expedientes
```

No se deben mezclar los documentos demostrativos con expedientes reales.

Cada expediente puede incluir `case.json` (no se indexa como documento):

```json
{"jurisdiccion":"civil","materia":"contractual","etapa":"sentencia","confidencialidad":"restringido"}
```

Se puede copiar `docs/case.json.example` dentro de cada carpeta de expediente y
ajustar sus valores. Antes de indexar, validar la estructura con:

```powershell
.\.venv\Scripts\python.exe scripts/validar_corpus_legal.py
```

La API acepta esos mismos filtros en `/search`, `/ask` y `/similar-cases`. El
software empresarial debe aplicar además sus propios permisos antes de enviar
la consulta.

Para indexar todos los archivos nuevos o modificados del corpus configurado:

```powershell
.\.venv\Scripts\python.exe scripts\index_corpus.py
```

El comando procesa PDF, DOCX, TXT, Markdown, XLSX e imágenes admitidas. Los
documentos sin cambios se omiten; los fallidos quedan registrados para revisión
y reintento.

## Búsqueda de casos parecidos

La recuperación RAG puede encontrar expedientes y fragmentos similares por
hechos, pretensiones, normas citadas, jurisdicción, órgano judicial y resultado.
Cada resultado debe conservar como mínimo:

- identificador del caso;
- documento y página;
- fecha y jurisdicción;
- tipo de procedimiento;
- fragmento de evidencia;
- estado procesal;
- resultado judicial, cuando esté confirmado.

La similitud documental no equivale a similitud jurídica. El sistema debe
mostrar los casos recuperados y sus diferencias, no convertir automáticamente
una similitud en una recomendación legal.

## Probabilidad de resultado

No es válido calcular una probabilidad de ganar usando solamente embeddings o
el número de casos parecidos. Para una probabilidad calibrada se necesitan:

1. casos históricos con resultado conocido;
2. una definición consistente de `ganó`, `perdió`, `acuerdo`, `archivo` y
   `resultado desconocido`;
3. separación temporal entre entrenamiento y evaluación;
4. variables estructuradas y evidencia documental trazable;
5. métricas de calibración, además de accuracy: Brier score, log loss,
   calibración por intervalos y cobertura;
6. revisión humana y registro de incertidumbre.

La primera versión debe entregar `casos_similares`, evidencia y una advertencia
de que no existe probabilidad calculada cuando faltan etiquetas suficientes. No
debe presentar una cifra como certeza ni sustituir el criterio profesional.

## Modelo de datos recomendado

Antes de indexar expedientes reales, conviene registrar por caso:

```text
case_id, jurisdiccion, pais, materia, tipo_procedimiento,
fecha_inicio, fecha_cierre, etapa, resultado, resultado_confirmado,
confidencialidad, hash_documentos
```

Los permisos deben filtrarse antes de recuperar fragmentos. La instrucción al
modelo no es un control de acceso suficiente. Los datos personales deben
redactarse o enmascararse en una etapa separada y auditable.

## Próximo bloque técnico

1. `case_id` ya se deriva de la primera carpeta de cada expediente anidado;
2. añadir filtros de jurisdicción, materia y confidencialidad a `/search` y
   `/ask`;
3. el endpoint `POST /api/v1/similar-cases` ya agrupa resultados por caso;
4. añadir un conjunto de evaluación legal anonimizado;
5. medir recuperación y calibración antes de entrenar o activar probabilidades.
