# Spec: ampliar ConvertToMarkdown para audio, vídeo y YouTube

## 1. Objetivo

Ampliar el componente existente `ConvertToMarkdown` para que sea el único responsable de **normalizar distintos tipos de contenido a Markdown**.

Actualmente procesa documentos como PDF, DOCX, PPTX, HTML, TXT y MD. Debe ampliarse para soportar también:

- audio;
- vídeo;
- URLs de YouTube.

La entrada y la salida externas deben mantenerse iguales a las actuales:

```text
Service Bus message
    ↓
ConvertToMarkdown
    ↓
Markdown en Blob Storage
    ↓
Webhook a Akay.Be
```

`Akay.Be` no debe necesitar conocer qué estrategia interna se ha utilizado para obtener el Markdown.

---

## 2. Principio de diseño

`ConvertToMarkdown` debe convertirse conceptualmente en un **Content Processor**, aunque no es obligatorio cambiar el nombre del proyecto si eso supone cambios innecesarios.

Debe existir un único componente desplegable, pero con responsabilidades internas separadas.

Flujo general:

```text
Contenido de entrada
        ↓
Detectar tipo
        ↓
┌───────────────────────────────┐
│ Documento                     │
│ PDF/DOCX/PPTX/HTML/TXT/MD     │
│        ↓                      │
│ MarkItDown                    │
└───────────────────────────────┘

┌───────────────────────────────┐
│ Audio                         │
│ MP3/WAV/AAC/OGG/...           │
│        ↓                      │
│ Azure Fast Transcription      │
│        ↓                      │
│ Markdown                      │
└───────────────────────────────┘

┌───────────────────────────────┐
│ Vídeo                         │
│ MP4/MOV/MKV/WebM/...          │
│        ↓                      │
│ FFmpeg extrae audio           │
│        ↓                      │
│ Azure Fast Transcription      │
│        ↓                      │
│ Markdown                      │
└───────────────────────────────┘

┌───────────────────────────────┐
│ YouTube                       │
│ URL                           │
│        ↓                      │
│ yt-dlp                        │
│        ↓                      │
│ FFmpeg si es necesario        │
│        ↓                      │
│ Azure Fast Transcription      │
│        ↓                      │
│ Markdown                      │
└───────────────────────────────┘

                ↓
         Markdown final
                ↓
         Blob Storage
                ↓
        Webhook Akay.Be
```

---

## 3. Mantener el contrato actual

No modificar innecesariamente el contrato externo existente.

La entrada sigue llegando mediante Azure Service Bus y debe conservar los identificadores actuales:

```text
ContextId  = Subject.Id
DocumentId = TopicContent.Id
```

Si actualmente el mensaje contiene información adicional necesaria para localizar el contenido, mantenerla.

No introducir `TopicId` ni conocimiento específico de las entidades de Akay dentro de este servicio.

`ContextId` y `DocumentId` deben considerarse identificadores opacos.

---

## 4. Salida

Todos los tipos de contenido deben producir exactamente el mismo resultado conceptual:

```text
Markdown generado
```

El Markdown debe guardarse en Blob Storage utilizando las convenciones actuales del proyecto.

Después debe llamarse al webhook existente de `Akay.Be` utilizando el mismo contrato actual siempre que sea posible.

El webhook debe seguir permitiendo identificar como mínimo:

```text
ContextId
DocumentId
estado del procesamiento
resultado / ubicación del Markdown
error, si existe
```

No crear un webhook distinto para documentos, audio o vídeo.

---

## 5. Arquitectura interna

Evitar una única clase con toda la lógica.

Separar internamente las estrategias de procesamiento. Una posible estructura es:

```text
processors/
    document_processor
    audio_processor
    video_processor
    youtube_processor

services/
    fast_transcription_service
    ffmpeg_service
    youtube_download_service
    markdown_builder
```

Los nombres exactos deben adaptarse a las convenciones actuales del proyecto.

No crear abstracciones innecesarias. El objetivo es separar responsabilidades, no construir una arquitectura ceremonial.

---

## 6. Documentos existentes

Mantener el comportamiento actual para:

- PDF;
- DOCX;
- PPTX;
- HTML;
- TXT;
- MD;
- cualquier otro formato ya soportado actualmente.

Seguir utilizando MarkItDown o la implementación actual.

No introducir breaking changes en esta parte.

---

## 7. Procesamiento de audio

Para archivos de audio utilizar **Azure AI Speech Fast Transcription** directamente desde `ConvertToMarkdown`.

No llamar a `Akay.To.AI` ni a `Akay.Be` para realizar la transcripción.

Flujo:

```text
Audio
  ↓
Azure Fast Transcription
  ↓
texto + segmentos + timestamps
  ↓
Markdown
```

