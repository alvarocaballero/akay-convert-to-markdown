# Especificación definitiva: procesamiento de contenido e indexación RAG

Fecha: 2026-11-14. Estado: diseño consolidado para implementación; no acredita código implementado ni despliegues.
Ámbito de implementación: C:\Develop\Akay\Akay.ConvertToMarkdown. Se reutiliza el repositorio actual.
Documento normativo: esta especificación sustituye los resúmenes y propuestas de contratos anteriores. El plan de tareas acompañante referencia sus apartados.

Revisión 2026-11-14: edición antes de aprobar, reconstrucción desde Markdown y corrección de transcripciones por segmento. Implementar la tarea complementaria N9A después de N9 y antes de N10; conservar el trabajo previo compatible.

Suplemento 2026-11-16: inventario de fórmulas únicamente en review.json (§10.1.1).
Conserva el trabajo y las evidencias anteriores; no reinicia N0-N16 ni N9A.

## 1. Decisiones y límites

- Un repositorio Python; tres ejecutables, tres imágenes Docker y tres Azure Container Apps independientes.
- Tres colas de trabajo de Azure Service Bus. No se utilizarán Topics/subscriptions ni una cuarta cola específica para YouTube.
- Documentos: Docling. Audio/vídeo/YouTube: Azure Speech; FFmpeg y adaptador YouTube cuando corresponda.
- Indexación: Docling Core/HybridChunker, tokenizer, proveedor de embeddings y Qdrant.
- No se instala ni usa ASR de Docling, Whisper ni modelos VLM de descripción de imágenes.
- El profesor puede corregir el Markdown antes de aprobarlo. Tras aprobar, el contenido queda bloqueado para edición; para cambiarlo debe eliminarlo y subir un nuevo documento.
- La transcripción puede revisarse antes de aprobarla editando únicamente el texto de segmentos existentes; sus identificadores, orden y tiempos no se editan.
- No hay versiones históricas de documentos. Una modificación del original crea otro contenido; una sustitución se coordina antes de retirar el anterior.
- No se modifican ahora Akay.Be, tablas, migraciones, pantalla, chat o generación de ejercicios. Sus responsabilidades y contratos se documentan para la integración posterior.
- No se reescribe desde cero: se reutilizan Service Bus, Blob, autenticación, webhooks, Azure Speech, FFmpeg, pruebas y manejo de errores existentes, adaptando lo necesario.
- Este documento no autoriza publicación, acceso a servicios reales ni despliegue. Esas acciones requieren destino y credenciales autorizados expresamente.

## 2. Modelo de uso en Akay

### 2.1. Principal y adicionales

Un Topic puede tener como máximo un documento principal activo. Es un documento textual admitido, no un audio/vídeo.

El principal proporciona el contenido base y la jerarquía de TopicContentSection. Después pueden añadirse PDF, DOCX, PPTX, HTML, MD, TXT, audio, vídeo o una URL YouTube a una sección de ese principal.

Los adicionales tienen identidad y artefactos propios. No generan filas de secciones de Akay ni marcadores akay-section. Pueden conservar encabezados internos para presentación y chunking.

Ejemplo:

~~~text
Topic 25
└─ Principal: TopicContent 501
   └─ Sección 3
      ├─ Texto y enlace al vídeo en el principal
      ├─ PDF adicional: TopicContent 502
      └─ Vídeo adicional: TopicContent 503 + transcripción
~~~

No se pega la transcripción en el Markdown principal ni se introduce como comentario HTML oculto. Principal y adicionales se relacionan por sectionId. El chat/ejercicios pueden usar ambos sin modificar los originales.

### 2.1.1. Edición, aprobación y preparación final

1. Convertir el original y guardar Markdown, Docling JSON, informe de extracción e imágenes.
2. Mostrar al profesor el resultado y el diagnóstico de extracción. Permitir editar el texto y los encabezados del Markdown, no los archivos de imagen.
3. Al aprobar un Markdown editado, congelar su entrada y bloquear más ediciones. Solicitar rebuildFromMarkdown en la misma cola documental, con una nueva requestId y el mismo contentKey.
4. Sobrescribir el Docling JSON y review.json desde ese texto y regenerar sus secciones, sin OCR ni extracción de imágenes. No escribir el Markdown; conservar las imágenes referenciadas y eliminar las del inventario que ya no se usan. Los resultados iniciales son provisionales para este flujo.
5. Akay.Be comprueba que el resultado corresponde a la aprobación vigente, persiste las secciones definitivas y solicita indexación usando los artefactos finales. Un fallo de preparación no publica el contenido ni lo marca como indexado.
6. Después pueden asociarse adicionales a esas secciones. No hay edición del principal aprobado; una nueva subida tiene otra identidad. Los adicionales existentes conservan la política de reasignación de 2.2.

Si se aprueba sin cambios, se pueden reutilizar los artefactos coherentes de la extracción inicial; no es obligatoria una segunda pasada sin modificaciones. No indexar borradores ni disparar indexación automática desde el conversor.

La revisión de medios es opcional: Akay.Be guarda los textos corregidos en transcript.json y actualiza su Markdown antes de indexar. Si no hay correcciones, usa los artefactos de transcripción originales. No se vuelve a transcribir el audio.

No se implementan ahora editores ni endpoints de Akay.Be. El bloqueo, la autorización, el guardado del borrador y el envío posterior de indexación son responsabilidades del consumidor, no nuevos estados de dominio impuestos a Python.

### 2.2. Sustitución del principal

Los adicionales NO se eliminan al sustituir o retirar el principal:

1. Conservar sus registros, originales, Markdown y JSON.
2. Desvincularlos de las secciones retiradas: quedan pendientes de reasignación.
3. Excluirlos temporalmente de recuperación RAG; solicitar su desindexación si todavía tienen puntos.
4. Generar/aceptar las nuevas secciones del nuevo principal.
5. El profesor vuelve a asignar los adicionales a las secciones nuevas.
6. Reindexar con el nuevo contexto, sin reconvertir/retranscribir los archivos.

No reasignar automáticamente por título ni por número de sección: pueden haber cambiado.

Akay.Be debe impedir que una eliminación en cascada de secciones borre los contenidos adicionales. La FK que los asigna a una sección debe admitir la desvinculación controlada.

Si se prepara el reemplazo mientras el principal anterior sigue activo, mantener las asociaciones anteriores hasta el corte explícito. Después del corte, ninguna asociación obsoleta queda disponible en búsquedas.

## 3. Independencia del dominio

Los workers son reutilizables para otras aplicaciones, incluidos manuales técnicos.

- contentKey y scopeKey son cadenas opacas; no se analizan prefijos como topic-content:.
- payload se devuelve sin interpretar.
- metadata contiene valores del consumidor; no exige subjectId, topicId ni topicContentId.
- sectionId identifica una sección documental genérica.
- El backend decide unicidad del principal, pertenencia, permisos, aceptación y publicación.
- Ningún worker accede a las tablas de Akay.
- callback selecciona una URL preconfigurada; el mensaje nunca proporciona una URL de webhook libre.

## 4. Despliegue y responsabilidades

| Worker / imagen lógica | Cola lógica | Responsabilidad | No incluye |
| --- | --- | --- | --- |
| document-converter | convert-document | Convertir documentos, extraer secciones si se solicita, imágenes y revisión | Speech, FFmpeg, yt-dlp, cliente Qdrant, ASR/VLM |
| media-transcriber | transcribe-media | Blob audio/vídeo o YouTube -> audio -> Azure Speech -> transcripción | Pipeline PDF de Docling, modelos OCR/layout/tablas, Qdrant |
| content-indexer | index-content | Indexar/desindexar Docling JSON y transcripciones | FFmpeg, Speech, yt-dlp, modelos OCR/layout/tablas/ASR |

