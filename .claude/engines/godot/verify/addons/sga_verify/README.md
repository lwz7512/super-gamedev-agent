# sga_verify — run-and-verify harness

Installed by `bash .claude/scripts/godot-verify.sh install`. Do not add it as an
autoload yourself: `godot-verify.sh` adds it for each run through a temporary
`override.cfg`, and without `-- --sga-scenario=…` on the command line it does
nothing.

- `verify.gd` plays a scenario: input at exact frames, expression checks on
  live nodes, screenshots with baseline comparison, a filmstrip and a trace.
- `error_logger.gd` collects engine and script errors (Godot 4.5+ `Logger`).

Scenario format and workflow: `.claude/docs/godot-verify.md` in the studio repo.
Keep it out of exported builds with the export filter `addons/sga_verify/*`.
