# Open Managed Agents deployment configuration

Apply this reference only to an explicitly selected Open Managed Agents deployment. The official skill owns the workflow.

At the upstream authentication step, configure the selected OMA API base URL and its key through `ANTHROPIC_BASE_URL` and `ANTHROPIC_API_KEY`. Use the SDK's documented base-URL option where necessary. This target uses OMA credentials instead of Anthropic Console login or cloud-provider authentication. Resolve missing connection settings from the user or project configuration before making a request; no deployment hostname is a default. Planning can follow the upstream flow before credentials are available.

OMA may expose non-Claude models through the Anthropic-compatible API. For an explicit OMA task, the original project's provider does not change the selected target. Select from the deployment's actual model catalog using the official CLI or SDK. Upstream model IDs, model-specific defaults, prices and feature availability require confirmation against that deployment.

Keep target and workspace resource-ID mappings in separate upstream lockfiles. Declarative resource files may be shared. Use returned resource IDs when the deployment's management-link format is unknown.

Continue with upstream tools, descriptions, schemas, SDKs and validation guidance. Report deployment-specific incompatibilities with their observed scope. Add a separate extension only for an implemented OMA feature with no upstream equivalent and an authoritative contract; this release defines no additional tool or workflow.