Las tres imágenes pueden compartir código técnico y una base mínima, pero sus dependencias y configuración de arranque se instalan/validan por separado.

Los nombres de colas e imágenes de esta tabla son lógicos. Los nombres reales y la transición de la cola existente convert-to-markdown se configuran durante la integración. No desplegar un consumidor documental sobre una cola que siga recibiendo mensajes multimedia sin coordinar el cambio del productor.

## 5. Identidad, idempotencia y orden

### 5.1. Identidades

- schemaVersion: versión técnica del contrato, inicialmente 1. No es una versión del documento.
- requestId: UUID de una operación. Los reintentos conservan el mismo UUID y el mismo contenido de la petición.
- contentKey: identidad estable asignada por el consumidor. En Akay se deriva de TopicContent: topic-content:502.
- scopeKey: ámbito de conocimiento, por ejemplo akay:subject:3 o manuals:product:washer-x200.
- indexProfile.id: identidad de una configuración técnica de indexación inmutable una vez utilizada.

Una petición de conversión y otra de indexación del mismo contenido tienen requestId diferentes. Reasignar un adicional genera una nueva operación, manteniendo contentKey.

La conversión inicial y rebuildFromMarkdown también tienen requestId diferentes. Cada petición identifica una entrada congelada; un reintento no puede leer un Markdown cuyo texto cambió bajo la misma identidad. La reconstrucción sobrescribe el review actual, sin conservar informes originales ni crear versiones históricas.

El par scopeKey/contentKey identifica inequívocamente el contenido dentro del espacio de indexación. Las cadenas no otorgan autorización por sí solas.

### 5.2. Precisión técnica: operationSequence

Se añade operationSequence a las operaciones del indexador para hacer explícito el orden entre indexar, reasignar y desindexar:

- Entero positivo creciente por scopeKey/contentKey, asignado por el backend.
- Un reintento conserva requestId y operationSequence.
- Es un contador de operaciones, NO versionado del documento.
- Una operación anterior a la última admitida no puede cambiar Qdrant.
- Una misma secuencia con otro requestId o parámetros diferentes es un conflicto.
- Un reintento de una operación completada reutiliza el resultado sin repetir mutaciones innecesarias.

El indexador requiere estado técnico duradero y coordinación entre réplicas. Puede apoyarse en Blob Storage con escrituras condicionales/leases; no añade tablas de dominio ni accede a la base de datos de Akay. Un bloqueo en memoria no basta.

La secuencia se coordina por contenido y ámbito incluso si cambia el perfil. No permitir que un trabajo antiguo en otra colección sobreviva a una retirada. El backend conserva los destinos de índice utilizados para poder limpiar los que corresponda.

Una operación obsoleta devuelve content.index.operation.superseded, sin volver a aplicar sus efectos. Esto no implica que Qdrant o Service Bus proporcionen una transacción conjunta.

## 6. Entrada: conversor documental

Cola lógica: convert-document. source.type solo admite blob; contentType es document.

~~~json
{
  "schemaVersion": 1,
  "requestId": "b1ad362f-0911-4773-8651-1508d94ca001",
  "operation": "convert",
  "contentKey": "topic-content:501",
  "source": {
    "type": "blob",
    "blobName": "topics/25/content/501/original.pdf"
  },
  "destinationBlobName": "topics/25/content/501/document.md",
  "contentType": "document",
  "overwriteDestination": false,
  "documentOptions": {
    "extractSections": true,
    "codeEnrichment": false,
    "formulaEnrichment": true,
    "ocrLanguage": "es"
  },
  "callback": "topic-content",
  "payload": {
    "topicContentId": 501
  }
}
~~~

### 6.1. Opciones

| Campo | Regla |
| --- | --- |
| operation | convert por defecto si se omite; también admite rebuildFromMarkdown. No confundir con index/delete del indexador |
| destinationBlobName | Obligatorio para convert; se omite en rebuildFromMarkdown, que no escribe Markdown |
| extractSections | Booleano, por defecto false. Akay.Be envía true para el principal y false para adicionales |
| codeEnrichment | Booleano, por defecto false; habilita procesamiento especializado de código |
| formulaEnrichment | Booleano, por defecto false; habilita reconocimiento especializado de fórmulas |
| ocrLanguage | String opcional: es (español), eu (euskera), gl (gallego), ca (catalán), fr (francés), en (inglés) o de (alemán). Por defecto es si se omite |
| overwriteDestination | Booleano, por defecto false; sobreescritura técnica, no creación de historial |

Los tres flags son independientes y por petición. Rechazar tipos inválidos y opciones desconocidas. extractSections=false no elimina los encabezados internos del documento.

ocrLanguage selecciona un único idioma por conversión; rechazar null, cadenas vacías,
espacios y valores no admitidos, sin normalizar ni sustituir silenciosamente.
Se aplica al OCR documental, no a traducción ni a Azure Speech. Mapear cada código
a la configuración realmente soportada por la versión fijada del motor OCR y
verificar sus recursos. No activar los siete idiomas simultáneamente. Si el motor
utiliza pesos multilingües compartidos, documentarlo sin confundir esa cobertura
con calidad verificada en todos los idiomas. Registrar individualmente los idiomas
cuya calidad OCR real siga pendiente.
En rebuildFromMarkdown no se ejecuta OCR: la opción conserva su validación contractual, pero no activa inferencia.

El backend, no Python, decide si un archivo es el principal. El original permanece en su Blob de entrada; no se copia a otra carpeta por razones de presentación.

### 6.2. Configuración funcional Docling

- Pipeline standard, backend docling_parse.
- OCR habilitado sin forzar OCR de toda la página.
- Motor OCR reproducible, preferentemente RapidOCR con backend/idiomas y pesos prefijados.
- Idioma OCR seleccionado por documentOptions.ocrLanguage, por defecto es; no sustituirlo con configuración global del worker. Verificar los recursos compatibles de los siete valores admitidos.
- Tablas habilitadas en modo accurate.
- Inferencia de jerarquía de encabezados habilitada con la API de la versión elegida.
- Imágenes de figuras exportadas como referenciadas.
- Sin exportación de imágenes completas de cada página. El renderizado interno necesario para OCR/crops no queda prohibido.
- Sin picture classification ni picture description.
- Código/fórmulas según flags.
- No habilitar servicios externos, plugins ni descarga arbitraria de recursos de HTML/Markdown.

La recuperación de capas textuales rotas depende de las APIs realmente disponibles en la versión fijada. Verificar el campo y su ubicación; no inventar un flag ni introducir una opción desconocida. Si no está soportada, registrar la limitación y el comportamiento de error.

El alcance de N3 es integrar Docling desde ConvertToMarkdown: invocarlo con las
opciones seleccionadas, conservar sus resultados disponibles y manejar sus
estados/errores. No incluye reparar, entrenar ni mejorar Docling o su OCR, ni
garantizar reconocimiento carácter a carácter. Registrar las limitaciones de
calidad observadas; por sí solas no bloquean esta integración. Las pruebas de
integración deben seguir detectando opciones ignoradas, pérdida de resultados,
fallos de invocación y estados parciales tratados incorrectamente como éxito.

Fijar versiones compatibles de Docling y docling-core tras contrastar las pruebas/API ya realizadas en el repositorio. No forzar actualizaciones o downgrades basándose solo en esta especificación funcional.

### 6.3. Reconstrucción del Markdown editado

Misma cola, worker e imagen. Ejemplo completo para el principal:

~~~json
{
  "schemaVersion": 1,
  "requestId": "b1ad362f-0911-4773-8651-1508d94ca005",
  "operation": "rebuildFromMarkdown",
  "contentKey": "topic-content:501",
  "source": {
    "type": "blob",
    "blobName": "topics/25/content/501/extracted.md"
  },
  "contentType": "document",
  "overwriteDestination": false,
  "documentOptions": {
    "extractSections": true,
    "codeEnrichment": false,
    "formulaEnrichment": false
  },
  "callback": "topic-content",
  "payload": {
    "topicContentId": 501
  }
}
~~~

