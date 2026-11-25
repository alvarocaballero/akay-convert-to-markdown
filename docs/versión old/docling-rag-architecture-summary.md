# Resumen de arquitectura: Docling y RAG para Akay

Este documento resume la propuesta acordada para sustituir MarkItDown por Docling, revisar los documentos procesados e indexar su contenido en Qdrant.

## Vista general

El repositorio actual `Akay.ConvertToMarkdown` producirá dos imágenes Docker, desplegadas como dos Azure Container Apps independientes:

```text
Akay.ConvertToMarkdown
├─ content-converter image
└─ content-indexer image
```

## 1. Container App: conversor

### Tecnología

```text
Python + Docling + Azure Speech + FFmpeg
```

### Responsabilidades

#### Documentos

1. Recibir el mensaje de Azure Service Bus.
2. Descargar el original desde Blob Storage.
3. Convertirlo con Docling.
4. Detectar la jerarquía y las secciones.
5. Añadir los tags acordados.
6. Obtener los confidence grades globales y por página.
7. Extraer las imágenes.
8. Generar los artefactos.
9. Subirlos a Blob Storage.
10. Llamar al webhook.
11. Completar el mensaje de Service Bus.

#### Audio y vídeo

Permanecen como están actualmente:

```text
Audio → Azure Speech
Vídeo → FFmpeg + Azure Speech
```

No se instalará ni utilizará el ASR de Docling.

### Configuración de Docling

| Opción | Valor |
| --- | --- |
| Pipeline | `standard` |
| PDF backend | `docling_parse` |
| OCR | Activado |
| Force OCR | Desactivado |
| Replace broken text layer | Activado |
| Tables | `accurate` |
| Heading hierarchy | Activado |
| Images | `referenced` |
| Page images | Desactivadas |
| Picture classification | Desactivada |
| Picture description | Desactivada |
| Code enrichment | Opcional |
| Formula enrichment | Opcional |

## 2. Artefactos por `TopicContent`

```text
topic-content/{topicContentId}/
├─ original.pdf
├─ document.md
├─ document.docling.json
├─ review.json
└─ images/
   ├─ image-001.png
   └─ image-002.png
```

### `original.*`

Fuente original subida por el profesor.

### `document.md`

- Resultado legible de la conversión.
- Incluye los tags de secciones.
- Se muestra como vista previa.
- No se edita en Akay.

### `document.docling.json`

- Contiene la estructura completa detectada por Docling.
- Alimenta posteriormente `HybridChunker`.
- Evita procesar otra vez el documento original.

### `review.json`

Contiene:

- Resumen del documento.
- Secciones y tags.
- Tablas e imágenes detectadas.
- Advertencias.
- Confidence grades globales y por página.

Sirve para construir la pantalla de revisión.

### `images/*`

Imágenes reales extraídas y referenciadas desde Markdown y `review.json`.

### Artefactos descartados inicialmente

No se generarán mientras no exista un consumidor real:

```text
conversion-report.json
manifest.json
HTML
Plain text
DocTags
```

## 3. Pantalla de revisión

Akay.Be mostrará:

- Markdown renderizado.
- Secciones y tags detectados.
- Resumen del documento.
- Tablas e imágenes.
- Grade global.
- Grades por página.
- Advertencias.

El profesor podrá:

```text
Aceptar
```

o:

```text
Modificar el original y volver a procesarlo
```

No habrá un editor de PDF, DOCX, PPTX ni Markdown.

## 4. Container App: indexador

### Tecnología

```text
Python
docling-core[chunking]
Tokenizer
Cliente de embeddings
Qdrant client
```

No necesita OCR, TableFormer, modelos de layout, FFmpeg, Azure Speech ni los modelos completos de Docling.

### Responsabilidades

Cuando el profesor acepte el documento:

1. Recibir el mensaje `index-topic-content`.
2. Descargar `document.docling.json`.
3. Descargar los tags desde `review.json`.
4. Reconstruir el `DoclingDocument`.
5. Ejecutar `HybridChunker`.
6. Contextualizar cada chunk con sus encabezados.
7. Añadir tags, páginas y metadatos de Akay.
8. Generar los embeddings.
9. Guardar los puntos en Qdrant.
10. Notificar a Akay.Be.
11. Gestionar órdenes de eliminación de Qdrant.

## 5. Imágenes Docker

### Imagen del conversor

```text
ghcr.io/akay/content-converter:{commit}
```

Incluye:

