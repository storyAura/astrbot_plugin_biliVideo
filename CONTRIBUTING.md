# Contributing

Thanks for your interest in improving biliVideo. This guide describes how the
project is structured and what's expected from a PR.

## Repository layout

```
astrbot_plugin_biliVideo/
├── main.py                # AstrBot entry: command bindings only (~160 lines)
├── metadata.yaml          # AstrBot manifest
├── requirements.txt       # Python deps (Pinned upper-bounds left out by design)
├── _conf_schema.json      # Plugin config schema shown in AstrBot dashboard
├── pyproject.toml         # Lint/type-check/test configuration
├── bilivideo/             # All real logic lives here
│   ├── core/              # constants, types, exceptions, config, logger
│   ├── api/               # Bilibili HTTP client, endpoints, WBI signing
│   ├── auth/              # Cookies, QR login flow
│   ├── parsing/           # URL extractor, message router, trigger sets
│   ├── transcription/     # BCut ASR + pipeline (subtitle→ASR fallback)
│   ├── downloader/        # yt-dlp wrapper
│   ├── llm/               # Provider abstraction + AstrBot/OpenAI impls
│   ├── summarize/         # End-to-end summary orchestrator + post-processing
│   ├── render/            # Markdown→PNG renderer (theme/templates/pagination)
│   ├── messaging/         # Forward-message + chunker + builders
│   ├── subscription/      # Atomic JSON store + manager + scheduler
│   ├── access/            # Cooldown, blacklist, in-flight dedup
│   ├── cache/             # LRU+TTL cache primitive
│   ├── handlers/          # One file per command/event handler
│   ├── tools/             # AI function-call tool registrations
│   └── services.py        # Composition root (BiliVideoServices)
└── tests/                 # PyTest suite (71 tests as of v2.0.0)
```

## Code style

- Many small files, single responsibility per file.
- 200–400 lines typical per module. A module hitting 600+ lines should be
  split before the next feature lands.
- No module-level mutable state. Use class instances or encapsulated caches.
- Type-hint public functions (`from __future__ import annotations` is
  enabled across the codebase).
- Avoid `except Exception:` — prefer concrete exception types from
  `bilivideo.core.exceptions`.

## Running checks

```bash
python -m pytest -q
ruff check .
mypy bilivideo
```

## Adding a new command

1. Create a handler in `bilivideo/handlers/<topic>.py` exposing
   `async def handle_<name>(services, event)`.
2. Re-export it from `bilivideo/handlers/__init__.py`.
3. Bind it in `main.py` via `@filter.command(...)` — the body should be a
   short delegation `async for resp in handler(services, event): yield resp`.
4. If the handler needs a new shared service, wire it into
   `BiliVideoServices.__init__`.
5. Write tests for any non-trivial pure logic in `tests/`.

## Adding a config option

1. Add the entry to `_conf_schema.json` (keep `[section]` prefix in the
   description for UI grouping).
2. Add a typed field to `bilivideo.core.config.PluginConfig`.
3. Map it inside `PluginConfig.from_mapping` with appropriate
   coercion/validation.
4. Reference the typed field via `services.config.<name>` from handlers
   — never read from a raw dict.

## Commit messages

Conventional commits, e.g.

- `feat: add cooldown for /最新视频`
- `fix: handle empty trigger_keywords config`
- `refactor: split JsonStore into separate module`
- `docs: clarify wkhtmltopdf install on Docker`
- `test: cover smart_truncate boundary cases`
