CLI improvements and UX updates
==============================

Summary of CLI-focused changes (feature/cli-optimization-docs):

- Improved loader/ETA experience: interactive live panel showing elapsed time,
  expected total, and per-phase breakdown during long operations.
- Pre-action confirmation for long-running commands with configurable
  `confirmation_threshold_s` in `data/ui_config.json`.
- Background fetch support (`fetch --bg`) and `bg status` reporting.
- Better CLI UX: boxed outputs, rewritten help text, and clearer command
  ergonomics in `app/cli.py`.
- News ingestion robustness:
  - Added NewsData.io fallback when `NEWSAPI_KEY` looks like a public
    NewsData key (prefix `pub_`) or NewsAPI returns zero results.
  - Masked API keys in logs and simplified params for public NewsData keys
    to avoid 422 responses.
- Parallel summarization per-section to reduce digest latency.
- UI config additions: `show_timers`, `use_fast_model`, `fast_model_name`,
  `summarizer_concurrency`, `confirmation_threshold_s`. Persisted in
  `data/ui_config.json` and surfaced via `config show` / `config set`.

Files touched
------------

- `app/cli.py` — loader UI, confirmation flow, background fetch
- `app/ingestion.py` — NewsData fallback, logging improvements
- `app/service.py` — parallel summarization
- `app/ui_config.py` — stricter load/save behavior (ignore unknown keys)

How to try locally
-------------------

1. Create and activate your venv (PowerShell):

```powershell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
```

2. Install dev/runtime deps and run the CLI:

```powershell
pip install -r requirements.txt
pip install -r requirements-dev.txt
python -m app.cli
```

3. Example commands to exercise features:

- `fetch --bg --limit 50` (run fetch in background)
- `fetch` (interactive loader + ETA)
- `digest` (summarize the latest snapshot)
- `config set confirmation_threshold_s 5` then run a long action to see the
  pre-confirm prompt.

Notes and follow-ups
--------------------

- CI workflow will run tests and ensure these changes stay green.
- Consider expanding tests to cover background fetch and ingestion fallbacks.
