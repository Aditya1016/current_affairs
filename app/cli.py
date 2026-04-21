import shlex
from typing import List

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .benchmark import run_model_benchmark
from .config import settings
from .graph_view import build_relationship_graph
from .route_harness import run_route_harness
from .schemas import DigestRequest, FetchRequest
from .service import (
    fetch_news_service,
    format_digest_text,
    generate_digest_service,
    get_metrics_summary_service,
    run_pipeline_service,
)
from .ui_config import load_ui_config, save_ui_config


HELP_TEXT = """
Commands:
  help                              Show this help
  fetch [--rss-only] [--limit N]    Fetch headlines and save snapshot
  digest [--snapshot ID] [--model M] [--bullets N]
                                    Generate digest from snapshot or latest
  news today                        Shortcut: fetch + digest
  agenda                            Shortcut: digest from latest snapshot
  pipeline [--rss-only] [--limit N] Run fetch + digest in one step
  benchmark --snapshot ID [--models "m1,m2"] [--bullets N]
                                    Run model comparison
    graph [--snapshot ID] [--top N] [--min-sim F] [--no-adaptive]
                                                                        Build related-news graph (Mermaid + JSON)
    metrics [--snapshot ID] [--limit N]
                                                                        Show phase timing summary (slowest first)
    route-test [--prompts "p1|p2|..."]
                                                                        Run keyword routing harness and log output
    logo                              Show FRIDAY logo file location
  model [MODEL_NAME]                Show or set default model for this session
  config show                       Show UI config
  config set name VALUE             Set assistant prompt name
  config set accent VALUE           Set prompt accent color (e.g. bright_cyan)
  config set panel VALUE            Set dashboard panel color
  config set tips true|false        Toggle tips panel visibility
  exit                              Quit
""".strip()


console = Console()


def _render_banner(ui: dict) -> None:
    panel_color = str(ui.get("panel_color", "cyan"))
    name = str(ui.get("assistant_name", "friday"))
    tips = bool(ui.get("show_tips", True))

    left = Table.grid(expand=True)
    left.add_row(f"[bold {panel_color}]Welcome back![/]")
    left.add_row("")
    left.add_row(f"[bold]{name.title()} CLI[/]")
    left.add_row("Local current-affairs assistant")

    if tips:
        right = Table.grid(expand=True)
        right.add_row(f"[bold {panel_color}]Tips[/]")
        right.add_row("Run [bold]news today[/] for fresh headlines")
        right.add_row("Run [bold]agenda[/] for latest snapshot digest")
        right.add_row("Run [bold]config show[/] for UI customization")

        outer = Table.grid(expand=True)
        outer.add_column(ratio=1)
        outer.add_column(ratio=2)
        outer.add_row(left, right)
        console.print(Panel(outer, border_style=panel_color))
    else:
        console.print(Panel(left, border_style=panel_color))


def _handle_config_command(raw: str, ui: dict) -> bool:
    parts = shlex.split(raw)
    if len(parts) < 2:
        console.print("Usage: config show | config set <name|accent|panel|tips> <value>")
        return True

    if parts[1] == "show":
        table = Table(title="UI Config")
        table.add_column("Key")
        table.add_column("Value")
        for k, v in ui.items():
            table.add_row(str(k), str(v))
        console.print(table)
        return True

    if parts[1] == "set" and len(parts) >= 4:
        key = parts[2].lower()
        value = " ".join(parts[3:]).strip()
        if key == "name":
            ui["assistant_name"] = value or "friday"
        elif key == "accent":
            ui["accent_color"] = value or "bright_cyan"
        elif key == "panel":
            ui["panel_color"] = value or "cyan"
        elif key == "tips":
            ui["show_tips"] = value.lower() in {"1", "true", "yes", "on"}
        else:
            console.print("Unknown config key. Use: name, accent, panel, tips")
            return True

        save_ui_config(ui)
        console.print("UI config updated.")
        return True

    console.print("Usage: config show | config set <name|accent|panel|tips> <value>")
    return True


def _parse_arg(args: List[str], name: str, default: str = "") -> str:
    if name in args:
        idx = args.index(name)
        if idx + 1 < len(args):
            return args[idx + 1]
    return default


