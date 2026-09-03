# APS Project Briefing Analysis

Use only the supplied ProjectContext material and briefing date.

- Return at most three concrete tasks that can be acted on for the briefing date.
- Each task must combine the action and its completion condition in one sentence.
- Return at most two notes, limited to blockers or decisions explicitly present in the context.
- Do not inspect or infer external repositories, branches, commits, worktrees or implementation state.
- Do not propose unrelated personal schedules.
- Do not create files or request filesystem paths.
- Return empty arrays when the supplied material contains no applicable task or note.
