# Agent Rules & Guidelines

## Live Session REPL Verification Rule (CRITICAL / MANDATORY)
- Every completed pass (not necessarily mid-pass), you MUST test using the live session REPL in the test directory `C:\Users\USER\Desktop\Frameworks\PDLt-Test` using dev mode to confirm green.
- Run the REPL with `--dev` or `/dev on` to inspect telemetry, stage transitions, and deliverable correctness.
- This is the most important directive.

## PDL Standard Adherence
- Prompt Pseudocode MUST strictly conform to `PDL-01` through `PDL-08`.
- NO invented field schemas (`TASK:`, `OUTPUT:`, `INCLUDE:`).
- One operation per line (`PDL-02`), capitalized action verbs (`PDL-04`).
- No drafting meta-rules or deferrals in the prompt or plan bodies (`PROMPT-01`, `PDL-08`).
