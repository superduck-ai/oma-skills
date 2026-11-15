# OMA skills

- Treat Anthropic's Claude API skill as the source of truth for CMA workflows, tools, descriptions, schemas, and SDK usage.
- Make OMA deployment changes in `overlays/`. Generate `skills/claude-api/`; do not hand-edit the generated tree.
- Keep the official skill name and frontmatter unchanged. Do not create a second onboarding flow, CLI, SDK, or duplicate tool definitions.
- Add an OMA-specific capability only when an implemented feature has no upstream equivalent and has an authoritative contract.
- Run the local checks and authoritative upstream verification before publishing.
- Keep private endpoints, credentials, customer data, session IDs, and private acceptance transcripts out of this repository.
- Do not turn a deployment incident into a universal compatibility rule.
