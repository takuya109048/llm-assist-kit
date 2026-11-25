# Python Project Rules

## Manage packages

This project uses pip and the standard-library `venv`. Do not use uv, pip-tools,
poetry, or conda. There is no lockfile.

- Create the environment: `python -m venv .venv`
- Activate it: `source .venv/bin/activate` (Windows: `.venv\Scripts\activate`)
- Install the project and dev tools (editable): `pip install -e ".[dev]"`
- Runtime dependencies live in `[project] dependencies` in `pyproject.toml`
- Dev tools (pytest, ruff, pyrefly) live in `[project.optional-dependencies] dev`
- After changing dependencies in `pyproject.toml`, re-run `pip install -e ".[dev]"`
- `ctx.py` must stay a single file that uses only the standard library: users run
  it on other projects without installing anything. Do not add runtime dependencies.
- Skills live in `skills/<name>/` (`SKILL.md` plus optional scripts), not in the
  target projects. Skill scripts also use only the standard library. In `SKILL.md`,
  write paths as `${SKILL_DIR}/...` and the runner as `python ${CTX} run -- ...`.
- `skills/apply-patch/apply_patch.zip` holds prebuilt codex-rs `apply_patch` binaries.
  Never edit it by hand; rebuild it with `python tools/build_apply_patch.py`
  (needs rustup, git and mingw-w64). Do not commit `.build/` or `skills/apply-patch/.bin/`.

## Run code

Run everything inside the activated `.venv`, or call the tools through
`.venv/bin/` (for example `.venv/bin/pytest`). Do not install packages globally.

- Run a script: `python script.py`
- Run a module: `python -m module_name`
- Run the tool: `python ctx.py --list` (preview) or `python ctx.py --stdout`
- Run a command and copy its result for the LLM: `python ctx.py run -- <command>`
- Register the PowerShell functions (`ctx`, ...) in the user's profiles:
  `python install.py` (`--print` shows the block, `--uninstall` removes it).
  To add a function, add a `PSFunction` to `FUNCTIONS` in `install.py`; it
  must point to a standard-library-only Python script in this kit. Put new
  function scripts in `commands/` (e.g. `commands/addcommit.py`).

## Create new projects

- Always use `pyproject.toml` for metadata (PEP 621). Never create `setup.py`,
  `setup.cfg`, or `requirements.txt`.
- Build backend: setuptools (`setuptools.build_meta`)

## Test code

- Framework: pytest
- Run tests: `pytest`
- Test files go in `tests/` at the project root
- Test file naming: `test_*.py`
- Test function naming: `test_*`
- No `__init__.py` needed in `tests/`
- Regenerate `examples/sample-context.md` and `examples/sample-run-result.md`
  after an intended output change:
  `CTX_UPDATE_EXAMPLE=1 pytest tests/test_example.py`
- Windows-only behavior (the clipboard) is tested on the `windows-latest` CI job;
  keep that job in the matrix

## Configure continuous integration

Use `actions/setup-python` in GitHub Actions, then `pip install -e ".[dev]"`.

## Lint and format code

- Tool: ruff (handles both linting and formatting)
- Lint: `ruff check .`
- Lint and auto-fix: `ruff check --fix .`
- Format: `ruff format .`
- Check formatting: `ruff format --check .`
- Configuration lives in `pyproject.toml` under `[tool.ruff]`

## Check types

- Tool: pyrefly
- Run: `pyrefly check`
- Configuration lives in `pyproject.toml` under `[tool.pyrefly]`

## Follow code style

- Follow ruff's defaults for formatting (88 char line length, double quotes, spaces)
- Import sorting is handled by ruff (`isort` rules enabled via `select = ["I"]`)
- Do not add `# type: ignore` comments without an error code

## Avoid these practices

- Do not use uv (`uv`, `uvx`, `uv.lock`, `uv_build`).
- Do not install packages globally or outside `.venv`.
- Do not create `requirements.txt` for dependency management. Use `pyproject.toml`.
- Do not run `python setup.py` commands.
