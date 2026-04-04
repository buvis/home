---
name: skill-creator
description: Guide for creating effective Claude Code skills. Use when users want to create a new skill, edit an existing skill, or verify a skill works before deployment. Triggers on "create skill", "new skill", "build skill", "edit skill", "skill template".
---

# Skill Creator

Create effective skills that extend Claude Code with specialized knowledge, workflows, and tools.

## About Skills

Skills are modular packages that give Claude Code procedural knowledge it cannot derive from the codebase alone. A skill is a directory with a required `SKILL.md` and optional supporting files.

Skills follow the [Agent Skills](https://agentskills.io) open standard. They work across Claude Code, Claude.ai, and other adopting tools.

### What Skills Provide

1. **Specialized workflows** - multi-step procedures for specific domains
2. **Tool integrations** - instructions for working with specific file formats or APIs
3. **Domain expertise** - company-specific knowledge, schemas, business logic
4. **Bundled resources** - scripts, references, and assets for complex and repetitive tasks

## Core Principles

### Concise Is Key

The context window is a shared resource. Skills share it with the system prompt, conversation history, other skills' metadata, and the user's request.

**Default assumption: Claude is already very smart.** Only include knowledge Claude does not already have. Challenge each piece of information: "Does Claude really need this?" and "Does this paragraph justify its token cost?"

Prefer concise examples over verbose explanations.

### Set Appropriate Degrees of Freedom

Match specificity to fragility and variability:

**High freedom (text instructions)**: Multiple approaches are valid, decisions depend on context.

**Medium freedom (pseudocode or parameterized scripts)**: A preferred pattern exists but some variation is acceptable.

**Low freedom (specific scripts, few parameters)**: Operations are fragile, consistency is critical, or a specific sequence must be followed.

Think of it as path width: a narrow bridge with cliffs needs guardrails (low freedom), while an open field allows many routes (high freedom).

### Anatomy of a Skill

```
skill-name/
├── SKILL.md           (required - frontmatter + instructions)
├── scripts/           (optional - executable code)
├── references/        (optional - docs loaded into context as needed)
└── assets/            (optional - files used in output, not loaded into context)
```

#### SKILL.md (required)

- **Frontmatter** (YAML between `---` markers): `name` and `description` control when the skill triggers. The description is the primary trigger mechanism - Claude reads it to decide relevance. All "when to use" information belongs here, not in the body.
- **Body** (Markdown): Instructions loaded only AFTER the skill triggers.

See [references/frontmatter.md](references/frontmatter.md) for the complete field reference.

#### scripts/

Executable code for tasks requiring deterministic reliability or that would otherwise be rewritten repeatedly.

- Scripts can be executed without loading into context (token-efficient)
- Claude may still read scripts for patching or environment-specific adjustments
- Always test scripts by running them before shipping

#### references/

Documentation loaded into context on demand to inform Claude's process.

- Database schemas, API docs, domain knowledge, company policies
- Keeps SKILL.md lean while making information discoverable
- For large files (>10k words), include grep search patterns in SKILL.md
- Information should live in either SKILL.md or references, not both

#### assets/

Files used in output, not loaded into context.

- Templates, boilerplate code, images, icons, fonts
- Claude copies or modifies these files as part of the output
- Example: `assets/hello-world/` for a frontend boilerplate project

#### What NOT to Include

- README.md, INSTALLATION_GUIDE.md, CHANGELOG.md, or other auxiliary docs
- Setup and testing procedures
- User-facing documentation about the skill itself

A skill contains only what Claude needs to do the job.

### Progressive Disclosure

Skills use a three-level loading system:

1. **Metadata** (name + description) - always in context (~250 chars max)
2. **SKILL.md body** - when skill triggers (<500 lines recommended)
3. **Bundled resources** - as needed (unlimited; scripts can run without context loading)

Keep SKILL.md under 500 lines. Split content into separate files when approaching this limit. When splitting, reference files from SKILL.md and describe clearly when to read them.

See [references/patterns.md](references/patterns.md) for progressive disclosure patterns.

## Skill Creation Process

1. Understand the skill with concrete examples
2. Plan reusable resources (scripts, references, assets)
3. Initialize the skill directory
4. Edit the skill (implement resources and write SKILL.md)
5. Validate the skill
6. Iterate based on real usage

### Naming

- Lowercase letters, digits, and hyphens only; max 64 characters
- Prefer short, verb-led phrases that describe the action
- Namespace by tool when it improves clarity (e.g., `gh-address-comments`)
- Directory name must match the skill name

### Step 1: Understand the Skill

Skip only when usage patterns are already clearly understood.

Gather concrete examples of how the skill will be used:

- "What should this skill support?"
- "Can you give examples of how it would be used?"
- "What would a user say that should trigger this?"

Ask the most important questions first. Avoid overwhelming the user. Conclude when there is a clear sense of the skill's scope.

### Step 2: Plan Reusable Resources

For each concrete example, consider:

1. How would you execute this from scratch?
2. What scripts, references, or assets would help when doing this repeatedly?

Examples:
- **PDF rotation**: same code each time -> `scripts/rotate_pdf.py`
- **Frontend webapp**: same boilerplate each time -> `assets/hello-world/`
- **BigQuery queries**: rediscovering schemas each time -> `references/schema.md`

### Step 3: Initialize the Skill

Run the init script to generate a template:

```bash
~/.claude/skills/skill-creator/scripts/init_skill.py <skill-name> --path <output-directory> [--resources scripts,references,assets]
```

Examples:

```bash
~/.claude/skills/skill-creator/scripts/init_skill.py my-skill --path ~/.claude/skills
~/.claude/skills/skill-creator/scripts/init_skill.py my-skill --path .claude/skills --resources scripts,references
```

Skip this step if the skill already exists and you are iterating.

### Step 4: Edit the Skill

The skill is being created for another instance of Claude to use. Include information that is beneficial and non-obvious. Think: what procedural knowledge, domain-specific details, or reusable assets would help Claude execute these tasks?

#### Start with Resources

Implement `scripts/`, `references/`, and `assets/` files first. This may require user input (e.g., brand assets, API docs). Test scripts by running them.

#### Write SKILL.md

**Frontmatter:**
- `name`: the skill name (lowercase, hyphens, max 64 chars)
- `description`: the primary trigger mechanism. Keep under 250 characters (truncated beyond that). All "when to use" info goes here - the body is only loaded after triggering.

See [references/frontmatter.md](references/frontmatter.md) for additional frontmatter fields (invocation control, subagent execution, tool permissions, etc.).

**Writing effective descriptions:**

Descriptions must describe triggering conditions, not summarize the skill's workflow. When a description summarizes workflow, Claude may follow the description as a shortcut instead of reading the full skill body.

```yaml
# BAD: summarizes workflow - Claude may follow this instead of reading skill
description: Deploy to staging by running tests, building docker image, and pushing to k8s

# GOOD: trigger conditions only
description: Use when deploying to staging. Triggers on "deploy staging", "push to staging".
```

- Start with "Use when..." to focus on triggers
- Include specific symptoms, scenarios, and file types
- Write in third person (injected into system prompt)
- Use keywords Claude would search for (error messages, tool names, symptoms)

**Body:** Use imperative/infinitive form. Structure by workflow, task, reference, or capabilities - whichever fits the skill's purpose.

**Token efficiency:**
- Frequently-loaded skills: aim for <200 words total
- Other skills: <500 words in SKILL.md body
- Move heavy reference to separate files
- Don't repeat what's in cross-referenced skills
- Reference other skills by name, not `@` paths (`@` force-loads files, burning context)

### Step 5: Validate the Skill

Run the validator to check structure and frontmatter:

```bash
~/.claude/skills/skill-creator/scripts/validate_skill.py <path/to/skill-folder>
```

Fix any reported errors and re-run.

### Step 6: Iterate

1. Use the skill on real tasks
2. Notice struggles or inefficiencies
3. Update SKILL.md or bundled resources
4. Test again

## Platform Details

See [references/platform.md](references/platform.md) for:
- Skill placement hierarchy (personal, project, enterprise, plugin)
- String substitutions (`$ARGUMENTS`, `${CLAUDE_SKILL_DIR}`, etc.)
- Dynamic context injection with shell commands
- Invocation control matrix
- Relationship to legacy `.claude/commands/` files