- source es el Markdown editado y congelado en Blob. Se omiten destinationBlobName y extractionReviewBlobName. El prefijo se deduce del origen: extracted.md usa extracted.artifacts/. Validar que el review actual corresponde al mismo contentKey antes de usar su inventario.
- Reconstruir el documento estructurado desde el Markdown, no reutilizar el JSON de la extracción anterior. Conservar el texto editado, encabezados, tablas, código y fórmulas representables; registrar limitaciones reales del parser, no prometer un round-trip sin pérdidas de layout.
- No ejecutar OCR, modelos PDF/layout/tablas ni enriquecimiento de código/fórmulas. Rechazar codeEnrichment=true o formulaEnrichment=true en esta operación en vez de ignorarlos.
- Ignorar los marcadores de sección anteriores para regenerar las secciones del review. No escribir ni normalizar el Markdown, ni tratar encabezados dentro de código como secciones.
- Conservar las imágenes del inventario actual todavía referenciadas y eliminar las que ya no se usan, únicamente por sus rutas exactas dentro del prefijo de este contenido. No borrar archivos ajenos ni buscar imágenes externas.
- Si el profesor elimina, cambia o añade un enlace de imagen inexistente, no repararlo ni bloquear el análisis por ello. No descargar ni abrir sus destinos. El Markdown permanece intacto.
- Sobrescribir document.docling.json y review.json en el mismo prefijo, sin conservar un informe original ni publicar Markdown. El mismo webhook devuelve destinationBlobName igual al blobName de origen. Reintentos usan estado técnico, no copias históricas públicas. Indexar solo tras completarse la regeneración y mantener el Markdown bloqueado durante la indexación.

## 7. Secciones y marcadores

Solo se producen cuando extractSections=true.

### 7.1. Identificador

Usar UUID/GUID determinista a partir de contentKey y la referencia estructural de la cabecera. Definir una única función y namespace fijo, con serialización no ambigua, reutilizada por todos los exportadores.

El resultado debe repetirse para la misma entrada procesada con la misma configuración fijada. No prometer estabilidad de referencias entre modelos/parser diferentes. No usar solo el título: pueden repetirse cabeceras.

Python asigna IDs antes de persistir en la base de datos. Akay.Be crea/actualiza TopicContentSection a partir de review.json al recibir el resultado correspondiente a la petición vigente.

En el flujo editable, las secciones de la extracción son provisionales. Solo el conjunto aceptado se usa para persistencia definitiva y asociación de adicionales. No exigir conservar IDs entre el original y el Markdown editado; sí exigir coherencia e idempotencia dentro del resultado final. El indexador usa las referencias del nuevo JSON, no las antiguas.

### 7.2. Sintaxis acordada

~~~markdown
<!-- akay-section:start id="8af35178-a031-50c7-9c53-d77084e0c684" -->
# Introducción a la fotosíntesis
~~~

El marcador se sitúa inmediatamente antes de la cabecera. No se define un marcador end adicional: los límites se obtienen de la jerarquía y del orden de lectura, hasta la siguiente sección del mismo nivel o superior.

review.json conserva el mapeo entre id, parentId, level, order y doclingItemRef. El indexador usa ese mapeo y el documento estructurado; no intenta recuperar IDs desde los comentarios Markdown. rebuildFromMarkdown actualiza este mapeo sin escribir ni sustituir los comentarios antiguos del Markdown.

No generar automáticamente etiquetas temáticas con LLM. En esta entrega, tags/marcadores de sección significan identidad estructural, no una taxonomía semántica.

Los page headers/footers no se convierten en secciones. El contenido anterior a la primera sección se mantiene como contenido general, con sectionId=null.

## 8. Entrada: transcriptor multimedia

Cola lógica: transcribe-media. contentType admite audio o video.

### 8.1. Desde Blob

~~~json
{
  "schemaVersion": 1,
  "requestId": "b1ad362f-0911-4773-8651-1508d94ca002",
  "contentKey": "topic-content:502",
  "source": {
    "type": "blob",
    "blobName": "topics/25/content/502/original.mp4"
  },
  "destinationBlobName": "topics/25/content/502/document.md",
  "contentType": "video",
  "overwriteDestination": false,
  "callback": "topic-content",
  "payload": {
    "topicContentId": 502
  }
}
~~~

### 8.2. Desde YouTube

Mismo contrato y misma cola, cambiando source:

~~~json
{
  "type": "youtube",
  "url": "https://www.youtube.com/watch?v=VIDEO_ID"
}
~~~

contentType sigue siendo video: YouTube es el origen, no un tercer tipo multimedia. Solo se obtiene la pista de audio necesaria; no se promete análisis visual del vídeo.

- Resolver/validar un vídeo individual con yt-dlp u otro adaptador probado.
- Procesar el audio con FFmpeg/FFprobe si hace falta; FFmpeg no sustituye al extractor de una página YouTube.
- Transcribir con Azure Speech Fast Transcription.
- Fijar yt-dlp, componentes auxiliares y runtime JavaScript si la versión lo requiere.
- No admitir playlists, directos ni URLs externas genéricas en esta entrega.
- Validar esquema/hosts/identificador, destinos resueltos y redirecciones; impedir acceso a red privada/metadata endpoints y rutas locales.
- Limitar tamaño real descargado, duración, tiempo y uso temporal. No confiar solo en metadatos previos.
- No aceptar comandos, argumentos, cookies o credenciales arbitrarios desde el mensaje.
- No eludir controles de acceso ni prometer soporte para todos los vídeos públicos. Procesar material autorizado conforme a las condiciones aplicables.
- Las restricciones de plataforma, dependencia de extractor o bloqueos se informan con errores explícitos.
- No recorrer automáticamente enlaces encontrados en documentos. YouTube se procesa por petición multimedia explícita.

Conservar source.url de origen y, en review.json, identificador canónico del vídeo/título si están disponibles. No guardar URLs temporales firmadas de descarga como origen permanente.

## 9. Artefactos y publicación

### 9.1. Documentos

- Markdown legible, con marcadores solo si extractSections=true.
- document.docling.json: documento estructurado completo.
- review.json: revisión, secciones y colección de imágenes.
- Archivos de imagen realmente necesarios, sin capturas completas de todas las páginas.

### 9.2. Medios

- Markdown legible de la transcripción.
- transcript.json: segmentos de transcripción con tiempos.
- review.json: resumen técnico y advertencias; sin secciones de Akay ni grades PDF ficticios.

No crear docling JSON en el transcriptor solo para uniformar el contrato. El indexador adapta transcript.json usando Docling Core.

### 9.3. Layout de salida y referencias

destinationBlobName siempre identifica el Markdown, también en audio/vídeo.

Para evitar colisiones cuando dos Markdown comparten directorio, derivar un subdirectorio de artefactos del nombre completo del destino sin extensión. Ejemplo normativo para document.md:

~~~text
topics/25/content/501/document.md
topics/25/content/501/document.artifacts/document.docling.json
topics/25/content/501/document.artifacts/review.json
topics/25/content/501/document.artifacts/images/figure-001.png
~~~

Para medios, sustituir document.docling.json por transcript.json.

En el flujo editable, guardar el texto editado en el mismo extracted.md y regenerar sus artefactos en el mismo prefijo. Ejemplo:

~~~text
topics/25/content/501/extracted.md
topics/25/content/501/extracted.artifacts/document.docling.json
topics/25/content/501/extracted.artifacts/review.json
topics/25/content/501/extracted.artifacts/images/figure-001.png
~~~

