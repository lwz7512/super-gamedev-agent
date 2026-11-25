---
title: Engine .gitignore templates can hide whole folders
date: 2026-11-25
game: super-gamedev-agent
engine: any
kind: tool
tags: [git, gitignore, unity]
skills: [devops-engineer]
status: active
---

The studio's Unity rule [Ll]ibrary/ also matched .claude/library/, and bin/ (build output) matched the template's bin/ scripts: neither reached GitHub, and nothing warned. Evidence: the Pages build failed on a missing library README.

Next time: after any push of a new folder, compare 'git ls-files | wc -l' with the files on disk, and add explicit !exceptions rather than loosening the engine rule.