Soportar inicialmente los formatos admitidos por Azure Fast Transcription que resulten razonables para Akay, por ejemplo:

```text
MP3
WAV
AAC
OGG / OPUS
FLAC
WebM audio
```

No implementar conversión arbitraria de codecs en esta rama salvo que ya exista una necesidad clara.

---

## 8. Azure Fast Transcription

Implementar la integración directamente mediante la API REST oficial de Azure AI Speech Fast Transcription.

No utilizar Batch Transcription.

No crear jobs.

No hacer polling.

El flujo debe ser:

```text
archivo de audio completo
      ↓
HTTP request
      ↓
Azure Fast Transcription
      ↓
respuesta completa
```

La integración debe:

- reutilizar la configuración/secretos del proyecto;
- aceptar cancelación;
- manejar errores HTTP;
- soportar retry únicamente para errores temporales;
- no registrar claves, tokens ni la transcripción completa.

---

## 9. Resultado de transcripción

Normalizar internamente la respuesta de Azure a un modelo similar a:

```text
TranscriptionResult
    Text
    Segments[]
        Start
        Duration
        Text
```

Los modelos exactos pueden variar según el lenguaje y arquitectura actual del proyecto.

No exponer los DTOs REST de Azure al resto de la aplicación.

---

## 10. Markdown generado desde audio

La transcripción debe convertirse a Markdown.

Formato recomendado:

```markdown
# Transcripción

## [00:00:12]

Introducción al tema...

## [00:03:47]

Ahora vamos a explicar la segunda ley de Newton...
```

Los timestamps deben conservarse porque posteriormente podrán utilizarse como metadatos durante chunking/RAG y para enlazar con el instante correspondiente del contenido multimedia.

No es necesario guardar timestamps palabra a palabra.

Los segmentos proporcionados por Azure son suficientes para esta primera versión.

---

## 11. Procesamiento de vídeo

Para vídeo, extraer primero la pista de audio utilizando FFmpeg.

Flujo:

```text
MP4/MOV/MKV/WebM/...
        ↓
FFmpeg
        ↓
audio
        ↓
Azure Fast Transcription
        ↓
Markdown
```

FFmpeg debe ejecutarse como proceso externo o mediante una librería suficientemente simple que lo encapsule.

Priorizar claridad y facilidad de mantenimiento.

---

## 12. Extracción de audio con FFmpeg

Siempre que sea posible, extraer la pista de audio sin recodificar.

Conceptualmente:

```text
vídeo con AAC
     ↓
extraer pista AAC
     ↓
Fast Transcription
```

Si el codec original no es compatible con Azure Fast Transcription, convertirlo a un formato compatible.

Formato de fallback recomendado:

```text
MP3 o WAV
```

No hacer:

- eliminación automática de silencios;
- cambio de velocidad;
- recortes;
- transformaciones que alteren innecesariamente la línea temporal.

---

## 13. Preservación de timestamps

La línea temporal del audio extraído debe corresponder con la del vídeo original.

Ejemplo:

```text
Vídeo 00:03:47
      ↓
Audio 00:03:47
      ↓
Transcripción 00:03:47
```

Esto permitirá posteriormente asociar una sección del Markdown con el instante exacto del vídeo.

Si alguna transformación altera la línea temporal, debe documentarse y evitarse salvo necesidad técnica.

---

## 14. YouTube

Añadir soporte para URLs de YouTube como fuente independiente.

Flujo previsto:

```text
YouTube URL
     ↓
yt-dlp
     ↓
mejor pista de audio disponible
     ↓
FFmpeg si necesita normalización
     ↓
Azure Fast Transcription
     ↓
Markdown
```

`yt-dlp` debe encargarse de resolver/obtener el contenido multimedia.

FFmpeg debe encargarse únicamente de extracción/conversión multimedia cuando sea necesario.

Mantener ambas responsabilidades separadas internamente.

---

## 15. YouTube como feature aislable

El soporte de YouTube debe poder activarse/desactivarse fácilmente mediante configuración o feature flag.

Esto permite desplegar inicialmente:

```text
Documentos + Audio + Vídeo
```

y habilitar YouTube posteriormente sin modificar el resto del pipeline.

---

## 16. Identificación del tipo de contenido

El processor debe determinar qué estrategia utilizar a partir de la información disponible.

Prioridad recomendada:

1. tipo explícito recibido en el mensaje, si ya existe;
2. MIME type;
3. extensión;
4. URL reconocida como YouTube.

No depender únicamente de la extensión si puede evitarse.

Debe existir una representación interna clara, por ejemplo:

```text
Document
Audio
Video
YouTube
```

---

## 17. Ficheros temporales

Audio y vídeo pueden requerir archivos temporales para FFmpeg/yt-dlp.

Utilizar un directorio temporal aislado por procesamiento.