El review actual se sobrescribe. Se conservan las imágenes de extracted.artifacts/images referenciadas por el Markdown y se eliminan únicamente las entradas del inventario que ya no se usan. El worker no escribe extracted.md, no conserva copias del review ni crea un Markdown nuevo.

Esta es una precisión de almacenamiento respecto a los ejemplos iniciales con review.json en una carpeta compartida. Los consumidores utilizan SIEMPRE las rutas devueltas, no reconstruyen rutas ni enumeran prefijos.

Los enlaces generados por la extracción usan rutas relativas válidas hacia sus imágenes. En Markdown editado, los enlaces modificados por el profesor siguen la política de 6.3: no se garantiza su existencia. El JSON no expone rutas locales ni habilita lectura local arbitraria. Probar su recarga para chunking sin descargar imágenes.

### 9.4. Colección de imágenes

La colección/inventario de imágenes vive únicamente en review.json. Cada entrada referencia un archivo Blob; no contiene binario base64.

Tras rebuildFromMarkdown, images contiene solo las imágenes existentes del inventario actual referenciadas en el Markdown editado. pageNumber en esas entradas describe su ubicación original; no trasladarlo a los nuevos párrafos. No añadir al inventario enlaces externos o desconocidos como si fueran imágenes extraídas.

No se devuelve otra lista images ni imagesPrefix en el webhook. Los archivos PNG en Blob no son una colección adicional de metadatos.

No generar manifest.json, conversion-report.json, HTML, plain text ni DocTags como artefactos públicos de esta entrega. Los registros técnicos internos de coordinación no son documentos de revisión ni contratos del consumidor.

### 9.5. Publicación segura

- Publicar un conjunto coherente de artefactos antes del webhook completed.
- Subir Markdown el último NO constituye por sí solo una transacción.
- Coordinar escrituras concurrentes al mismo destino y comprobar origen/opciones/contentKey antes de reutilizar un resultado.
- No considerar suficiente un Markdown antiguo sin JSON/revisión.
- Recuperar cargas incompletas sin mezclar artefactos de intentos distintos.
- Reintentar el webhook tras publicación completa sin reconvertir/retranscribir, incluida la entrada YouTube.
- Las sobreescrituras se coordinan y no invalidan archivos todavía utilizados por otra publicación.
- Un contenido aceptado no cambia de original ni de opciones mediante una sobreescritura en segundo plano: usar una nueva identidad/destino o retirar explícitamente su disponibilidad antes de reprocesarlo. overwriteDestination no autoriza cambios invisibles de material activo.
- Limpiar solo recursos propios/no publicados del intento. Nunca borrar prefijos amplios del consumidor.

## 10. Esquemas de revisión y transcripción

### 10.1. review.json

Ejemplo de forma contractual; los valores son ilustrativos:

~~~json
{
  "schemaVersion": 1,
  "contentKey": "topic-content:501",
  "contentType": "document",
  "source": {
    "type": "blob",
    "blobName": "topics/25/content/501/original.pdf"
  },
  "summary": {
    "pageCount": 8,
    "sectionCount": 1,
    "tableCount": 0,
    "imageCount": 1,
    "formulaCount": 0,
    "durationMilliseconds": null
  },
  "sections": [
    {
      "id": "8af35178-a031-50c7-9c53-d77084e0c684",
      "parentId": null,
      "title": "Introducción a la fotosíntesis",
      "level": 1,
      "order": 0,
      "doclingItemRef": "#/texts/0",
      "pageNumber": 1
    }
  ],
  "tables": [],
  "formulas": [],
  "images": [
    {
      "id": "figure-001",
      "blobName": "topics/25/content/501/document.artifacts/images/figure-001.png",
      "caption": null,
      "pageNumber": 2
    }
  ],
  "confidence": {
    "meanGrade": null,
    "lowGrade": null,
    "pages": []
  },
  "warnings": [],
  "extractionReviewBlobName": null,
  "processing": {
    "operation": "convert",
    "engine": "docling",
    "engineVersion": "PINNED_AT_IMPLEMENTATION"
  }
}
~~~

Reglas:

- summary es estadística, no resumen generado por un LLM.
- sections=[] para adicionales y medios.
- tables incluye representación visual/celdas, título y procedencia disponibles; no imágenes completas de página.
- images=[] cuando no existan.
- confidence procede del ConversionResult, no de asumir que DoclingDocument lo contiene todo.
- Conservar valores disponibles por página: layoutScore/Grade, ocrScore/Grade, parseScore/Grade y resúmenes disponibles.
- No emitir NaN o Infinity en JSON. Valores ausentes/no medidos son null; nunca cero inventado.
- No prometer una probabilidad calibrada de corrección ni usar un grade como garantía.
- Un documento no paginado puede tener pageCount=null y confidence.pages=[].
- Advertencias estructuradas con code, message y pageNumber opcional.
- Tablas/captions/textos se tratan como contenido no confiable al renderizar en frontend.

Para rebuildFromMarkdown, processing.operation es rebuildFromMarkdown y extractionReviewBlobName es null. source identifica el Markdown editado y autoritativo; el review anterior se sobrescribe. sections, tables y formulas corresponden al documento reconstruido. summary.pageCount y páginas del texto son null; confidence.meanGrade y lowGrade son null y confidence.pages=[]. imageCount cuenta las imágenes aún referenciadas. No fabricar correspondencias entre texto editado y páginas del original.

### 10.1.1. Inventario complementario de fórmulas

`formulas` es un array de ocurrencias estructuradas, vacío si no se detectan.
`summary.formulaCount` es un entero igual a `formulas.length`. Al leer informes
anteriores, los campos ausentes toman `[]` y `0`; schemaVersion sigue siendo 1.

| Campo de cada ocurrencia | Regla |
| --- | --- |
| id | Identidad local determinista para reintentos idénticos; convención `formula-001`, `formula-002`, etc., en el orden de FormulaItems del array texts de Docling. No deduplicar expresiones iguales. |
| doclingItemRef | Referencia del elemento estructurado, por ejemplo `#/texts/4`. |
| sectionId | ID de la sección disponible según el orden de lectura y el mapeo del propio informe; null antes de la primera sección, sin extracción de secciones o fuera de la capa body. |
| text | Texto del elemento proporcionado por la ruta de procesamiento: orig si está disponible; en su ausencia, text. Conservarlo sin corregir expresiones; puede estar vacío. |
| latex | Representación decodificada disponible en FormulaItem.text de Core 2.99.0; null si está vacía o solo contiene espacios. No inferirla desde orig ni desde el flag de enriquecimiento. |
| pageNumber | Primera página de procedencia disponible del elemento; null si no existe. |

Se contrastaron las APIs con Docling 2.141.0/Core 2.99.0: el orden de lectura PDF
crea fórmulas con orig y text vacío, el enriquecimiento escribe la representación
decodificada en text y el serializador Core usa ese campo como matemática.
No existe un campo latex independiente. Disponibilidad no garantiza validez
sintáctica ni corrección matemática del resultado del modelo. No reparar,
normalizar ni fabricar expresiones. El inventario usa solamente FormulaItems del
documento ya procesado: sin otra llamada LLM, modelos nuevos ni pasada adicional
de extracción. formulaEnrichment conserva su valor y comportamiento actual.
No se garantiza detectar todas las fórmulas, especialmente expresiones inline.

En rebuildFromMarkdown se vuelve a recoger el inventario del documento reconstruido,
incluidas las fórmulas editadas/añadidas/eliminadas que el parser represente como
FormulaItems. No copiar el inventario original ni sus páginas; pageNumber es null.
No inicializar enriquecimiento. **Limitación verificada del parser fijado:** el
backend Markdown/Marko GFM 2.141.0/2.2.5 conserva expresiones `$...$`/`$$...$$` como
texto, no como FormulaItems. Esas expresiones no aparecen en este inventario;
no se añade un parser matemático ni se promete un round-trip de fórmulas.

