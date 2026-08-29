# Changelog

All notable changes to this plugin are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## v2.1.0 (2026-08-29) — Markdown/LaTeX 渲染与结构化时间戳

> Feature release from
> [#27](https://github.com/storyAura/astrbot_plugin_biliVideo/pull/27)
> (thanks [@Eco404](https://github.com/Eco404)). No config changes required;
> fully backward-compatible. Docker / 无 `wkhtmltoimage` 环境也能出图；开启
> 时间戳时优先走结构化工具调用，失败再回退 Markdown。

### Added

- Restored the original `wkhtmltoimage` HTML/CSS renderer as the preferred
  backend whenever its executable is available on `PATH`.
- Server-side LaTeX rendering on the wkhtml backend: inline and display
  formulas become embedded MathText PNGs, with no JavaScript, network
  resource, or TeX installation required. Malformed formulas keep the
  original source text.
- An all-Python fallback for hosts without `wkhtmltoimage`:
  `markdown-it-py` parses CommonMark, Matplotlib MathText renders common TeX,
  and Pillow composes the cards. Emphasis, inline code, links, nested lists,
  blockquotes, tables, inline math, and display math are preserved.
- When timestamps are enabled, AstrBot providers request one required,
  schema-constrained summary tool call. Chapter timestamps are validated for
  type, range, and order before renderer-safe Markdown is generated.
  Providers without tool support and invalid tool responses fall back to the
  legacy Markdown prompt; custom `openai_compatible` providers stay on that
  path and never receive tool arguments.
- New Python dependencies: `markdown-it-py`, `mdit-py-plugins`, `matplotlib`.

### Changed

- Summary-style instructions no longer conflict with a global request to
  preserve as much detail as possible. Concise output is limited to at most
  eight single-point chapters, professional output to twelve analytical
  chapters, and detailed output to twenty chapters. These targets are shared
  by the prompt and AstrBot tool schema; `max_note_length` remains the only
  final character limit.
- Structured-output validation treats style chapter-count overruns, missing
  AI summaries, and nested h1/h2 headings as recoverable. It accepts usable
  chapters, demotes nested headings to h3, and only keeps a 64-chapter safety
  limit plus checks that protect timestamp correctness and renderability.
- The structured request and a subsequent Markdown fallback each receive a
  fresh LLM timeout. `processing_timeout` remains the overall limit for the
  complete download, transcription, and summary job.
- Timestamp parsing accepts `m:ss`, `mm:ss`, and `h:mm:ss`. Summary cache
  keys include the output format, provider/model, and timestamp-related
  options so stale no-timestamp summaries are not reused after configuration
  changes.

### Fixed

- Double-escaped line endings in structured `body_markdown` and `ai_summary`
  are normalized at Markdown boundaries, while LaTeX commands such as
  `\\nu` and `\\nabla` remain untouched.
- The timestamp pill's unsupported stopwatch character is replaced with a
  font-safe time label. A timestamp emitted as a paragraph directly after a
  chapter heading is merged into that heading instead of being discarded.

## v2.0.1 (2026-07-11) — Concurrency & robustness fixes

> Bug-fix release: no new commands or config keys; fully backward-compatible.

### Added

- QQ mini-app card links inside quoted messages are now parsed by `/总结`:
  the message chain is walked recursively (Reply → Json segments) and the
  card's `qqdocurl` is extracted directly
  ([#24](https://github.com/storyAura/astrbot_plugin_biliVideo/pull/24),
  thanks [@pheasantgogogo](https://github.com/pheasantgogogo)).

### Fixed

- A new video can no longer be pushed twice when a manual `/检查更新` runs
  concurrently with the scheduled push loop: both paths share a
  per-`(origin, mid)` lock (`KeyedLocks`) and re-read `last_bvid` under it
  before deciding to push. The manual check claims the video inside the
  lock and runs the slow summary generation outside it, so it never stalls
  the scheduled loop and never yields while holding the lock.
- `JsonStore` persistence failures are no longer swallowed: a failed write
  rolls back the in-memory state and propagates, subscription/push-target
  commands report the failure to the user, and the blocking
  write+`fsync`+rename runs in a worker thread instead of on the event loop.
  Writes orphaned by task cancellation are sequence-guarded so they can
  never clobber a newer write, and `shutdown()` closes the store so a stale
  hot-reloaded instance can't dump its old snapshot over fresh data.
- Rendering no longer blocks the event loop: `render_note_components` is
  async and offloads image work via `asyncio.to_thread`.
- Waiter cancellation no longer poisons shared futures in
  `InflightDeduper`/`LRUTTLCache` (waiters use `asyncio.shield`; keys are
  always cleaned up).
- Access control matches whole origin segments (group `10000` no longer
  matches `910000`); `添加推送群`/`添加推送号`/`移除推送` are admin-only.
- The transcription pipeline cleans up audio/subtitle files on every
  failure path; downloads and BCut uploads honour cooperative cancellation
  after timeout.

### Changed

- The 15 inline `is_allowed` permission checks collapsed into a
  `@require_access` decorator; dead `CooldownError`/`AccessDeniedError`
  exceptions removed.
- Forward-message `Nodes` building is unified in `messaging/forward.py`
  (`build_video_forward_nodes` gained `header=`, new
  `build_multi_video_forward_nodes`); the scheduled push and the AI search
  tool no longer hand-roll node lists.
- Config defaults are single-sourced from the dataclass field defaults;
  the plugin version is single-sourced from `metadata.yaml`
  (`__version__` parses it, `/总结状态` displays it, `pyproject.toml` uses
  a dynamic version, and `MANIFEST.in` ships the yaml in sdists).
- WBI signing reuses the shared HTTP connection pool
  (`sign_params(params, client=client)`) instead of creating a throwaway
  session per nav fetch, gaining the client's retry logic.

## v2.0.0 (2026-06-03) — Architecture refresh

> Major refactor. **Backward-compatible** for end users (commands and
> config keys preserved) but a complete restructure under the hood.

### Added

- New layered package `bilivideo/` with clear single-responsibility modules:
  `core`, `api`, `auth`, `parsing`, `transcription`, `downloader`, `llm`,
  `summarize`, `render`, `messaging`, `subscription`, `access`, `cache`,
  `handlers`, `tools`.
- Typed configuration via `PluginConfig` dataclass with validation,
  enum-restriction and clamping (no more `dict.get()` everywhere).
- Structured exception hierarchy (`BiliVideoError`, `NetworkError`,
  `TranscriptionError`, `LLMError`, …) — user-friendly messages now ride
  on the exception itself instead of substring-matching.
- LRU + TTL + single-flight cache (`LRUTTLCache`) shared by the WBI key
  fetcher and `get_video_info`.
- Shared `aiohttp.ClientSession` plus exponential-backoff retries for
  every B 站 API call.
- Per-user cooldown tracker for `/总结` (default 8 s, configurable).
- In-flight deduplication (`InflightDeduper`) to fold concurrent requests
  for the same BV into a single underlying job.
- Atomic `JsonStore` (tempfile + `os.replace` + `fsync`) for the
  subscription/push-target file — no more half-written JSON on crash.
- Full PyTest suite with 71 tests covering URL extraction, pagination,
  smart truncation, message parsing, subscription persistence, cooldown,
  LRU cache, in-flight deduplication, access control, and config.
- `pyproject.toml` with Ruff + MyPy + PyTest configuration.
- `user_cooldown_seconds`, `llm_temperature`, `image_width`,
  `forward_bot_name`, `forward_bot_uin`, and `trigger_keywords` config
  options.

### Changed

- `main.py` shrunk from ~2,000 lines to ~160 lines; it now only registers
  AstrBot commands and forwards them to handlers.
- `metadata.yaml` repo URL fixed (it previously concatenated a stray
  `yt-dlp` token, breaking the link).
- `requirements.txt` now lists `segno` (was implicitly required by the
  QR-login flow but missing from the manifest).
- `_conf_schema.json` reorganised with per-section `[xxx]` description
  prefixes for UI grouping; values now validated/clamped on load.
- Cookie storage hardened: atomic writes + `chmod 0600` on creation.
- Auto-detect (`on_all_message`) is now a small composition of typed
  helpers (`MessageContext`, `TriggerSet`, URL extractor) instead of
  ~300 lines of nested branches.
- WBI signing is single-flight: concurrent requests share one fetch.
- Scheduler iterations include jitter so multi-instance deployments don't
  thunder simultaneously.

### Fixed

- `audio_meta.file_path` access on the subtitle-only path no longer
  raises `AttributeError`.
- Short-link resolution now uses async aiohttp throughout (was blocking
  the event loop with `requests.head`).
- `get_uploader_info` failures now fall back gracefully through video
  lookup → search result → UID-based placeholder, mirroring the original
  intent without the duplicate code.
- Quote/reply detection: trigger keywords are configurable; the hard
  intercept for `[CQ:reply` and `[引用消息]` is preserved.
- `metadata.yaml` `name` is now lowercase `astrbot_plugin_bilivideo`
  (was camelCase `astrbot_plugin_biliVideo`). This unblocks installation
  on case-insensitive filesystems (Windows/macOS APFS) where the
  AstrBot extractor would otherwise hit "directory already exists" —
  closes [#14][issue14].

[issue14]: https://github.com/storyAura/astrbot_plugin_biliVideo/issues/14

### Security

- `bili_cookies.json` is created with mode `0600` (was 0644) so SESSDATA
  isn't world-readable on shared servers.
- Cookie loading no longer surfaces SESSDATA values in debug logs.
- Reduced surface for prompt-injection: search results pass through a
  typed dataclass before reaching the LLM, with `<em>` highlighting
  stripped server-side.

### Removed

- Module-level mutable globals (`_wbi_cache`, `_font_face_cache`)
  replaced by encapsulated caches.
- Legacy `services/`, `downloaders/`, `transcriber/`, `utils/`, `gpt/`,
  `models/` directories — their contents now live in the new
  `bilivideo/` package.

---

## v1.0.5a (2026-05-14)

- Optional summary on auto-push (`auto_push_summary`).
- Hard-intercept quoted/reply messages from re-triggering auto detection.

## v1.0.4b (2026-05-14)

- Fix `audio_meta.file_path` crash on subtitle-only path.
- Harden cleanup function to skip `None`/empty paths.

## v1.0.4 (2026-05-13)

- Fix `extract_video_id` UnboundLocalError for BCut transcript flow.
- Fix unterminated subpattern regex on `b23.tv` resolution.

## v1.0.3 (2026-05-12)

- Quote-message false-trigger fix; trigger keyword mechanism.
- Forward-message mode; long-summary pagination.
- Prefer subtitles config option.

## v1.0.2 (2026-03-01)

- AstrBot v4.17.2 compatibility, mini-app link recognition,
  `/识别开关` toggle command.

## v1.0.1

- First release.
