# Current Affairs Backend

Local FastAPI backend for India-first current affairs digest generation using NewsAPI + RSS + Ollama.

You can run this project in two modes:

- API mode with uvicorn
- Terminal chatbot mode (Claude-code-style workflow without uvicorn)

## Features (Phase 1)

- Fetches headlines from NewsAPI and RSS feeds
- Normalizes and deduplicates overlapping headlines
- Ranks and groups stories into India and World buckets
- Generates concise English-only digest using local Ollama model
- Stores raw snapshots and digest outputs in local JSON files
- Includes lightweight benchmark helper for model comparison

## Quick Start

1. Create and activate a Python virtual environment.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy environment template:

   ```bash
   copy .env.example .env
   ```

4. Optionally set `NEWSAPI_KEY` in `.env`.
5. Start API (optional):

   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

6. Start terminal chatbot mode (recommended for on-demand usage):

   ```powershell
   .\run_cli.ps1
   ```

   or directly:

   ```powershell
   .\.venv\bin\python.exe -m app.cli
   ```

## Terminal Chatbot Commands

- `news today` : fetch and summarize latest headlines now
- `agenda` : summarize latest stored snapshot
- `fetch --rss-only --limit 20` : fetch without NewsAPI
- `digest --snapshot <id> --model qwen3.5:9b --bullets 12`
- `pipeline --rss-only --limit 20` : fetch + digest in one command
- `benchmark --snapshot <id> --models "qwen3.5:9b,mistral:7b-instruct"`
- `graph --snapshot <id> --top 36 --min-sim 0.44` : build relationship graph files
- `metrics --snapshot <id> --limit 50` : show slowest pipeline phases by timing
- `route-test --prompts "p1|p2|p3"` : run specialist routing harness
- `logo` : print FRIDAY logo path
- `model <name>` : set session model
- `config show` : display current UI personalization values
- `config set name friday` : change prompt name
- `config set accent bright_blue` : change prompt accent color
- `config set panel blue` : change dashboard border color
- `config set tips false` : hide startup tips panel
- `help`
- `exit`

## Claude-Code-Like UI Notes

- Startup dashboard and prompt styling are rendered with Rich.
- Personalization persists in `data/ui_config.json`.
- You can rename the assistant prompt and theme colors without editing code.

## FRIDAY Logo

- Custom logo asset: `assets/friday_logo.svg`
- Contains a big FRIDAY center text with a circular HUD-style icon layout.

## News Graph Visualization

- Command: `graph --snapshot <id> --top 36 --min-sim 0.44`
- If `--snapshot` is omitted, latest snapshot is used.
- Export Mermaid graph file: `data/graphs/<snapshot_id>.mmd`
- Export metadata JSON file: `data/graphs/<snapshot_id>.json`
- Related stories are connected by title similarity, helping you visualize clusters of the same event.

## API Endpoints

- `GET /health`
- `POST /fetch-news`
- `POST /generate-digest`
- `POST /run-pipeline`
- `POST /benchmark-models`

## Example Requests

Fetch news:

```bash
curl -X POST http://127.0.0.1:8000/fetch-news -H "Content-Type: application/json" -d "{\"limit_per_source\": 20, \"include_newsapi\": true}"
```

Generate digest from latest snapshot:

```bash
curl -X POST http://127.0.0.1:8000/generate-digest -H "Content-Type: application/json" -d "{\"max_bullets\": 12}"
```

## Model Benchmark (utility)

You can call `run_model_benchmark(snapshot_id, models)` from `app.benchmark` in a Python shell/script after creating a snapshot.

API example:

```bash
curl -X POST http://127.0.0.1:8000/benchmark-models -H "Content-Type: application/json" -d "{\"snapshot_id\": \"20260420T120000Z\", \"models\": [\"qwen3.5:9b\", \"qwen2.5:7b-instruct\", \"mistral:7b-instruct\"]}"
```

## Data Layout

- `data/friday.db` primary SQLite database for snapshots, digests, and phase metrics
- `data/benchmarks/*.json` model benchmark reports
- `data/graphs/*.mmd` and `data/graphs/*.json` graph exports
- `data/routing/*.json` routing harness outputs

## Observability and Bottleneck Tracking

- Every major phase logs duration metrics (fetch, ranking, summarize, persist, pipeline total).
- CLI command: `metrics --limit 50` to see which phases consume the most time.
- API endpoint: `GET /metrics/summary?snapshot_id=<id>&limit=50`

## Specialist Routing Harness

- Run: `route-test`
- Optional custom prompts: `route-test --prompts "fix hooks|review PR risk|tune graph threshold"`
- Output log saved to `data/routing/routing_harness_<timestamp>.json`

## Notes

- Dockerization is intentionally deferred to the final stage.
- If `NEWSAPI_KEY` is not set, RSS ingestion still works.