Ejemplo conceptual:

```text
/tmp/{documentId}/{unique-id}/
```

Al finalizar, tanto correctamente como con error:

```text
eliminar archivos temporales
```

No acumular contenidos multimedia dentro del contenedor.

La limpieza debe realizarse también ante cancelaciones y excepciones.

---

## 18. Ejecución de procesos externos

Para FFmpeg y yt-dlp:

- capturar stdout;
- capturar stderr;
- comprobar exit code;
- aceptar `CancellationToken` o equivalente;
- terminar el proceso cuando se cancele el procesamiento;
- evitar procesos huérfanos;
- establecer timeout máximo;
- limitar el tamaño de logs almacenados.

No considerar correcto un procesamiento únicamente porque no se lanzó una excepción.

---

## 19. Concurrencia

FFmpeg y la descarga de contenido pueden consumir CPU, memoria y red.

Mantener limitada la concurrencia del worker.

Añadir una configuración similar a:

```text
MAX_CONCURRENT_JOBS
```

Utilizar inicialmente un valor conservador.

Ejemplo:

```text
2-4 trabajos simultáneos por instancia
```

El valor debe ser configurable y no quedar hardcodeado.

---

## 20. Límites

Añadir límites configurables para evitar trabajos descontrolados.

Como mínimo considerar:

```text
MAX_INPUT_SIZE_MB
MAX_MEDIA_DURATION_MINUTES
PROCESS_TIMEOUT_MINUTES
```

No fijar valores arbitrarios sin revisar primero las limitaciones actuales del proyecto y de Azure Fast Transcription.

---

## 21. Retry

Mantener/reutilizar la política de retry actual del componente.

Reintentar únicamente errores temporales, por ejemplo:

```text
HTTP 408
HTTP 429
HTTP 5xx
timeouts transitorios
errores de red
```

No reintentar automáticamente errores permanentes como:

```text
archivo corrupto
formato no soportado
vídeo sin audio
URL inválida
401 / 403
YouTube eliminado o privado
```

---

## 22. Idempotencia

El mensaje de Service Bus puede entregarse más de una vez.

El procesamiento debe ser idempotente en la medida de lo posible.

Antes de reprocesar, comprobar si el resultado Markdown correspondiente al `ContextId + DocumentId` ya existe y es válido según el mecanismo actual del proyecto.

No introducir lógica de dominio de Akay dentro del processor.

---

## 23. Errores

Normalizar los errores utilizando el patrón actual del proyecto.

Distinguir al menos:

```text
unsupported_format
source_not_found
invalid_media
no_audio_track
ffmpeg_failed
youtube_download_failed
speech_transcription_failed
speech_rate_limited
processing_timeout
cancelled
blob_read_failed
blob_write_failed
webhook_failed
```

El webhook debe recibir información suficiente para que `Akay.Be` pueda marcar el `TopicContent` como fallido y mostrar un error razonable.

No devolver stdout/stderr completos al usuario final.

---

## 24. Blob Storage

Mantener el comportamiento actual:

```text
leer contenido original desde Blob
        ↓
procesar
        ↓
guardar Markdown resultante en Blob
```

Los audios temporales extraídos de vídeos no necesitan persistirse permanentemente salvo que exista una razón funcional.

Por defecto:

```text
vídeo → audio temporal → transcripción → eliminar audio
```

El artefacto permanente debe seguir siendo el Markdown.

---

## 25. Webhook

Mantener el webhook existente.

No crear callbacks diferentes para cada tipo de contenido.

Flujo de éxito:

```text
procesamiento terminado
        ↓
Markdown guardado
        ↓
webhook actual
```

Flujo de error:

```text
procesamiento fallido
        ↓
webhook actual con estado/error
```

Si el webhook actual no soporta correctamente errores, ampliarlo de forma retrocompatible.

---

## 26. Service Bus

Mantener el mecanismo existente de consumo desde Azure Service Bus.

No crear nuevas colas para audio, vídeo o YouTube salvo que exista una necesidad demostrada.

El mismo worker debe recibir el mensaje y seleccionar internamente la estrategia adecuada.

Conceptualmente:

```text
ConvertContentToMarkdown message
        ↓
resolver estrategia
        ↓
procesar
```

---

## 27. Docker / runtime

Actualizar la imagen Docker para incluir las dependencias necesarias.

Como mínimo:

```text
ffmpeg
ffprobe
```

Para YouTube:

```text
yt-dlp
```

Mantener MarkItDown y las dependencias actuales.

Durante el build o startup debe ser posible validar las herramientas, por ejemplo:

```text
ffmpeg -version
ffprobe -version
yt-dlp --version
```

No descargar binarios dinámicamente en cada procesamiento.

---

## 28. Configuración de Azure Speech