Los informes multimedia emiten formulas=[] y formulaCount=0; no inferir ecuaciones
del texto transcrito. El consumidor obtiene el inventario leyendo review.json;
el webhook no cambia. No añadir codeBlocks/codeBlockCount ni modificar código o
codeEnrichment. Akay.Be, tablas/migraciones y generación de resúmenes/glosarios
siguen siendo responsabilidades futuras del consumidor.

### 10.2. transcript.json

~~~json
{
  "schemaVersion": 1,
  "contentKey": "topic-content:502",
  "origin": {
    "type": "blob",
    "blobName": "topics/25/content/502/original.mp4"
  },
  "language": "es-ES",
  "durationMilliseconds": 18500,
  "segments": [
    {
      "id": "segment-0001",
      "startMilliseconds": 12000,
      "endMilliseconds": 18500,
      "speaker": null,
      "text": "La fotosíntesis transforma la energía luminosa."
    }
  ]
}
~~~

origin conserva la fuente original Blob o YouTube, no la ruta temporal de descarga. El indexador conserva esa referencia para las citas, además de la ruta del JSON técnico.

Los segmentos conservan el orden, el idioma/locutor si están disponibles y tiempos procedentes de Speech. Validar rangos y unidades. Si no se dispone de tiempos, representarlos como null y advertirlo; no inventarlos.

Antes de aprobar, el consumidor puede mostrar la lista de segmentos y permitir modificar solo text del segmento seleccionado por id. No cambiar id, orden, startMilliseconds, endMilliseconds, speaker ni origin; no añadir/eliminar/fusionar segmentos mediante esa edición. Validar texto no vacío y límites de tamaño. Guardar el transcript.json corregido y regenerar su Markdown desde esos mismos segmentos antes de indexar. Esta escritura y el editor pertenecen a Akay.Be, fuera de la implementación Python actual; no requieren nueva cola, operación de Speech ni webhook de transcripción. El indexador recibe el JSON guardado con su contrato existente.

Los tiempos conservados localizan el segmento de audio original; no prometen alineación palabra a palabra ni que el texto corregido sea una cita literal del audio. Tras aprobar, no se admite edición. Las pruebas Python usan fixtures de segmentos corregidos sin afirmar que ya existe la pantalla .NET.

No convertir cada segmento temporal en una sección de Topic. No generar capítulos semánticos con un LLM en esta entrega.

## 11. Webhook de conversión completada

Dos clases de endpoint lógico en el backend: resultado de conversión y resultado de índice. Los destinos físicos se resuelven con callback.

Conservar document.conversion.completed para documentos y medios, discriminando por contentType.

~~~json
{
  "schemaVersion": 1,
  "eventType": "document.conversion.completed",
  "requestId": "b1ad362f-0911-4773-8651-1508d94ca001",
  "operation": "convert",
  "contentKey": "topic-content:501",
  "source": {
    "type": "blob",
    "blobName": "topics/25/content/501/original.pdf"
  },
  "destinationBlobName": "topics/25/content/501/document.md",
  "contentType": "document",
  "artifacts": {
    "doclingJsonBlobName": "topics/25/content/501/document.artifacts/document.docling.json",
    "reviewBlobName": "topics/25/content/501/document.artifacts/review.json"
  },
  "payload": {
    "topicContentId": 501
  }
}
~~~

Para audio/vídeo, artifacts tiene transcriptJsonBlobName y reviewBlobName, sin doclingJsonBlobName:

~~~json
{
  "transcriptJsonBlobName": "topics/25/content/502/document.artifacts/transcript.json",
  "reviewBlobName": "topics/25/content/502/document.artifacts/review.json"
}
~~~

El nombre único es transcriptJsonBlobName, no transcriptionJsonBlobName.

El evento significa conversión/tagging/artefactos completos, NO aceptación del profesor ni indexación. No se dispara el indexador automáticamente.

Para documentos, devolver operation=convert o rebuildFromMarkdown, también en fallos cuando sea recuperable. El resultado de reconstrucción usa el mismo eventType y las rutas finales en destinationBlobName/artifacts; su source es el Markdown de entrada. Las notificaciones multimedia no requieren este nuevo discriminador. La aprobación y la indexación siguen siendo decisiones de Akay.Be, no un efecto del webhook.

El backend guarda referencias, obtiene review.json con acceso autorizado y persiste secciones solo del principal. Ni la lista de imágenes ni todo el contenido de review.json se duplican en el webhook.

En el flujo editable, el primer webhook permite revisión; no convierte las secciones iniciales en asociaciones definitivas. El webhook de reconstrucción vigente permite persistir las secciones finales y enviar index-content. Un callback de extracción antiguo no sustituye el resultado final ni desbloquea la edición.

## 12. Entrada: indexador

Cola lógica index-content. Operaciones index y delete.

### 12.1. Indexar un adicional multimedia

~~~json
{
  "schemaVersion": 1,
  "requestId": "b1ad362f-0911-4773-8651-1508d94ca003",
  "operationSequence": 1,
  "operation": "index",
  "contentKey": "topic-content:502",
  "scopeKey": "akay:subject:3",
  "source": {
    "type": "blob",
    "format": "transcript",
    "blobName": "topics/25/content/502/document.artifacts/transcript.json"
  },
  "sectionContext": {
    "mode": "fixed",
    "sectionId": "8af35178-a031-50c7-9c53-d77084e0c684",
    "headingPath": ["Fotosíntesis", "Fase luminosa"]
  },
  "indexProfile": {
    "id": "study-default",
    "provider": "AzureOpenAI",
    "model": "text-embedding-3-small",
    "deployment": "embedding-small",
    "dimensions": 1536,
    "tokenizer": "cl100k_base",
    "maxChunkTokens": 600,
    "distance": "Cosine",
    "collection": "study-content"
  },
  "metadata": {
    "topicContentId": 502,
    "topicId": 25,
    "subjectId": 3
  },
  "callback": "content-index-result",
  "payload": {
    "topicContentId": 502
  }
}
~~~

Selección inicial aprobada para N10: **AzureOpenAI**, **text-embedding-3-small**,
**1536 dimensiones** y **cl100k_base**. No existe todavía un recurso Azure OpenAI
ni un deployment de embeddings. La selección no aprueba los demás valores del
ejemplo: `study-default`, `embedding-small`, `600`, `Cosine` y `study-content`
siguen siendo ilustrativos, no configuración de producción. No se ha fijado una
revisión remota del modelo.

N10 implementa el adaptador configurable y la indexación local de conjuntos de
puntos. Se verifica con embeddings simulados, transporte HTTP simulado y Qdrant
local persistente; **la integración de producción no está verificada**. Endpoint,
deployment y autenticación reales requieren configuración explícita válida. No
se descubren credenciales ambientales ni se aprovisionan recursos para las pruebas.
El registro de evidencias y límites vive en
[el progreso](docling-rag-progress.md) y en
[la guía de indexación](content-processing-indexing.md).

### 12.2. Formatos y asignación

- source.type=blob; source.format es docling o transcript.
- Documentos adicionales: format=docling y sectionContext.mode=fixed.
- Principal: format=docling y mode=fromReview.
- Otros consumidores genéricos pueden utilizar mode=none, sin sección de dominio.
- No se admite un source.url en el indexador. YouTube lo procesa el transcriptor.

Para el principal:

~~~json
{
  "mode": "fromReview",
  "reviewBlobName": "topics/25/content/501/document.artifacts/review.json"
}
~~~

Para contenido genérico sin asociación de sección:

~~~json
{
  "mode": "none"
}
~~~

En Akay, adicionales sin sección no pueden indexarse/publicarse. Esta regla se aplica en Akay.Be; mode=none existe para reutilización por otros consumidores y para documentos sin secciones de dominio.