def _parse_int_arg(args: List[str], name: str, default: int) -> int:
    raw = _parse_arg(args, name, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def _print_digest(snapshot_id: str = "", model: str = "", max_bullets: int = 12) -> None:
    request = DigestRequest(
        snapshot_id=snapshot_id or None,
        model=model or None,
        max_bullets=max_bullets,
    )
    response = generate_digest_service(request)
    console.print(format_digest_text(response))


def _render_graph_summary(result: dict) -> None:
    table = Table(title="News Relationship Graph")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Snapshot", str(result.get("snapshot_id", "")))
    table.add_row("Nodes", str(result.get("node_count", 0)))
    table.add_row("Edges", str(result.get("edge_count", 0)))
    table.add_row("Clusters", str(result.get("cluster_count", 0)))
    table.add_row("Requested min-sim", str(result.get("min_similarity", "")))
    table.add_row("Used min-sim", str(result.get("used_similarity", "")))
    table.add_row("Adaptive", str(result.get("adaptive", False)))
    table.add_row("Mermaid file", str(result.get("mermaid_file", "")))
    table.add_row("JSON file", str(result.get("json_file", "")))
    console.print(table)

    clusters = result.get("clusters", [])[:5]
    if not clusters:
        console.print("No strong clusters found. Lower --min-sim to increase connections.")
        return

    node_map = {n["node_id"]: n for n in result.get("nodes", [])}
    console.print("Top clusters:")
    for idx, cluster in enumerate(clusters, start=1):
        preview_titles = []
        for node_id in cluster[:3]:
            row = node_map.get(node_id)
            if row:
                preview_titles.append(row["title"])
        console.print(f"{idx}. size={len(cluster)} :: " + " | ".join(preview_titles))


def _render_metrics_summary(result: dict) -> None:
    table = Table(title="Pipeline Phase Timing Summary")
    table.add_column("Phase")
    table.add_column("Samples", justify="right")
    table.add_column("Avg ms", justify="right")
    table.add_column("Max ms", justify="right")
    table.add_column("Total ms", justify="right")

    for row in result.get("phases", []):
        table.add_row(
            str(row.get("phase", "")),
            str(row.get("samples", 0)),
            str(row.get("avg_ms", 0)),
            str(row.get("max_ms", 0)),
            str(row.get("total_ms", 0)),
        )

    if not result.get("phases"):
        console.print("No metrics yet. Run fetch/digest/pipeline first.")
        return

    console.print(table)


def run_cli() -> None:
    ui = load_ui_config()
    _render_banner(ui)
    console.print("Type 'help' for commands. Type 'exit' to quit.")
    session_model = ""

    while True:
        try:
            accent = str(ui.get("accent_color", "bright_cyan"))
            assistant_name = str(ui.get("assistant_name", "friday"))
            raw = console.input(f"\n[bold {accent}]{assistant_name}>[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nExiting.")
            break

        if not raw:
            continue

        lower = raw.lower()
        if lower in {"exit", "quit"}:
            console.print("Goodbye.")
            break

        if lower == "help":
            console.print(HELP_TEXT)
            continue

        if lower.startswith("config"):
            _handle_config_command(raw, ui)
            continue

        if lower in {"hi", "hello", "hey", "yo"}:
            console.print("Hi. Try: news today, agenda, fetch --rss-only, or help")
            continue

        if lower.startswith("model"):
            parts = shlex.split(raw)
            if len(parts) == 1:
                console.print(f"Session model: {session_model or 'default from .env'}")
            else:
                session_model = " ".join(parts[1:]).strip()
                console.print(f"Session model set to: {session_model}")
            continue

        if lower in {"news today", "whats the news for today", "what's the news for today", "news", "today news"}:
            try:
                result = run_pipeline_service(
                    FetchRequest(limit_per_source=20, include_newsapi=bool(settings.newsapi_key)),
                    DigestRequest(model=session_model or None),
                )
                console.print(f"Fetched {result.fetch.total_fetched} items. Snapshot: {result.fetch.snapshot_id}")
                console.print(format_digest_text(result.digest))
            except Exception as exc:
                console.print(f"Error: {exc}")
            continue

        if lower in {"agenda", "today agenda", "what is agenda", "what's agenda"}:
            try:
                _print_digest(model=session_model)
            except Exception as exc:
                console.print(f"Error: {exc}")
            continue

        parts = shlex.split(raw)
        cmd = parts[0].lower()
        args = parts[1:]

        try:
            if cmd == "fetch":
                limit = _parse_int_arg(args, "--limit", 20)
                rss_only = "--rss-only" in args
                response = fetch_news_service(
                    FetchRequest(limit_per_source=limit, include_newsapi=not rss_only)
                )
                console.print(
                    f"Fetched {response.total_fetched} items. Snapshot: {response.snapshot_id}. Sources: {response.source_breakdown}"
                )
            elif cmd == "digest":
                snapshot_id = _parse_arg(args, "--snapshot", "")
                model = _parse_arg(args, "--model", session_model)
                bullets = _parse_int_arg(args, "--bullets", 12)
                _print_digest(snapshot_id=snapshot_id, model=model, max_bullets=bullets)
            elif cmd == "pipeline":
                limit = _parse_int_arg(args, "--limit", 20)
                rss_only = "--rss-only" in args
                result = run_pipeline_service(
                    FetchRequest(limit_per_source=limit, include_newsapi=not rss_only),
                    DigestRequest(model=session_model or None),
                )
                console.print(f"Fetched {result.fetch.total_fetched} items. Snapshot: {result.fetch.snapshot_id}")
                console.print(format_digest_text(result.digest))
            elif cmd == "benchmark":
                snapshot_id = _parse_arg(args, "--snapshot", "")
                if not snapshot_id:
                    console.print("Error: --snapshot is required for benchmark")
                    continue
                raw_models = _parse_arg(args, "--models", "")
                bullets = _parse_int_arg(args, "--bullets", 12)
                if raw_models:
                    models = [x.strip() for x in raw_models.split(",") if x.strip()]
                else:
                    models = [
                        "qwen3.5:9b",
                        "deepseek-r1:7b",
                        "qwen2.5-coder:7b",
                        "qwen2.5:7b-instruct",
                        "mistral:7b-instruct",
                    ]
                report = run_model_benchmark(snapshot_id=snapshot_id, models=models, max_bullets=bullets)
                console.print(f"Benchmark completed for {snapshot_id}")
                for row in report.get("results", []):
                    console.print(
                        f"- {row['model']}: score={row['aggregate_score']} latency_ms={row['latency_ms']} "
                        f"india_points={row['india_points']} world_points={row['world_points']}"
                    )
            elif cmd == "graph":
                snapshot_id = _parse_arg(args, "--snapshot", "")
                top_n = _parse_int_arg(args, "--top", 36)
                min_sim_raw = _parse_arg(args, "--min-sim", "0.44")
                adaptive = "--no-adaptive" not in args
                try:
                    min_sim = float(min_sim_raw)
                except ValueError:
                    min_sim = 0.44
                result = build_relationship_graph(
                    snapshot_id=snapshot_id,
                    top_n=top_n,
                    min_similarity=min_sim,
                    adaptive=adaptive,
                )
                _render_graph_summary(result)
            elif cmd == "logo":
                console.print("FRIDAY logo file:")
                console.print("assets/friday_logo.svg")
                console.print("Open it in VS Code preview or browser for the full HUD look.")
            elif cmd == "metrics":
                snapshot_id = _parse_arg(args, "--snapshot", "")
                limit = _parse_int_arg(args, "--limit", 50)
                metrics = get_metrics_summary_service(snapshot_id=snapshot_id, limit=limit)
                _render_metrics_summary(metrics)
            elif cmd == "route-test":
                prompts_raw = _parse_arg(args, "--prompts", "")
                if prompts_raw:
                    prompts = [p.strip() for p in prompts_raw.split("|") if p.strip()]
                else:
                    prompts = [
                        "set up pre-commit hooks and fix lint failures",
                        "review this PR risks and write release notes",
                        "graph has too few clusters tune similarity threshold",
                        "improve CLI dashboard and command discoverability",
                        "run full dev cycle and ship after checks",
                    ]
                report = run_route_harness(prompts)
                console.print(f"Routed {report['prompt_count']} prompts.")
                console.print(f"Output: {report['output_file']}")
                for specialist, count in report.get("specialist_counts", {}).items():
                    if count:
                        console.print(f"- {specialist}: {count}")
            else:
                console.print("Unknown command. Type 'help'.")
        except Exception as exc:
            console.print(f"Error: {exc}")


if __name__ == "__main__":
    run_cli()