Añadir la configuración necesaria para Fast Transcription siguiendo el mecanismo actual de configuración/secrets del proyecto.

No hardcodear:

- keys;
- regiones;
- endpoints;
- API versions.

Mantener secretos fuera del repositorio.

---

## 29. Seguridad

No registrar:

- claves de Azure;
- tokens;
- SAS completos;
- contenido de audio;
- transcripciones completas;
- URLs sensibles si contienen credenciales.

Sanitizar errores antes de enviarlos mediante webhook.

---

## 30. Tests unitarios

Añadir tests al menos para la selección de estrategia:

```text
PDF   → DocumentProcessor
DOCX  → DocumentProcessor
MP3   → AudioProcessor
WAV   → AudioProcessor
MP4   → VideoProcessor
MKV   → VideoProcessor
YouTube URL → YoutubeProcessor
unsupported → error
```

Añadir tests de:

```text
Fast Transcription response mapping
Markdown generation with timestamps
FFmpeg success
FFmpeg failure
video without audio
YouTube download failure
retryable Azure error
non-retryable Azure error
cancellation
timeout
cleanup temporary files
webhook success
webhook failure
```

Mockear las dependencias externas cuando sea razonable.

---

## 31. Tests de integración

Añadir tests de integración opcionales con archivos pequeños reales:

```text
sample.pdf
sample.mp3
sample.mp4
```

YouTube debe probarse separadamente y no debe hacer que la suite normal dependa de disponibilidad externa.

Los tests que requieran Azure Speech deben ejecutarse únicamente cuando existan credenciales explícitas de integración.

---

## 32. Logging y observabilidad

Registrar información útil sin incluir contenido sensible.

Ejemplos:

```text
Processing document {DocumentId} as Video
Extracting audio from {DocumentId}
Starting fast transcription for {DocumentId}
Transcription completed in X seconds
Markdown generated for {DocumentId}
Webhook completed for {DocumentId}
```

Registrar también duración total de cada fase para poder detectar cuellos de botella.

---

## 33. Fuera de alcance

No implementar en esta tarea:

```text
Topic.State
TopicContent.State
lógica de dominio de Akay.Be
comprobación de que todos los documentos de un Topic están Ready
chunking
embeddings
Qdrant
RAG
indexación
```

Todo eso pertenece a `Akay.Be` o a fases posteriores del workflow.

---

## 34. Flujo final esperado

```text
                         Service Bus
                              │
                              ▼
                     ConvertToMarkdown
                              │
                     detectar tipo
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
          ▼                   ▼                   ▼
      DOCUMENTO             AUDIO               VÍDEO
          │                   │                   │
      MarkItDown        Fast Transcription      FFmpeg
          │                   │                   │
          │                   │                   ▼
          │                   │                 Audio
          │                   │                   │
          │                   └──────────────┬────┘
          │                                  │
          │                          Fast Transcription
          │                                  │
          └────────────────┬─────────────────┘
                           │
                           ▼
                       Markdown
                           │
                           ▼
                     Blob Storage
                           │
                           ▼
                    Webhook Akay.Be
```

Para YouTube:

```text
YouTube URL
    ↓
yt-dlp
    ↓
FFmpeg (si es necesario)
    ↓
Fast Transcription
    ↓
Markdown
    ↓
Blob
    ↓
Webhook
```

---

## 35. Criterios de aceptación

La tarea se considera completada cuando el mismo mensaje de Service Bus utilizado actualmente permite procesar correctamente:

```text
PDF/DOCX/PPTX/HTML/TXT/MD
Audio
Vídeo
YouTube
```

Y todos terminan produciendo:

```text
Markdown en Blob Storage
        +
callback mediante el webhook existente
```

Además:

- no hay cambios innecesarios en el contrato externo;
- documentos existentes continúan funcionando;
- audio utiliza Azure Fast Transcription;
- vídeo utiliza FFmpeg + Fast Transcription;
- YouTube utiliza yt-dlp y FFmpeg cuando sea necesario;
- los timestamps del vídeo/audio se conservan en el Markdown;
- los archivos temporales se eliminan;
- la concurrencia está limitada;
- existen timeouts;
- existen retries únicamente para errores transitorios;
- el worker es idempotente;
- hay tests de las nuevas rutas;
- no se introduce dependencia de `Akay.To.AI` ni llamadas intermedias a `Akay.Be` para transcribir.

---

## 36. Restricción importante

Antes de implementar, inspeccionar la arquitectura y contratos actuales de `ConvertToMarkdown`.

Adaptar nombres, estructura de carpetas, modelos, configuración y patrones de error al código existente.

No reescribir componentes que ya funcionan salvo que sea necesario para incorporar las nuevas estrategias.

Priorizar una solución simple y mantenible frente a una refactorización general del proyecto.