El indexador valida que los artefactos/contentKey/mapeos recibidos concuerdan; no acepta un review ajeno al documento.

### 12.3. Perfil inmutable

El mensaje contiene la configuración efectiva completa, no solamente un profileId que obligaría a consultar la base de datos.

El consumidor registra sus perfiles. Un perfil usado no se modifica: un cambio de modelo/dimensiones/tokenizer/política relevante crea otro id y requiere reindexar los contenidos afectados.

- provider identifica un adaptador soportado/configurado, no un proveedor arbitrario cargado dinámicamente.
- Credenciales, endpoints autorizados y límites operativos residen en secretos/configuración controlada.
- Validar dimensions, distance, token budget, tokenizer y compatibilidad de colección/modelo.
- Compartir dimensiones no prueba que dos modelos produzcan vectores comparables.
- Una colección corresponde a un espacio de embeddings compatible; cambiarlo implica nuevo destino y migración explícita, no mezclar vectores.
- La consulta .NET usa el modelo/preprocesamiento compatible con los documentos, incluyendo prefijos query/document cuando el modelo los requiera.

No se exige fingerprint en contratos. Se puede calcular un hash de configuración para diagnóstico interno. No reemplaza al id del perfil, no mide calidad ni detecta un cambio de pesos remoto que no esté reflejado en los datos conocidos.

El primer adaptador usa la API REST de Azure OpenAI `2024-10-21` y el deployment
configurado, con clave explícita o proveedor asíncrono explícito de tokens Entra.
No hay fallback de autenticación ni descubrimiento automático de un recurso.
La ventana admitida es de 8192 tokens por entrada; comprobar también los límites
de lote y contar el texto contextualizado completo. El recurso y su cuota real
siguen pendientes. El tokenizer se carga desde un archivo local con el SHA-256
oficial comprobado, sin descargar recursos durante los trabajos.

La API local de N10 requiere llamadas serializadas por su consumidor. Su resultado
solo confirma las escrituras del conjunto y su limpieza acotada; no proporciona
una transacción entre lotes, disponibilidad de dominio ni protección frente a
operaciones concurrentes obsoletas. N11 añade coordinación duradera y entrega de
resultados; hasta entonces la entrada de cola del indexador permanece cerrada.

## 13. Chunking e indexación

### 13.1. Documentos

Recargar DoclingDocument desde el JSON guardado, sin procesar otra vez el PDF.

HybridChunker usa estructura y tokenizer para dividir unidades grandes y unir unidades pequeñas compatibles. No es una evaluación pedagógica ni garantía de extracción correcta.

- En el principal, asignar contenido a secciones mediante referencias estructurales y orden de lectura.
- No permitir chunks que mezclen secciones de dominio diferentes, aunque tengan el mismo título o HybridChunker las considere combinables.
- En adicionales, todos los chunks heredan sectionId y headingPath del contexto fijo, conservando encabezados internos como contexto adicional.
- Guardar texto limpio separado del texto contextualizado usado para embeddings.
- Contar el texto contextualizado completo dentro del presupuesto; no superar la ventana del modelo.
- Conservar referencias de procedencia disponibles: páginas, elementos y fuente.
- No depender de comentarios HTML para identificar secciones.
- No mezclar fuentes documentales distintas dentro de un mismo chunk.

Si hubo edición, recargar el nuevo JSON y el nuevo review.json producidos por rebuildFromMarkdown. Nunca indexar el texto inicial por conservar su ruta en caché. No asignar al texto corregido páginas o coordenadas antiguas. El contrato index-content no cambia: el consumidor envía las referencias finales compatibles entre sí.

### 13.2. Transcripciones

Construir con Docling Core un documento estructurado desde segmentos ya transcritos, sin ASR ni OCR.

Mantener un mapeo de referencias de elementos a segmentos temporales. Si se divide o fusiona contenido, conservar procedencia suficiente para citar el intervalo real; no asignar tiempos de frase inventados a palabras.

El texto para chunks/embeddings procede del transcript.json indicado, incluidas sus correcciones. Conservar el mapeo por id y tiempos; no recargar la respuesta inicial de Speech ni retranscribir para recuperar el texto previo.

El contenido contextualizado puede incorporar la ruta de sección, nombre del recurso y encabezados internos apropiados. Es un proceso técnico, no generación automática de capítulos.

### 13.3. Puntos Qdrant

Usar IDs UUID deterministas, no strings arbitrarias como topic-content-502-chunk-4. Su generación no depende de requestId.

Ejemplo de payload técnico:

~~~json
{
  "scopeKey": "akay:subject:3",
  "contentKey": "topic-content:502",
  "profileId": "study-default",
  "operationSequence": 1,
  "chunkIndex": 0,
  "sectionId": "8af35178-a031-50c7-9c53-d77084e0c684",
  "headingPath": ["Fotosíntesis", "Fase luminosa"],
  "text": "La fotosíntesis transforma la energía luminosa.",
  "contextualizedText": "Fotosíntesis > Fase luminosa\n\nLa fotosíntesis transforma la energía luminosa.",
  "source": {
    "format": "transcript",
    "blobName": "topics/25/content/502/document.artifacts/transcript.json"
  },
  "provenance": {
    "pages": [],
    "startMilliseconds": 12000,
    "endMilliseconds": 18500
  },
  "metadata": {
    "topicContentId": 502,
    "topicId": 25,
    "subjectId": 3
  }
}
~~~

Los campos reservados no pueden ser sobreescritos por metadata. El binario de imágenes/vídeos no se guarda en Qdrant.

La operación index reemplaza el conjunto de puntos de ese contenido/perfil/ámbito. Reintentos no duplican puntos y un conjunto menor no deja chunks antiguos. Esperar confirmación de escrituras antes del webhook completed.

Qdrant no es fuente de verdad; se puede reconstruir desde artefactos y configuración del consumidor. No declarar publicación de dominio desde Python.

### 13.4. Función de scopeKey

Se almacena como metadata técnica y se utiliza como filtro exacto en búsquedas y eliminaciones. No se tokeniza como contenido ni se incluye por defecto en embeddings.

.NET construye los filtros a partir del contexto autorizado, junto a contenido aceptado, secciones vigentes y permisos. Nunca confiar solo en un scopeKey enviado por el navegador.

Añadir índices de payload a los campos utilizados para búsqueda/limpieza. Una colección compartida no implica permiso para buscar en todos sus ámbitos.

## 14. Entrada: desindexar

Misma cola, sin otra imagen ni otra operación para reasignar.

~~~json
{
  "schemaVersion": 1,
  "requestId": "b1ad362f-0911-4773-8651-1508d94ca004",
  "operationSequence": 2,
  "operation": "delete",
  "contentKey": "topic-content:502",
  "scopeKey": "akay:subject:3",
  "indexTarget": {
    "profileId": "study-default",
    "collection": "study-content"
  },
  "callback": "content-index-result",
  "payload": {
    "topicContentId": 502
  }
}
~~~

Solo elimina los puntos de Qdrant del contenido y destino indicados. NO borra originales, imágenes, Markdown, JSON ni registros de base de datos.

Repetir un delete para puntos ausentes tiene éxito. Rechazar filtros vacíos, contenido ambiguo o destinos no autorizados. No borrar todos los puntos de una colección/ámbito al pedir eliminar un contenido.

Para reasignar el adicional a una sección nueva: otra operación index, por ejemplo operationSequence=3, mismo contentKey y nuevos sectionId/headingPath. Reutilizar artefactos; recalcular embeddings si cambia el texto contextualizado.

## 15. Webhooks del índice

### 15.1. Indexación completada

~~~json
{
  "schemaVersion": 1,
  "eventType": "content.indexing.completed",
  "requestId": "b1ad362f-0911-4773-8651-1508d94ca003",
  "operationSequence": 1,
  "contentKey": "topic-content:502",
  "scopeKey": "akay:subject:3",
  "index": {
    "profileId": "study-default",
    "chunkCount": 28
  },
  "payload": {
    "topicContentId": 502
  }
}
~~~

