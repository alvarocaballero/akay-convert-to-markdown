# Plan de implementación: Akay.Be · contenidos, revisión, secciones, fórmulas e indexación

**Objetivo:** adaptar la implementación EXISTENTE de subida de `TopicContent` y conversión con ConvertToMarkdown sin romper su circuito de Blob Storage → Outbox → Azure Service Bus → worker → webhook → actualizaciones de estado/notificaciones. **No rediseñar ese circuito desde cero.**

## 0. Instrucciones al agente: inspección obligatoria

Antes de cambiar código, localizar y explicar brevemente:

- Entidades `Topic`, `TopicContent`, enums de procesamiento/indexación, repositorios, EF mappings y migraciones/scripts SQL.
- Endpoints/handlers actuales de creación, edición y subida de contenidos; configuración de blobs y nombres almacenados.
- Eventos Outbox, publicación por `OutboxProcessor`, contrato actual de Service Bus y uso de `attemptId`.
- Webhook de conversión, validación del emisor, idempotencia, agregación del estado de `Topic` y lógica de notificaciones.
- Contratos y ejemplos reales de `review.json` / `docling.json` de la **versión actual** de ConvertToMarkdown, así como el modo `RebuildFromMarkdown`.
- Mecanismo disponible para indexación (si existe) y sus límites.

**No inventar nombres de clases ni campos del JSON:** adaptar este plan a las convenciones reales. Si faltan contratos de entrada o ejemplos de `review.json`, dejarlo identificado de forma explícita antes de mapear campos. No inventar extracción de secciones o fórmulas dentro de Akay.Be.

## 1. Reglas funcionales cerradas

### Contenido principal y secundarios

- `TopicContent.IsPrimary: bool` (por defecto `false`). Como máximo **un principal activo por Topic**.
- Principal: solo documento (`pdf`, `docx`, `pptx`, `md`, `txt` y los demás formatos documentales ya admitidos). Prohibidos audio y vídeo. Debe solicitarse extracción de secciones.
- Secundario: documento o audio/vídeo. No extraer secciones. Puede subirse y convertirse **sin sección asignada**.
- `TopicContent.TopicSectionId: int?`: nulo para principal; opcional para secundario.
- Para asignar sección a un secundario, el principal de ese mismo Topic debe existir, estar `Ready` y la sección debe pertenecer a ese Topic y principal.
- Un secundario puede estar `Ready` sin sección, pero **no puede indexarse** hasta que tenga una sección válida.
- Fórmulas: persistir únicamente para documentos, sean principales o secundarios; la información procede de `review.json` definitivo.
- No se permite modificar el Markdown cuando `ContentProcessingState == Ready`. La asignación de sección es un cambio de metadatos separado.

### Estados

`ContentProcessingState` recomendado (no hay datos existentes, se pueden renumerar; revisar serialización y dependencias):

- `Uploading=1`, `UploadFailed=2`, `Pending=3`, `Processing=4`, `PendingReview=5`, `Ready=6`, `Failed=7`.

`ContentIndexingState` permanece: `NotIndexed=0`, `Pending=1`, `Indexing=2`, `Indexed=3`, `Failed=4`.

Flujos:

1. **Subida con revisión y cambios:** `Uploading → Pending → Processing → PendingReview → Pending → Processing → Ready`.
2. **Subida con revisión y sin cambios:** `Uploading → Pending → Processing → PendingReview → Ready`.
3. **Subida sin revisión:** `Uploading → Pending → Processing → Ready`.
4. Errores de subida → `UploadFailed`; errores de conversión/reconstrucción/finalización → `Failed` cuando no proceda retry transitorio.

`PendingReview` significa que terminó la conversión inicial y el usuario debe decidir. Los casos A, B y C comparten **una única rutina de finalización** que persiste los datos finales antes de marcar `Ready`.

## 2. Cambios de persistencia

### `academic.topic_content`

- Añadir `is_primary boolean NOT NULL DEFAULT false`.
- Añadir `topic_section_id integer NULL` con FK a `topic_section`.
- Mantener `processing_attempt_id`, errores, nombres/rutas existentes y estados de indexación: reutilizarlos.
- Índice único parcial para el principal activo:

```sql
CREATE UNIQUE INDEX ux_topic_content_primary_active
ON academic.topic_content (topic_id)
WHERE is_primary = true AND deleted_at IS NULL;
```

