# Contributing

Thank you for your interest in contributing to Shortz.

## Development Setup

```bash
git clone https://github.com/youruser/shortz.git
cd shortz
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

## Code Standards

- **Python 3.11+** — use type hints, f-strings, `pathlib`
- **Docstrings** — every module, class, and public function
- **Logging** — use `core.logging_config.setup_logging()`, never bare `print()`
- **Config** — all env vars via `core.config`, never hardcoded
- **Thread safety** — `QMutex` for shared GUI state, `asyncio.to_thread` for API

## File Structure

| Directory | Contents |
|-----------|----------|
| `core/` | Shared config and logging |
| `api_server.py` | FastAPI endpoints |
| `redis_queue.py` | Queue operations |
| `worker.py` | GPU worker loop |
| `gui.py` | PyQt6 interface |
| `Shortz.py` | Pipeline logic |
| `scripts/` | Utility scripts |
| `docker/` | Dockerfiles |
| `docs/` | Documentation |
| `tests/` | Test suite |

## Pull Request Guidelines

1. **One concern per PR** — keep changes focused
2. **Test locally** — run `python -m py_compile <file>` on all changed files
3. **Document changes** — update docstrings and README if needed
4. **No dead code** — remove unused imports, variables, files

## Commit Messages

Use conventional commits:

```
feat: add batch generation API
fix: worker Redis reconnect on connection drop
docs: update architecture diagram
refactor: centralise config to core/config.py
```

## Reporting Issues

Include:
- Python version and OS
- GPU model and VRAM
- Full error traceback
- Steps to reproduce