index es un informe del resultado; no es un índice nuevo. profileId indica la configuración usada y chunkCount los puntos del conjunto completado. collection y fingerprint no son obligatorios ni se necesita repetir el perfil entero.

### 15.2. Desindexación completada

~~~json
{
  "schemaVersion": 1,
  "eventType": "content.index.deleted",
  "requestId": "b1ad362f-0911-4773-8651-1508d94ca004",
  "operationSequence": 2,
  "contentKey": "topic-content:502",
  "scopeKey": "akay:subject:3",
  "index": {
    "profileId": "study-default"
  },
  "payload": {
    "topicContentId": 502
  }
}
~~~

### 15.3. Operación obsoleta

~~~json
{
  "schemaVersion": 1,
  "eventType": "content.index.operation.superseded",
  "requestId": "b1ad362f-0911-4773-8651-1508d94ca003",
  "operationSequence": 1,
  "contentKey": "topic-content:502",
  "scopeKey": "akay:subject:3",
  "currentOperationSequence": 2,
  "payload": {
    "topicContentId": 502
  }
}
~~~

No significa contenido publicado ni indexado con la operación antigua. El backend no retrocede estados al recibirlo.

## 16. Errores, notificación y settlement

| Operación | Fallo definitivo |
| --- | --- |
| Conversión documental/multimedia | document.conversion.failed |
| Indexación | content.indexing.failed |
| Desindexación | content.index.deletion.failed |

Un fallo contiene las identidades recuperables, operación/secuencia cuando proceda, payload y un error seguro:

~~~json
{
  "code": "DOCUMENT_CONVERSION_FAILED",
  "message": "The document could not be converted."
}
~~~

- Conservar autenticación X-Api-Key y callback permitido por configuración.
- Idempotency-Key se deriva de requestId y tipo de resultado. El receptor debe deduplicar: el header por sí solo no lo hace.
- Completar Service Bus tras procesamiento Y webhook exitoso. Fallos permanentes se completan tras notificar su fallo.
- Errores transitorios se reintentan/abandonan; no emitir un fallo definitivo por cada 429/timeout temporal.
- Dead lettering lo controla la cola. Documentar monitorización/recuperación de su DLQ; no prometer un webhook final cuando los intentos se agotan sin un mecanismo implementado.
- Mensaje inválido sin callback/requestId recuperables: tratamiento de poison message y logs, sin notificación inventada.
- Reintentos de notificación no repiten extracción ni embeddings confirmados.
- Confirmaciones antiguas no reactivan documentos eliminados o adjuntos pendientes de reasignación.
- No exponer contenidos completos, credenciales, rutas locales ni logs de subprocesos en errores.
- Una conversión parcial/incompleta no se convierte silenciosamente en completed; advertencias recuperables sí se muestran en review.json.
- Mantener el event loop y renovación de lock funcionando. Cancelar asyncio.to_thread no detiene el hilo: no limpiar temporales ni liberar coordinación mientras continúe un proceso capaz de escribir.
- El límite de renovación del lock debe cubrir todo el trabajo, subidas, notificación y margen, no solo un timeout de transcripción.
- Shutdown, timeouts, pérdida de lease/lock y carreras de reintentos deben estar probados.

## 17. Responsabilidades futuras de Akay.Be y datos manuales

No se implementan en esta entrega, pero el contrato exige:

### 17.1. TopicContent y TopicContentSection

Guardar identidad/papel principal-adicional, Topic, sección asignada nullable para adicionales, fuente Blob/YouTube, opciones, referencias de artefactos, aceptación, estado y peticiones vigentes.

- Principal -> TopicContentSection con GUID, parentId, título, nivel, orden y referencia Docling.
- Adicional -> sección asignada; al retirar principal no se elimina el adicional.
- No usar ImagesPrefix como inventario persistido ni filas por imagen sin un caso de uso; review.json contiene la colección.
- Guardar operación/secuencia de índice vigente y resultado para rechazar callbacks antiguos.
- Claves técnicas contentKey y scopeKey se calculan/validan en backend.

### 17.2. RagIndexProfile

Campos conceptuales: Id, Name, Provider, Model, ModelRevision si existe, Deployment, Dimensions, Tokenizer, MaxChunkTokens, Distance, QdrantCollection, IsActive.

Perfiles inmutables tras uso; sin secretos. El backend envía el snapshot al indexador y usa el mismo espacio de embeddings al consultar.

### 17.3. Revisión, aceptación y limpieza

- Mostrar Markdown renderizado, secciones del principal, tablas, imágenes, grades disponibles y advertencias.
- Recursos privados con acceso autorizado; no guardar SAS de larga duración en la base de datos ni en Markdown permanente.
- Confirmación de conversión -> revisión, NO indexación automática.
- Antes de aprobar, permitir edición del Markdown y corrección de text por segmento; no edición de archivos de imagen. Sanitizar la vista sin ejecutar HTML ni cargar recursos arbitrarios desde el servidor.
- Al aprobar, bloquear edición y congelar la entrada. Si cambió el Markdown, solicitar rebuildFromMarkdown; solo su resultado vigente y coherente permite persistir las secciones definitivas y enviar index. Si no cambió, reutilizar los artefactos iniciales coherentes.
- Para medios corregidos, guardar transcript.json y su Markdown concordantes antes de indexar. No invocar Speech ni permitir editar tiempos/IDs desde la pantalla.
- Aceptación, artefactos definitivos y asociación válida -> mensaje index usando publicación fiable del backend. Los adicionales se asignan a secciones definitivas, no a las provisionales de la extracción.
- No permitir nuevas ediciones tras aprobar. Para cambiar el contenido aprobado, eliminarlo y subir otro; preservar los adicionales para reasignación según 2.2. Un fallo de preparación/indexación conserva el bloqueo y permite reintentar sin publicar un resultado incompleto.
- Desvincular adicional -> excluirlo de consultas y solicitar delete de índice; conservar archivos.
- Borrar un adicional definitivamente -> limpiar solo su índice/artefactos/registro.
- Retirar principal -> limpiar sus recursos/secciones, preservando adicionales para reasignar.
- Qdrant/Blob/base de datos no tienen una transacción común: coordinar limpieza con reintentos y comprobación de resultados.

Chat, prompts, ejercicios y construcción de filtros autorizados son .NET. Para ejercicios globales no utilizar solo top-k como sustituto de recorrer todo el material aceptado.

## 18. Tres imágenes y CI/CD

### 18.1. Dependencias y modelos

- Document-converter: Docling documental, OCR/layout/tablas y code/formula cuando se ofrecen esos flags. Precargar solo modelos necesarios.
- Media-transcriber: Speech, FFmpeg/FFprobe, yt-dlp y dependencias YouTube de la versión fijada. Sin pesos Docling/Whisper.
- Content-indexer: docling-core, extra/tokenizer del proveedor elegido, cliente embeddings, Qdrant, Azure clientes y estado técnico. Sin modelos de extracción ni ASR.
- No instalar todos los extras en una base compartida que vuelva pesadas las tres imágenes.
- Mantener dependencias CPU-only cuando se despliegue en CPU.
- Modelos/tokenizers locales accesibles por usuario no-root y sin descargas en el primer trabajo.
- La imagen document-converter incluye los recursos OCR necesarios para es/eu/gl/ca/fr/en/de y selecciona un idioma por conversión. Deduplicar pesos compartidos cuando lo permita la versión fijada; probar su disponibilidad offline y registrar calidad real pendiente por idioma. Incluir layout, tablas y código/fórmulas habilitables, sin ASR/Whisper ni modelos de descripción/clasificación de imágenes.
- La imagen documental ejecuta convert y rebuildFromMarkdown. La segunda operación no requiere modelos adicionales ni debe inicializar los de extracción para reconstruir un Markdown.
- No confundir paquetes como Transformers con pesos Whisper. Excluir lo innecesario sin desinstalar bibliotecas necesarias para código/fórmulas.

