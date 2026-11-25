# Prepare and gate three independent worker deployments

N15 supplies offline ARM generation and a manual, one-worker-at-a-time Container
Apps workflow. **No Azure environment, app, queue, identity or deployment is
verified or created by local checks.** Physical settings remain explicit inputs.
Use complete N14 `release.json` digest records; a build-only or partial publication
cannot be deployed through this path.

## Quick path

1. Have the authorized environment owner supply the prerequisites below and the
   complete desired configuration. Preserve the approved converter's existing
   app/environment/identity/resource settings where compatible; no such production
   snapshot has been supplied to this repository. Do not substitute fixture values.
2. Prepare/review the three templates locally, without login or network access:

   ```powershell
   .venv\Scripts\python.exe tools/container_apps.py prepare --config <controlled-config.json> --release <release.json> --run-metadata <publication-run.json> --sha <full-sha> --run-id <run-id> --attempt <attempt> --output .local/n15/reviewed
   ```

   The output directory must be new. Outputs are `document.arm.json`,
   `media.arm.json`, `index.arm.json` and `deployment-plan.json`. They contain only
   declared configuration and Key Vault references, never fetched secret values.
   Local run metadata is supplied by the operator; the workflow obtains it from
   the same repository's GitHub API before login. Offline metadata is not remote
   publication attestation.
3. After explicit rollout authorization, dispatch `deploy-workers.yml` on `main`,
   selecting the protected GitHub environment, **one** worker and the exact N14
   commit/run/attempt. `authorize` and `cutover_confirmed` default to false. The
   selected environment must also enable deployment explicitly. Repeat separately
   for each role only after evaluating the previous role's outcome.

There is no push/workflow-run deployment trigger and no automatic three-app
transaction. Local preparation never runs `az`, `gh`, a registry client or an
application service. Tests use synthetic destinations and an injected CLI double.

## Required environment and bootstrap inputs

| Owner-supplied prerequisite | Required boundary |
| --- | --- |
| Azure subscription/resource group, standard Container Apps environment, location/workload profile | Already provisioned and authorized. Express environments do not support this custom KEDA/Key Vault configuration. |
| Three physical app names, GHCR repositories, new queues and the legacy mixed queue | Distinct assignments, never inferred from logical names. Existing app lookup fails before mutation if an app is absent or in another environment/location. |
| Per-app runtime UAMI/client ID, scaler UAMI, secret-reader UAMI | Explicit resource IDs attached to that app. Identities cannot cross worker boundaries; roles within one app may use the same identity if explicitly authorized. |
| Source/output/state Blob containers and controlled prefixes | Runtime Blob permissions: source read, outputs/state read/write/lease as appropriate. Index needs read access to its saved source/review artifacts and write access to technical state. Containers are not created. |
| Three Service Bus queues, queue lock/MaxDeliveryCount, DLQ monitoring | Runtime **and scaler** permissions must be granted explicitly, e.g. Azure Service Bus Data Receiver at the authorized queue scope. Runtime receiver authentication does not configure KEDA. No Topics or fourth queue. |
| Versioned Key Vault secret URIs and secret-reader permissions/network access | App-scoped secret names; Key Vault Secrets User or equivalent approved access. No raw secret values in the configuration. |
| GHCR pull username and read-packages credential in Key Vault | Separate from the N14 publisher's GITHUB_TOKEN and from Azure deployment OIDC. Include any organization/SSO package authorization. Azure managed identity is not used to authenticate to GHCR. |
| Speech endpoint/key; Azure OpenAI deployment/key; Qdrant URL/auth/profile snapshots | Existing runtime contracts apply. N15 does not provision embeddings or choose production profiles/quotas. The current index command requires explicit Azure `apiKey` mode. |
| Callbacks, routing, resources, replica/concurrency/grace settings | Review target-specific limits and consumer readiness before enabling. Secrets use references; callback/endpoint configuration is never discovered from user credentials. |

