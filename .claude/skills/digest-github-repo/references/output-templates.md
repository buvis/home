# Output templates (digest-github-repo)

The Step 5 zettelkasten summary templates, one per mode. Placeholders follow the template field guide in SKILL.md.

## Curated-list mode

```markdown
---
id: <zettelkasten-id>
title: "<YYYYMMDD> - <repo-name> digest"
date: <YYYY-MM-DDTHH:mm:ss>
tags: [<tag1>, <tag2>, <tag3>]
type: github-repo-digest
publish: false
processed: false
repo: OWNER/REPO
---

# <YYYYMMDD> - <repo-name> digest

Digest of [OWNER/REPO](https://github.com/OWNER/REPO) — new items.

## <Section name>

<One-sentence description of what goes here>

- [ ] **<short-name>** — [<item-owner>/<item-repo>](https://github.com/<item-owner>/<item-repo>) — <description>. ★<count>

## Dropped

- [-] [<item-owner>/<item-repo>](https://github.com/<item-owner>/<item-repo>) — <reason>
```

Use `- [ ]` for items to evaluate, `- [-]` for items being dropped. Do not duplicate any item
from the dedup list.

## Activity-digest mode

```markdown
---
id: <zettelkasten-id>
title: "<YYYYMMDD> - <repo-name> digest"
date: <YYYY-MM-DDTHH:mm:ss>
tags: [<tag1>, <tag2>, <tag3>]
type: github-repo-digest
publish: false
processed: false
repo: OWNER/REPO
---

# <YYYYMMDD> - <repo-name> digest

Digest of [OWNER/REPO](https://github.com/OWNER/REPO) — recent activity.

## <Theme>

- <Prose sentence summarising a cluster of related changes, with #NNN references>
- <Another cluster>

## <Next theme>

- <Cluster summary>
```

Each list item is a cluster of related activity (not individual items). Write 2-4 sentences
per cluster, with inline PR/issue references.
