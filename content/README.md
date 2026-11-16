# Curriculum corpus

Emma retrieves from this folder at turn time and ingests it into Postgres/pgvector through
`POST /api/admin/ingest`.

Every file is Markdown with a small YAML-ish header:

```markdown
---
slug: present-perfect-vs-past-simple
title: Present perfect vs past simple
kind: grammar
level: B1
---

Body text...
```

Fields:

| Field | Required | Values |
|---|---|---|
| `slug` | no | unique id; defaults to a slugified title |
| `title` | no | defaults to the filename |
| `kind` | no | `grammar` \| `usage` \| `scenario` (default `grammar`) |
| `level` | no | `A1` \| `A2` \| `B1` \| `B2` \| `C1` (default `A1`) |

Scenario files additionally carry `setting`, `learner_role`, `emma_role`, `opening_line`,
`target_language` and `success_criteria`. Those rows seed the `scenario` table at startup.

Files under `scenarios/` are read twice on purpose: their header seeds the `scenario` table,
and their body is also retrieved as reference material for the tutor.

Drop a new file in, restart (or re-run ingest), and Emma will use it. Retrieval is filtered
to `level <= learner.cefr`, so a B1 learner never sees C1 notes.