The workflow **updates existing apps only**. For the missing media/index apps, an
authorized bootstrap owner must first create the queues, identities/RBAC, state
containers, Key Vault references and app resources using reviewed settings. The
generated one-resource templates describe the desired apps, but this workflow
does not create prerequisites or bypass the existing-app check. Bootstrap must
keep producers paused and avoid starting incompatible consumers; validate model/
tokenizer access, UID 10001's temporary-volume permissions and all service routes
before enabling production. Record bootstrap separately, including exact targets
and observed results. No bootstrap commands have been executed here.

## Controlled configuration shape

`CONTENT_PROCESSING_AZURE_CONFIG` is a JSON object with exactly:

```json
{
  "schemaVersion": 1,
  "subscriptionId": "<subscription-uuid>",
  "resourceGroup": "<existing-resource-group>",
  "environmentId": "<full-existing-standard-environment-resource-id>",
  "location": "<existing-location>",
  "serviceBusNamespace": "<namespace-without-servicebus.windows.net>",
  "legacyQueue": "<known-legacy-mixed-queue>",
  "workers": {
    "document": "<document-worker-object>",
    "media": "<media-worker-object>",
    "index": "<index-worker-object>"
  }
}
```

Replace each worker placeholder with an object containing all the following
fields. These placeholders deliberately fail validation, rather than selecting
physical destinations. `tests/unit/test_deployments.py::inputs` contains a full
**synthetic** three-worker fixture, not a deployable environment recommendation.

| Worker field(s) | Required value |
| --- | --- |
| `appName`, `queueName`, `imageRepository` | Explicit app/queue and lowercase `ghcr.io/owner/repository`, without tag/digest. Repositories must match all three release entries exactly. |
| `runtimeIdentity`, `runtimeClientId`, `scalerIdentity`, `secretsIdentity` | UAMI resource IDs and runtime client UUID. No ambient identity lookup. |
| `registryUsername`, `registryPasswordSecret` | Explicit GHCR reader username and declared app secret name. |
| `secrets` | Array of `{ "name": "<app-secret-name>", "keyVaultUrl": "https://<vault>.vault.azure.net/secrets/<name>/<version>" }`. The generator supplies `secretsIdentity`; `value` is forbidden. |
| `resources` | `{ "cpu": <positive-number>, "memory": "<positive-number>Gi" }`. No sizing default. Azure must validate the workload profile's supported CPU/memory combinations. |
| `workloadProfileName`, `tags` | Existing profile name and complete desired string tag map. The release tag is added. |
| `minReplicas`, `maxReplicas`, `concurrency` | Explicit integers; minimum >=0, maximum 1..1000, minimum <= maximum. Document concurrency is **1** initially; media/index concurrency is supplied independently. |
| `messageCount`, `pollingInterval`, `cooldownPeriod` | Independent queue threshold/poll/cooldown integers; threshold/poll >0, cooldown >=0. No HTTP scaler. |
| `terminationGracePeriodSeconds` | Explicit positive grace period, subject to actual platform support and measured drain requirements. It does not guarantee every long-running job finishes before forced termination. |
| `env` | Required role-specific settings below, plus explicitly reviewed runtime options. Plain strings or `{ "secretRef": "<declared-name>" }`. Key/token/password fields require references. |

Required `env` settings:

- All: `AZURE_STORAGE_ACCOUNT_URL`, `SOURCE_CONTAINER_NAME`, `WEBHOOK_CALLBACKS`,
  `WEBHOOK_API_KEY` (reference).
- Document/media: `DESTINATION_CONTAINER_NAME`, `PUBLICATION_STATE_CONTAINER_NAME`,
  `PUBLICATION_STATE_PREFIX`.
- Media: `SPEECH_ENDPOINT`, `SPEECH_RESOURCE_KEY` (reference).
- Index: `INDEX_STATE_CONTAINER`, `INDEX_STATE_PREFIX`, `INDEX_PROFILES` (nonempty
  immutable snapshot JSON string), `INDEX_QDRANT_URL`, `INDEX_QDRANT_AUTH_MODE`,
  `INDEX_QDRANT_API_KEY` (reference if `apiKey`), `AZURE_OPENAI_ENDPOINT`,
  `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_AUTH_MODE=apiKey`,
  `AZURE_OPENAI_API_KEY` (reference).

