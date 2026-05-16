# CLAUDE.md — AI-assisted data monitoring investigations

---

## Project Context
<!-- Fill in before starting a project session -->
- **Project type**: [x] Software dev  [ ] Art/exhibition/writing  [ ] Research  [ ] Finance/data
- **Primary language**: [x] English  [ ] Lithuanian  [ ] Mixed
- **Session goal**: first build a replica of data quality monitoring tool which highlights data outliers that needs deeper investigation. Finally develop an AI agent that helps with deeper investigations: connects to the database, runs SQL iteratively, reasons about results, and produces a plain-language summary of the root cause plus verification queries for us to cross-check.

---

## Workflow Orchestration

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- Write a brief spec or outline upfront — reduce ambiguity before acting
- If something goes sideways mid-task: STOP, re-plan, then continue
- Use plan mode for verification steps, not just building

### 2. Subagent Strategy (software projects)
- Use subagents to keep the main context window clean
- Offload research, exploration, and parallel analysis to subagents
- One focused task per subagent

### 3. Self-Improvement Loop (long-running projects only)
- After any correction: update `tasks/lessons.md` with the pattern
- Write rules that prevent the same mistake from recurring
- Review lessons at session start for relevant projects

### 4. Verification Before Done
- Never mark a task complete without demonstrating it works
- Ask: "Would a thoughtful colleague approve this?"
- For code: run tests, check logs, diff against original behaviour
- For writing/content: re-read against the original brief

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- Skip this for simple, obvious fixes — don't over-engineer
- Challenge your own output before presenting it

### 6. Autonomous Problem-Solving
- When given a clear problem: fix it, don't ask for hand-holding
- Point at errors or blockers explicitly; then resolve them
- Zero unnecessary context-switching required from the user

---

## Task Management

1. **Plan First** — write plan to `tasks/todo.md` with checkable items
2. **Verify Plan** — check in before starting implementation on complex tasks
3. **Track Progress** — mark items complete as you go
4. **Explain Changes** — give a high-level summary at each meaningful step
5. **Document Results** — add a review/outcome section to `tasks/todo.md`
6. **Capture Lessons** — update `tasks/lessons.md` after corrections (long projects)

---

## Core Principles

- **Simplicity First** — make every change as simple as possible; impact minimal scope
- **No Laziness** — find root causes; no temporary hacks; aim for senior-level standards
- **Minimal Impact** — changes should only touch what's necessary; don't introduce new risk
- **Honesty** — flag uncertainty rather than guessing; surface trade-offs clearly

---

## Domain-Specific Reminders

### Software / Claude Code
- Read relevant SKILL.md before writing code or creating files
- Prefer editing existing files over creating new ones unless structure demands it
- API keys and secrets: never hardcode; use env vars

### Art / Exhibition / Writing
- Preserve the author's voice when editing text — suggest, don't overwrite
- When merging or synthesising texts, note where source material diverges in tone
- Lithuanian-language content: flag any uncertain terminology rather than guessing

### Finance / Data
- Flag assumptions in calculations explicitly
- Prefer reproducible data pipelines (scripts + exports) over one-off manual steps
- Quarterly manual entry is acceptable for slowly-changing values (e.g. pension funds)

---

## What to Customise Per Project
- Replace the Project Context block above
- Add project-specific constraints or conventions below this line
- Delete sections that don't apply to this project type