- Aplicación conversora.
- Docling.
- Modelos documentales.
- RapidOCR.
- Modelo de código y fórmulas.
- FFmpeg.
- Cliente de Azure Speech.

### Imagen del indexador

```text
ghcr.io/akay/content-indexer:{commit}
```

Incluye:

- Aplicación indexadora.
- `docling-core`.
- `HybridChunker`.
- Tokenizer.
- Cliente de embeddings.
- Cliente de Qdrant.

Ambas imágenes se construirán desde el mismo repositorio mediante dos targets o Dockerfiles.

## 6. Mensajería

### Cola existente

```text
convert-to-markdown
```

Gestionada por el conversor.

### Cola nueva

```text
index-topic-content
```

Gestionada por el indexador.

Operación de indexación:

```json
{
  "operation": "index",
  "topicContentId": 123
}
```

Operación de eliminación:

```json
{
  "operation": "delete",
  "topicContentId": 123
}
```

## 7. Base de datos

### `TopicContent`

Necesitará conceptualmente:

```text
OriginalBlobName
MarkdownBlobName
DoclingJsonBlobName
ReviewBlobName
ImagesPrefix
ProcessingStatus
RagIndexProfileId
RagIndexingStatus
RagIndexedAt
```

Los nombres definitivos dependerán del modelo actual.

### Tabla nueva: `RagIndexProfile`

```text
Id
Name
Provider
Model
Deployment
Dimensions
Tokenizer
Distance
QdrantCollection
IsActive
```

Ejemplo:

```text
akay-embedding-v1
AzureOpenAI
text-embedding-3-small
embedding-small
1536
cl100k_base
Cosine
akay-content-v1
```

El perfil debería asociarse al ámbito de conocimiento, probablemente la asignatura. Cada `TopicContent` registrará el perfil con el que fue indexado.

Las credenciales no se almacenarán en esta tabla. Permanecerán en Key Vault o en secretos de Container Apps.

## 8. Qdrant

Cada chunk será un punto:

```json
{
  "id": "topic-content-123-chunk-4",
  "vector": [],
  "payload": {
    "topicContentId": 123,
    "topicId": 5,
    "subjectId": 3,
    "text": "...",
    "contextualizedText": "...",
    "headings": ["Arquitectura", "Puertos"],
    "tags": ["architecture", "ports"],
    "pages": [4, 5]
  }
}
```

Los puntos se eliminarán filtrando por `topicContentId`.

Qdrant no será la fuente de verdad: podrá reconstruirse desde Blob Storage y la base de datos.

## 9. Sustitución de documentos

No existirán versiones históricas.

```text
Procesar documento nuevo
    ↓
Profesor acepta
    ↓
Indexar documento nuevo
    ↓
Activarlo
    ↓
Eliminar los puntos del anterior en Qdrant
    ↓
Eliminar los blobs del anterior
    ↓
Eliminar el registro anterior
```

El documento anterior se conservará temporalmente hasta que el nuevo esté correctamente indexado, evitando que el tema se quede sin contenido si el reemplazo falla.

## 10. Responsabilidades de .NET

Akay.Be se encargará de:

- Estados y dominio.
- Permisos.
- Revisión y aceptación.
- Generación de ejercicios.
- Generación del embedding de las preguntas.
- Consulta de Qdrant.
- Construcción del contexto RAG.
- Llamada al LLM.
- Respuestas y citas.
- Orquestación de la sustitución y eliminación.

Para generar ejercicios sobre todo el contenido podrá leer el Markdown completo o recorrer todos los chunks, sin limitarse a una búsqueda top-k.

## 11. Flujo completo

```text
Profesor sube original
    ↓
Akay.Be guarda el TopicContent y envía convert-to-markdown
    ↓
Python Converter genera Markdown, JSON, revisión e imágenes
    ↓
Webhook de conversión completada
    ↓
Akay.Be muestra la revisión
    ↓
Profesor acepta
    ↓
Akay.Be envía index-topic-content
    ↓
Python Indexer ejecuta HybridChunker y genera embeddings
    ↓
Python Indexer guarda los chunks en Qdrant
    ↓
Webhook de indexación completada
    ↓
Akay.Be habilita ejercicios y chat RAG
```

## 12. Decisiones pendientes antes de implementar

- Proveedor y modelo de embeddings.
- Alojamiento de Qdrant.
- Generación exacta de los tags de sección.
- Campos reales del modelo actual `TopicContent`.
- Contratos definitivos de mensajes y webhooks.

