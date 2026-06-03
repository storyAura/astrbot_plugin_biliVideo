# Changelog

All notable changes to this plugin are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## v2.0.0 — Architecture refresh

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