- Validar en aplicación y, si es viable con las claves disponibles, reforzar en BD que `topic_section_id` sea del mismo Topic (FK compuesta `topic_section(id, topic_id)` o estrategia equivalente). Validar también `is_primary = false` para permitir `topic_section_id != null`.

### `academic.topic_section`

Tabla nueva. Mínimo: `id`, `topic_id`, `topic_content_id`, más **los campos reales de las secciones de `review.json`**. Candidatos a confirmar, no asumir como contrato: `source_section_id`, `title`, `level`, `display_order`, `parent_section_id`, `start_offset`, `end_offset`, `metadata jsonb`. Establecer índices, FKs e identidad de origen apropiadas. `topic_content_id` apunta al principal que define la sección. Revisar unidades de offsets y si el final es inclusivo/exclusivo (Python vs .NET difieren en representación de caracteres Unicode).

### `academic.topic_formula`

Tabla nueva. Mínimo: `id`, `topic_id`, `topic_content_id`, identificador de origen si existe, representación de la fórmula (`latex`, `text`/`value`, según `review.json`), ubicación/offsets si existen, y metadatos adicionales que sean útiles. No forzar a inventar posiciones que el JSON no suministre. Índices por Topic y Content; FKs coherentes.

**Fuente de verdad de secciones y fórmulas: siempre `review.json` definitivo.** `docling.json` y Markdown no se vuelven a analizar en Akay.Be para extraerlas.

Aplicar scripts/migraciones siguiendo la convención existente del proyecto. No introducir migraciones automáticas en `Program.cs`.

## 3. API de Akay.Be

### Ampliar subida existente

Añadir a su comando/DTO actual:

- `isPrimary: bool`.
- `requiresReview: bool` (solo para iniciar el procesamiento, **no** columna en BD).
- `sectionId: int?` (si se proporciona, validar reglas; no exigirlo a secundarios).

Derivar `extractSections = isPrimary` en backend; **no aceptar del cliente una combinación contradictoria**.

### `POST /api/topic-contents/{id}/approve`

Body: `{ "markdownModified": true | false }`.

- Solo válido desde `PendingReview`; autorización del profesor/administrador conforme a políticas existentes.
- `false`: leer artefactos finales ya disponibles, persistir secciones/fórmulas según corresponda y cambiar a `Ready` en una transacción. **Sin Service Bus ni Docling**.
- `true`: el frontend ya ha guardado el Markdown editado en el Blob existente; transacción que establece `Pending`, genera **nuevo** `processing_attempt_id` y crea evento Outbox para `RebuildFromMarkdown`. Se enviará `requiresReview=false`. Cuando el webhook confirme el rebuild, se finaliza y pasa a `Ready`.
- No permitir una segunda aprobación mientras está `Pending`/`Processing`; rechazar o devolver estado idempotente según convención API.
- No cambiar el nombre del Blob de Markdown ni mandar `destinationBlobName` en el rebuild.

### `PATCH /api/topic-contents/{id}/section`

Body: `{ "sectionId": 123 }` (o `null` para desasignar si está permitido).

- Solo secundarios. Principal `Ready`; sección válida del mismo Topic y perteneciente a ese principal.
- Permitir asignación posterior a la conversión, incluso si el secundario ya está `Ready`.
- **Seguridad de indexación:** prohibir cambio/desasignación durante `Pending`/`Indexing`. Si está `Indexed`, o implementar invalidación y reindexación seguras, o bloquear el cambio en esta fase; nunca dejar embeddings indexados con sección incorrecta. Documentar la política finalmente adoptada.

### `POST /api/topic-contents/{id}/index`

- Solo `ContentProcessingState == Ready`; para secundario, exigir `TopicSectionId` válido.
- Validar permisos y que no exista indexación activa. Si ya está `Indexed`, no reindexar sin una operación explícita admitida.
- En transacción: `ContentIndexingState=Pending`, generar intento de indexación si procede, registrar Outbox para el indexador existente.
- El procesamiento real mueve `Pending → Indexing → Indexed|Failed` de forma idempotente.
- **Si aún no existe indexador:** implementar contrato y orquestación por separado del motor de embeddings, con un adaptador claramente identificado; no simular `Indexed` ni generar embeddings ficticios.

## 4. Contratos Service Bus y webhook

Reutilizar el mensaje existente (`userId`, `contextId`, `documentId`, `fileName`, `sourceBlobName`, `callback`, `attemptId`, etc.) y añadir lo imprescindible:

- `operation`: valor de conversión inicial ya soportado / `RebuildFromMarkdown` (respetar exactamente el nombre que entiende el worker).
- `requiresReview`: `true`/`false`.
- `extractSections`: derivado de `IsPrimary`.

**Rebuild:** enviar `operation=RebuildFromMarkdown`, `sourceBlobName` del Markdown revisado, **omitir `destinationBlobName`**, `requiresReview=false`, `extractSections=IsPrimary`. El worker existente mantiene el MD y reemplaza los artefactos (`review.json`, `docling.json`, imágenes) del mismo contenido.

Webhook de éxito: conservar campos actuales y disponer de `attemptId`, `operation` y `requiresReview` para tomar la decisión. **Verificar si realmente los devuelve el worker**; si falta alguno, registrar como dependencia contractual con ConvertToMarkdown. No añadir `RequiresReview` a la tabla únicamente para compensar un webhook incompleto. Validar autenticación del callback, pertenencia del intento y transición esperada.

- Conversión inicial + `requiresReview=true` → `PendingReview`, sin persistencia todavía de secciones/fórmulas finales.
- Conversión inicial + `requiresReview=false` → rutina de finalización → `Ready`.
- Rebuild + `requiresReview=false` → rutina de finalización → `Ready`.

## 5. Finalización transaccional e idempotencia

Crear/reutilizar un servicio de aplicación **único** para finalizar contenido (sin duplicar lógica entre aprobación y webhook):

1. Leer `review.json` **fuera de la transacción**; validar estructura y correspondencia con el Content/Topic. Para audio/vídeo sin fórmulas/secciones, no exigir JSON que no aplique.
2. Iniciar transacción PostgreSQL; obtener el Content con control de concurrencia; revalidar estado e `attemptId` cuando proceda.
3. Persistir las `topic_section` del principal según JSON y las `topic_formula` correspondientes. En `PendingReview`, todavía no hay secciones definitivas por lo que no hay secundarios asignados a ellas; evitar recreaciones posteriores sin garantías de referencias.
4. Cambiar `ContentProcessingState` a `Ready` **en esa misma transacción** y dejar `ContentIndexingState=NotIndexed` hasta indexación explícita.
5. Registrar en Outbox los eventos que ya correspondan al flujo actual, sin duplicarlos, y confirmar transacción.

Si fallan persistencia o validación, **no marcar `Ready`**. Clasificar errores transitorios/reintentables y definitivos. Asegurar que repetir webhook/approve no duplique secciones, fórmulas ni notificaciones persistentes. Utilizar `processing_attempt_id` para descartar callbacks antiguos; al recibir `Ready` para el mismo intento, devolver éxito idempotente.

Al reenviar mensajes para el mismo contenido, evitar que workers de intentos antiguos sobrescriban artefactos del intento nuevo. Comprobar qué protege actualmente el worker/Blob (serialización por Content, verificación de intento, ETag o publicación condicional). No asumir que descartar el webhook antiguo evita esas escrituras. Implementar la mínima protección compatible, documentando si exige trabajo posterior en el worker.

## 6. CRÍTICO: conservar las notificaciones existentes

El flujo actual **ya funciona** y debe seguir funcionando:

- En cada callback de finalización de conversión inicial se envía el evento/notificación **no persistente** cuando quedan otros archivos pendientes.
- Cuando ya no quedan archivos pendientes de conversión inicial, se envía la notificación **persistente** de finalización del lote.
- Conservar los nombres, interfaces, destinatarios, agregación de estados, Outbox y mecanismos de SignalR/eventos usados hoy (`FileUploadedUpdated` y `UploadBatchCompleted` si esos son los nombres reales).
- `PendingReview` **no es una conversión pendiente**; para la notificación de fin de lote, se considera que el worker ya terminó ese Content, aunque falte la aprobación humana. No equivale a `Ready` para el estado global del Topic.
- El rebuild/approve/indexación **no son una nueva subida**: no deben generar falsos `UploadBatchCompleted` ni duplicar notificaciones del lote original.
- Verificar el comportamiento cuando existen varias conversiones concurrentes, una termina en `PendingReview`, otras fallan, o dos callbacks llegan a la vez. Conservar la semántica existente para fallos y pendientes y asegurar que la persistente se emite solo una vez por lote según la identidad/dedupe ya existente.
- Si la lógica actual usa `Ready` como sinónimo de «conversión finalizada», corregir esa condición de manera localizada sin reescribir todo el sistema de notificaciones.

