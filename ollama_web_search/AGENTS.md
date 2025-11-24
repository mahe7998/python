# Repository Guidelines

## Project Structure & Module Organization
- `main.py` is the entry point; it wires the Ollama client to the browser tools and drives the chat loop.
- `web_search_gpt_oss_helper.py` holds the browser, page state, and formatting utilities—mirror its patterns when extending browsing features.
- `README.md` documents architecture and setup; keep it aligned with changes to the run loop or environment requirements.
- Create new modules under the repo root or a `tests/` package as the project grows; keep web-search adapters close to the browser helper for clarity.

## Build, Test, and Development Commands
- `uv sync` installs the locked dependency set from `uv.lock`.
- `uv run main.py` launches the interactive agent with web search enabled.
- `uv run python -m pytest` executes the automated test suite (add tests first).
- `uv tree` inspects the resolved dependency graph when you need to audit transitive packages.

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indentation, `snake_case` for functions, and `PascalCase` for classes; keep names descriptive of browser intent (e.g., `browser_find`).
- Type hints are encouraged for new functions to mirror the existing dataclass usage and ease tool integration.
- Keep side-effectful utilities (network or IO) in dedicated helpers so pure functions remain easy to test.

## Testing Guidelines
- Use `pytest` and place files under `tests/` with the pattern `test_<module>.py`.
- Mock Ollama responses and network calls to avoid quota usage; reserve live-search checks for opt-in integration tests marked `@pytest.mark.integration`.
- Aim for coverage of parsing utilities and state transitions in `BrowserStateData` so browsing regressions surface early.

## Commit & Pull Request Guidelines
- Match the existing history: concise, imperative subject lines ("Add", "Update", "Fix") under 72 characters, optionally with a scoped prefix.
- Reference related issues in the body, list manual test commands, and call out any changes that affect environment variables or external services.
- PRs should summarize behavior changes, note impacts on Ollama query quotas, and include screenshots or logs when UI or output formatting shifts.

## Security & Configuration Tips
- Export `OLLAMA_API_KEY` locally (e.g., `export OLLAMA_API_KEY=...`) and never commit secrets; prefer `.env` entries in your shell profile, not version control.
- Document any new configuration knobs in `README.md` and guard against accidental logging of API keys during verbose debug output.