The generator owns `AZURE_CLIENT_ID`, all four known queue assignments, the fully
qualified Service Bus namespace, `MAX_CONCURRENT_JOBS`, `/tmp/akay` and `TMPDIR`,
`DOCLING_ARTIFACTS_PATH=/opt/docling/models` (document only) and
`INDEX_TOKENIZER_PATH=/opt/tokenizers/cl100k_base.tiktoken` (index only). They match
the existing images/settings. Do not repeat/override them in `env`. This prepared
Azure path uses managed identity for Blob/Service Bus; local SAS/emulator modes
remain available in the application, not in these deployment templates.

ARM leading-bracket literals are escaped, so JSON profile arrays cannot become
template expressions. Full profile semantics, secret values and optional runtime
budget constraints remain validated by the existing application at startup, not
proved by a non-secret deployment configuration check.

## GitHub authorization and delivery

Configure the selected GitHub environment with required reviewers/branch
protection and an approved OIDC federated credential for that environment's exact
subject. Supply these environment variables explicitly:

| Variable | Value |
| --- | --- |
| `CONTENT_PROCESSING_DEPLOYMENT_ENABLED` | Exactly `true` to permit login/application. Missing/false fails before Azure login. |
| `CONTENT_PROCESSING_AZURE_CONFIG` | The complete non-secret JSON configuration above. |
| `AZURE_DEPLOY_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | Approved OIDC deployment identity/tenant/subscription; subscription must match the plan. This identity is separate from app runtime identities. |

The OIDC principal needs only the authorized target resource/deployment writes,
reads and managed-identity assignment rights; it does not need data-plane Speech,
embeddings, Blob or GHCR push credentials. No workflow creates role assignments.
Environment approval rules and Azure RBAC are external prerequisites, not YAML
guarantees. Only the manual deployment job has `id-token: write`; it has no
`packages: write`. N14 publication remains independently gated and unchanged.

Before OIDC login, the workflow downloads the exact named artifact from the
selected same-repository N14 run/attempt and checks API run metadata: main branch,
manual publication workflow path, successful conclusion, commit/run/attempt and
complete matching three-repository digest set. Expired/missing artifacts stop the
run; do not synthesize `release.json` from mutable tags. Keep approved complete
release records under controlled retention for rollback. The N14 artifact's
common root is `.local`, so its downloaded release path is `n14/release/release.json`.

Application uses Azure CLI **2.81.0**, no Container Apps extension/dynamic install,
and ARM API **2025-07-01**. Each dispatch checks the selected existing app, validates
its one-resource template, applies it in **Incremental** mode, then confirms the
returned app properties/image/identity/routes/scale/secret references. Template
files must still match the prepared plan. Azure errors are not dumped into logs.
The explicit runner-temp Azure config is mounted by azure/cli at `/root/.azure`;
neither it nor the downloaded smoke logs is uploaded as deployment evidence.
The apply command requires that dedicated `--azure-config /root/.azure` directory
and scrubs inherited environment/credentials from its CLI subprocesses. Without an
explicit config directory it cannot fall back to a developer's default Azure login.

The selected app's configuration is desired state, not a merge patch: reconcile
the complete secret/tag/identity/env inventories before adopting an existing app.
Apps with existing ingress or sidecar/init containers fail before mutation.
Incremental ARM mode preserves other resources but does not merge an app's omitted
properties. No pre-existing production configuration is replaced locally.

Only a confirmed apply emits `<worker>.applied.json` with
`status=applied-control-plane-only`. Provisioning acknowledgement is **not** service
smoke, startup/readiness, permission, scale-from-zero or .NET acceptance evidence.
Timeouts or failed postchecks can leave an applied revision without this record;
inspect the exact Azure deployment/app before retrying. Never claim rollback or
successful deployment merely because generated JSON or workflow lint passes.

## Cutover, mixed releases and rollback

1. Preserve the currently approved converter snapshot/digest/settings and prior
   complete release records. Establish compatible callback contracts and paused
   producer routes. No approved physical snapshot is assumed from README examples.
2. Pause old producers and the old mixed consumer through the authorized operator
   process. Drain or explicitly reconcile its active messages/locks and inspect the
   mixed queue/DLQ. Do not redirect a document-only app to that backlog. Changing
   HTTP traffic percentages cannot route or stop a queue worker.
3. Bootstrap/update the three **distinct** routes with producers paused. Apply one
   role at a time from the same complete release identity; verify that role's
   startup, pull secrets, Blob/state, Service Bus receiver **and scaler**, callback,
   models/tokenizer/tools and resources. Single-revision mode avoids intentionally
   retaining competing revisions, but rolling replacement can still overlap.
4. Enable only tested producer routes, then explicit final-artifact indexing after
   consumer approval. Mixed-release windows require compatible contracts/receipts;
   if compatibility is uncertain, keep producers/affected consumers paused until
   all three matching roles pass. Conversion never triggers indexing automatically.
5. On failure, stop affected routes/consumers, drain/reconcile in-flight work, then
   manually dispatch the affected role with the **previous complete release's**
   commit/run/attempt and its compatible full configuration. Apply other roles
   separately if needed. App-wide secrets/identities/config are not revision-local;
   a revision activation alone is not full rollback. No automatic rollback occurs.
6. Restore the legacy mixed consumer only with its previous image/config and legacy
   envelope producer routes after new consumers have stopped. Never run it on the
   new index queue or release version-one work into a legacy backlog. Preserve
   published artifacts, technical receipts and N11's uncertain-write barrier;
   deployment rollback cannot repair state or authorize stale Qdrant mutations.

No Akay.Be deployment, code, schema or migration is included. The actual cutover
and producer changes require their own authorized integration work.

## Evidence and pending work

[Progress](docling-rag-progress.md) records RED/GREEN, actual local CLI preparation,
existing-settings compatibility, injected Azure command/postcheck tests and
actionlint/ShellCheck. N13/N14 image evidence is reused because app code, runtime
locks and Dockerfiles are unchanged by N15.

Pending external checks: physical configuration/bootstrap; complete remote N14
publication; GitHub artifact/approval/OIDC execution; Azure CLI container execution
and ARM validation/application; actual GHCR pull/Key Vault/RBAC/network; UID/temp
volume permissions; app readiness/model loading; independent scale-from-zero,
resource sizing/grace under load; staging callbacks/order/retries and coordinated
rollback/cutover. No live application call, login or cloud operation ran locally.
The [N16 handoff](content-processing-handoff.md) supplies reproducible local
end-to-end/operator/.NET integration evidence, retaining these external gaps
rather than claiming a deployed system.

## Verified API references

- [Microsoft.App/containerApps 2025-07-01 schema](https://learn.microsoft.com/azure/templates/microsoft.app/2025-07-01/containerapps)
  — custom scaler identity, Key Vault references, registry passwordSecretRef,
  Single revisions, EmptyDir and termination grace; no invented HTTP worker probe.
- [Container Apps scaling](https://learn.microsoft.com/azure/container-apps/scale-app)
  and [ephemeral storage](https://learn.microsoft.com/azure/container-apps/storage-mounts#ephemeral-storage)
  — no-ingress needs a custom scaler; EmptyDir shares the platform CPU-dependent
  ephemeral capacity, not N13's Docker tmpfs hard quota. No unsupported per-volume
  `sizeLimit` or read-only-root flag is invented in the ARM schema.
- [Azure CLI 2.81.0 deployment arguments](https://github.com/Azure/azure-cli/blob/azure-cli-2.81.0/src/azure-cli/azure/cli/command_modules/resource/_params.py)
  and [commands](https://github.com/Azure/azure-cli/blob/azure-cli-2.81.0/src/azure-cli/azure/cli/command_modules/resource/commands.py).
- [azure/login v2](https://github.com/Azure/login/tree/v2),
  [azure/cli v2 configuration/mount implementation](https://github.com/Azure/cli/blob/v2/src/main.ts),
  [download-artifact v4 inputs](https://github.com/actions/download-artifact/tree/v4).
