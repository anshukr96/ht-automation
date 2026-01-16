# Repository Guidelines

## Project Structure & Module Organization

- `src/` contains application logic (pipelines, integrations, and automation steps).
- `tests/` holds unit and integration tests mirroring `src/` paths (e.g., `tests/pipelines/`).
- `assets/` stores static resources used by automation runs (templates, prompts, sample inputs).
- `scripts/` contains developer utilities (e.g., `scripts/dev`, `scripts/test`).
- `docs/` is for architecture notes and runbooks.

If you add a new module, create it under `src/` and add a matching test file under `tests/`.

## Build, Test, and Development Commands

This repository is currently a scaffold. As you introduce tooling, wire these commands (or equivalents) and keep them documented:

- `npm run dev` to start local development.
- `npm run build` to produce production artifacts.
- `npm test` to run the full test suite.
- `npm run lint` to run static checks.

If you use a different runtime (Python, Go), add analogous commands in this section.

## Coding Style & Naming Conventions

- Use 2-space indentation for JS/TS or 4 spaces for Python; be consistent across the repo.
- Name files and folders in `kebab-case` (e.g., `content-scheduler.ts`).
- Keep modules single-purpose: one pipeline or integration per file when practical.
- Prefer explicit, descriptive names for steps and adapters (e.g., `sanitize-input`, `publish-to-cms`).

If you add a formatter or linter (Prettier, ESLint, Ruff), document the config and run commands.

## Testing Guidelines

- Place tests next to the structure they cover (e.g., `src/pipelines/` -> `tests/pipelines/`).
- Name tests with `*.test.*` or `*_test.*` depending on the language.
- Aim for coverage on critical automation logic (parsing, scheduling, publishing, retries).

## Commit & Pull Request Guidelines

- No historical convention yet; use Conventional Commits (`feat:`, `fix:`, `chore:`) going forward.
- PRs should describe what changed, why it changed, and any new dependencies or config updates.
- Include screenshots or logs when changes affect content output or scheduling behavior.

## Configuration & Secrets

- Keep secrets out of the repo; use `.env` files or your secrets manager.
- Document required environment variables in `docs/configuration.md`.