**No eliminar ni sustituir las notificaciones actuales por otras nuevas.** El cambio principal es que una conversión exitosa puede finalizar en `PendingReview` o en `Ready`.

## 7. Agregación del estado de Topic

Revisar la lógica existente de estado agregado:

- `PendingReview` es contenido **todavía no Ready**, aunque la conversión haya acabado.
- Un `Topic` no se convierte en `Ready` por el mero hecho de que todos los contenidos estén en `PendingReview` o hayan terminado en el worker; solo cuando cumpla la regla vigente de todos los contenidos `Ready`.
- Separar esa regla del criterio de «no quedan conversiones pendientes» utilizado por la notificación del lote.
- La indexación del Topic sigue su lógica independiente, con los nuevos requisitos de sección para secundarios.

## 8. Tests obligatorios

1. Índice único: rechaza dos principales activos para un Topic; prohíbe principal audio/vídeo.
2. Subida de secundario sin sección aceptada; no indexable; asignación válida solo tras `Ready` del principal y únicamente a sección de su Topic.
3. Con revisión: conversión → `PendingReview`; sin revisión: conversión + persistencia → `Ready`.
4. `approve(markdownModified=false)` → `Ready`, sin cola adicional, sin duplicados.
5. `approve(markdownModified=true)` → nuevo `attemptId`, `Pending` + Outbox; `RebuildFromMarkdown` con `sourceBlobName` y **sin** `destinationBlobName`; webhook → `Ready`.
6. Los datos de `topic_section` y `topic_formula` reflejan el **review.json final**, no el borrador ni docling.json; secundarios no crean secciones.
7. Si falla el parseo o guardado de metadatos, la transición a `Ready` no queda confirmada a medias.
8. Webhook duplicado/antiguo, llegada fuera de orden y reintentos Service Bus: no duplican DB/eventos.
9. Mantener los dos tipos de notificación existentes para 1 o N archivos, con mezcla de `PendingReview`, `Ready` y fallos; rebuild no dispara una nueva finalización de lote.
10. Indexación: solo `Ready`; secundario requiere sección; bloqueo durante indexación; no marcar `Indexed` hasta confirmación del indexador.
11. Inmutabilidad de Markdown en `Ready`; aprobación repetida y cambios concurrentes a estados incorrectos rechazados.
12. Tests de integración de FKs/índice parcial, transacciones y Outbox con PostgreSQL cuando exista infraestructura de tests.

## 9. Orden de trabajo y entregables

**Fase 1:** inspección del código y contratos reales; identificar exactamente qué piezas se reutilizan y la compatibilidad requerida con ConvertToMarkdown. Entregar breve mapa de clases/métodos afectados.

**Fase 2:** entidades, enums, EF mappings, validaciones, tablas e índices; tests de dominio/DB.

**Fase 3:** adaptar subida, publicación de Outbox y callback para revisión opcional; implementar servicio de finalización con `review.json`; conservar/agregar tests de notificaciones.

**Fase 4:** endpoint `approve`, operación de reconstrucción y endpoints de asignación; tests completos de A/B/C, idempotencia y concurrencia.

**Fase 5:** endpoint de indexación y conexión con el mecanismo real de indexación disponible, o dejar el motor separado y explícitamente pendiente si no existe. Tests de transición y validación.

### Criterios de aceptación

- Las tres rutas A/B/C funcionan y alcanzan `Ready` **solo** cuando los metadatos definitivos están guardados.
- Secundarios sin sección son válidos pero no indexables.
- Secciones y fórmulas provienen únicamente de `review.json`; principal define las secciones.
- No se introduce columna `RequiresReview`.
- Se reutiliza la arquitectura actual de Blob, Outbox, Service Bus y webhooks, y se **preservan exactamente** las notificaciones persistentes y no persistentes que ya existen.
- Rebuild conserva el nombre del MD y actualiza los artefactos sin proporcionar `destinationBlobName`.
- Reintentos/callbacks duplicados no corrompen estados ni generan dobles notificaciones.
- Se entregan scripts SQL, código y pruebas; enumerar explícitamente cualquier dependencia real de cambios en ConvertToMarkdown.

**Antes de editar:** si hay discrepancia entre este plan y el contrato real de `review.json` o de los webhooks, no adivinar. Explicar la discrepancia y proponer el ajuste mínimo compatible. Evitar refactors no relacionados.