### 18.2. Publicación y despliegue

- Evolucionar GitHub Actions existente a pruebas y tres builds/publicaciones GHCR.
- Tres imágenes y tres despliegues separados, una identidad de release/SHA.
- No desplegar latest; registrar tag inmutable/digest.
- No crear tag de release exitoso antes de que pasen pruebas y los tres builds.
- Credenciales para publicar en GHCR y para que Azure descargue imágenes son configuraciones diferentes.
- Azure login preferentemente OIDC autorizado; cada app con su identidad/secretos, cola y escalador Service Bus.
- Sin ingress público; logs y estado de worker no requieren un servidor HTTP por defecto.
- Escalado y concurrencia independientes. Un proceso de extracción documental por réplica como inicio conservador, midiendo recursos.
- Mantener configuración documental de 2 vCPU/4 GiB solo como propuesta inicial, no capacidad garantizada. Medir medios/indexador.
- Incorporar bootstrap documentado para colas/apps/identidades o exigir explícitamente esos recursos; no asumir que ya existen.
- Despliegue manual/aprobado hasta que Akay.Be y contratos estén preparados para el corte.
- No realizar aprovisionamiento o despliegue real sin autorización explícita de destino y credenciales.
- No hay despliegue atómico de tres apps. Diseñar corte/rollback coordinado sin consumidores nuevos procesando mensajes incompatibles.

## 19. Criterios de aceptación

1. Misma fuente/configuración y reintentos producen IDs de sección coherentes; títulos repetidos no colisionan.
2. Principal crea secciones; adicionales no las crean y conservan estructura interna.
3. Flags código/fórmulas independientes y estrictos; probar las cuatro combinaciones.
4. Las imágenes solo se enumeran en review.json; los archivos del inventario extraído existen y no hay capturas de cada página. Los enlaces modificados por el profesor no se reparan, descargan ni convierten en condición de éxito.
5. Conversión no depende de Qdrant/Speech; transcripción no carga Docling; indexador no requiere FFmpeg/Speech.
6. PDF/DOCX/PPTX/HTML/TXT/MD se procesan; medios actuales siguen pasando por Speech/FFmpeg.
7. Blob y YouTube comparten transcribe-media, sin Topics ni cuarta cola; URLs no soportadas se rechazan de forma controlada.
8. Markdown/transcript.json contienen el mismo contenido transcrito y mantienen procedencia temporal disponible.
9. El indexador soporta docling y transcript sin reprocesar fuentes.
10. Chunks respetan sección, contexto, tokenizer, fuente y límites; conservan páginas/tiempos sin inventarlos.
11. Reintentar index no duplica puntos; menos chunks/reasignación no dejan puntos viejos.
12. Delete está acotado y no elimina archivos ni otro contenido.
13. Retirar principal no borra adicionales; la integración posterior puede reasignarlos reutilizando artefactos.
14. Una operación vieja no resucita puntos después de delete ni hace retroceder estados.
15. Fallos parciales/webhooks repetidos/leases/timeouts/shutdown no producen completados prematuros ni paquetes incoherentes.
16. Probar las tres imágenes, builds y configuración de despliegue. Marcar pruebas cloud pendientes si no se autorizaron.
17. Contratos y ejemplos se validan automáticamente; no hay NaN, secretos o rutas locales en salidas.
18. Los tests por defecto no requieren Azure Speech/YouTube/embeddings reales. Usar dobles y servicios locales; pruebas reales separadas y autorizadas.
19. rebuildFromMarkdown sobrescribe JSON y review desde texto editado y regenera sus secciones sin tocar ningún byte del Markdown; chunks e indexación usan el texto final, sin OCR ni extracción de imágenes.
20. El review anterior se sobrescribe sin copia histórica. Se conservan las imágenes referenciadas del inventario y se eliminan las que ya no se usan; no se atribuyen grades, páginas ni coordenadas originales al texto corregido.
21. Corregir text en fixtures de transcript.json cambia el contenido de los chunks y conserva IDs, orden, origen y tiempos de los segmentos; no se llama a Speech. La implementación de la pantalla y el guardado .NET siguen fuera de alcance.
22. ocrLanguage acepta exactamente los siete códigos documentados, aplica es al omitirlo y rechaza null/vacío/no admitidos. La selección llega al motor fijado sin sustituciones; recursos de los siete idiomas verificados y calidad OCR real pendiente identificada por idioma.
23. La documentación de integración establece bloqueo al aprobar y ninguna indexación automática por conversión. No afirmar que esas garantías .NET ya están implementadas por haber pasado pruebas Python.
24. El alcance de N3 es la integración, no reparar el OCR ni garantizar reconocimiento carácter a carácter. Mantener las limitaciones de calidad como diagnósticos separados; opciones ignoradas, resultados perdidos o estados parciales tratados como éxito sí son defectos de integración.
25. review.json inventaría las ocurrencias FormulaItem con IDs locales repetibles, referencias/secciones/páginas disponibles, texto conservado y latex nullable. formulaCount coincide con el array; informes antiguos usan []/0 y medios no infieren fórmulas. Probar escapes JSON, ocurrencias repetidas y reconstrucción sin inventario/páginas originales, registrando las limitaciones del parser y del modelo real.

## 20. Pendiente de configuración, no de arquitectura

- Selección de embeddings aprobada: AzureOpenAI / text-embedding-3-small / 1536 /
  cl100k_base. Pendientes: aprovisionar un recurso Azure OpenAI autorizado, configurar
  su endpoint/deployment/autenticación y verificar llamadas reales expresamente
  autorizadas. No existe deployment ni revisión de modelo aprobada; no inventarlos.
- Identidad y snapshot definitivo de perfil, presupuesto de chunks, distancia,
  colección y límites/cuotas de producción. Los valores sintéticos de pruebas no
  son decisiones de despliegue. N10 tiene evidencias locales, no integración Azure
  ni publicación de producción verificadas.
- Alojamiento/credenciales Qdrant y colecciones iniciales.
- Nombres físicos de colas, repositorios GHCR, tres apps y entorno Azure.
- Identidades/OIDC, secretos, callbacks, permisos y límites operativos.
- Calidad OCR real por idioma de los siete códigos admitidos, locks de recursos para las imágenes, idiomas Speech y política YouTube soportada por la versión fijada. Los idiomas OCR y su valor predeterminado ya están acordados.
- Reconciliación de avances del agente contra esta nueva especificación.

No bloquear conversión local por no tener recursos de despliegue. No inventar esos valores ni contactar servicios reales para descubrirlos.

## 21. Referencias técnicas

- [Docling: opciones y artefactos locales](https://docling-project.github.io/docling/usage/advanced_options/)
- [Docling: chunking](https://docling-project.github.io/docling/concepts/chunking/)
- [Docling: confidence](https://docling-project.github.io/docling/concepts/confidence_scores/)
- [Docling Core](https://github.com/docling-project/docling-core)
- [Azure Speech Fast Transcription](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/fast-transcription-create)
- [yt-dlp: dependencias](https://github.com/yt-dlp/yt-dlp#dependencies)
- [Qdrant: filtros](https://qdrant.tech/documentation/search/filtering/)
- [Qdrant: puntos](https://qdrant.tech/documentation/manage-data/points/)
- [Azure Container Apps: GitHub Actions y GHCR](https://learn.microsoft.com/en-us/azure/container-apps/github-actions)

Las referencias se contrastan con las versiones realmente fijadas. Los contratos definidos aquí son de nuestro componente, no promesas de una API externa.
