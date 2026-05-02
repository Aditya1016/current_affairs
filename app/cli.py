import shlex
from typing import List

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .benchmark import run_model_benchmark
from .graph_view import build_relationship_graph
from .route_harness import run_route_harness
from .schemas import DigestRequest, FetchRequest
from .service import (
    fetch_news_service,
    format_digest_text,
    format_india_digest_text,
    generate_today_india_digest_service,
    generate_digest_service,
    get_metrics_summary_service,
    get_metrics_trend_service,
    run_pipeline_service,
    search_stories_service,
    word_pack_service,
    word_of_day_service,
)
from .ui_config import load_ui_config, save_ui_config
from .trending import detect_trending_topics, get_trending_by_category


HELP_TEXT = """
Commands:
  help                              Show this help
  fetch [--rss-only] [--limit N]    Fetch headlines and save snapshot
  digest [--snapshot ID] [--model M] [--bullets N]
                                    Generate digest from snapshot or latest
    news today                        Fresh India-only digest for today
    word today [--level easy|balanced|exam] [--no-repeat DAYS]
                                    Fresh India-relevant uncommon word of the day
    word pack [--count N] [--level easy|balanced|exam] [--no-repeat DAYS]
                                    Generate a unique vocabulary pack from today's India news
    agenda                            Digest from latest snapshot
  pipeline [--rss-only] [--limit N] Run fetch + digest in one step
    search "QUERY" [--limit N] [--category india|world] [--source NAME] [--days N] [--plot] [--plot-by source|category]
                                                                        Search indexed stories from past snapshots
    trending [--days N] [--min-occurrences N] [--limit N]
                                                                        Show trending topics across all categories
    trending-india [--days N] [--limit N]                             Show trending topics in India news
    trending-world [--days N] [--limit N]                             Show trending topics in World news
    benchmark --snapshot ID [--models "m1,m2"] [--bullets N] [--plot] [--plot-mode score|latency|both]
                                                                        Run model comparison with optional terminal charts
    graph [--snapshot ID] [--top N] [--min-sim F] [--no-adaptive]
                                                                        Build related-news graph (Mermaid + JSON)
    metrics [--snapshot ID] [--limit N] [--phase NAME] [--trend N] [--plot]
                                                                        Show phase timing summary or time trend sparkline
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


def _sparkline(values: List[float]) -> str:
    if not values:
        return ""
    ticks = "▁▂▃▄▅▆▇█"
    v_min = min(values)
    v_max = max(values)
    if abs(v_max - v_min) < 1e-9:
        return ticks[0] * len(values)
    out = []
    span = v_max - v_min
    for value in values:
        idx = int(((value - v_min) / span) * (len(ticks) - 1))
        out.append(ticks[max(0, min(idx, len(ticks) - 1))])
    return "".join(out)


def _render_metrics_trend(result: dict) -> None:
    points = result.get("points", [])
    if not points:
        console.print("No trend samples found for the given filters.")
        return

    phase = str(result.get("phase", "") or "all phases")
    values = [float(row.get("duration_ms", 0.0)) for row in points]
    chart = _sparkline(values)

    summary = Table(title="Pipeline Phase Trend")
    summary.add_column("Metric")
    summary.add_column("Value")
    summary.add_row("Phase", phase)
    summary.add_row("Samples", str(result.get("count", 0)))
    summary.add_row("Min ms", str(result.get("min_ms", 0)))
    summary.add_row("Avg ms", str(result.get("avg_ms", 0)))
    summary.add_row("Max ms", str(result.get("max_ms", 0)))
    summary.add_row("Sparkline", chart)
    console.print(summary)

    detail = Table(title="Recent Samples")
    detail.add_column("#", justify="right")
    detail.add_column("Time")
    detail.add_column("Phase")
    detail.add_column("Duration ms", justify="right")
    for idx, row in enumerate(points[-12:], start=max(1, len(points) - 11)):
        detail.add_row(
            str(idx),
            str(row.get("created_at", ""))[:19],
            str(row.get("phase", "")),
            str(round(float(row.get("duration_ms", 0.0)), 2)),
        )
    console.print(detail)


def _render_plotext_series(title: str, values: List[float], y_label: str) -> None:
    if not values:
        return
    try:
        import plotext as plt  # type: ignore
    except ImportError:
        console.print("plotext is not installed. Install requirements to enable --plot charts.")
        return

    try:
        x = list(range(1, len(values) + 1))
        plt.clf()
        plt.title(title)
        plt.xlabel("Sample")
        plt.ylabel(y_label)
        plt.plot(x, values)
        plt.show()
    except Exception as exc:
        console.print(f"Could not render plot chart: {exc}")


def _render_plotext_bar(title: str, labels: List[str], values: List[float], y_label: str, x_label: str = "Category") -> None:
    if not labels or not values:
        return
    try:
        import plotext as plt  # type: ignore
    except ImportError:
        console.print("plotext is not installed. Install requirements to enable --plot charts.")
        return

    try:
        plt.clf()
        plt.title(title)
        plt.xlabel(x_label)
        plt.ylabel(y_label)
        plt.bar(labels, values)
        plt.show()
    except Exception as exc:
        console.print(f"Could not render bar chart: {exc}")


def _render_benchmark_plot(report: dict, mode: str = "both") -> None:
    results = report.get("results", [])
    if not results:
        return

    models = [str(row.get("model", "")) for row in results]
    scores = [float(row.get("aggregate_score", 0.0)) for row in results]
    latencies = [float(row.get("latency_ms", 0.0)) for row in results]

    selected_mode = (mode or "both").strip().lower()
    if selected_mode not in {"score", "latency", "both"}:
        selected_mode = "both"

    if selected_mode in {"score", "both"}:
        _render_plotext_bar(
            title="Benchmark Aggregate Scores",
            labels=models,
            values=scores,
            y_label="Score",
            x_label="Model",
        )

    if selected_mode in {"latency", "both"}:
        _render_plotext_bar(
            title="Benchmark Latency (ms)",
            labels=models,
            values=latencies,
            y_label="Latency ms",
            x_label="Model",
        )


def _render_search_distribution_plot(result: dict, plot_by: str = "source") -> None:
    selected = (plot_by or "source").strip().lower()
    if selected not in {"source", "category"}:
        selected = "source"

    buckets = {}
    for row in result.get("results", []):
        key = str(row.get(selected, "") or "unknown")
        buckets[key] = buckets.get(key, 0) + 1

    if not buckets:
        return

    labels = list(buckets.keys())
    values = [float(buckets[label]) for label in labels]
    _render_plotext_bar(
        title=f"Search Distribution by {selected.title()}",
        labels=labels,
        values=values,
        y_label="Stories",
        x_label=selected.title(),
    )


def _render_story_search(result: dict) -> None:
    table = Table(title="Story Search")
    table.add_column("#", justify="right")
    table.add_column("Category")
    table.add_column("Source")
    table.add_column("Published")
    table.add_column("Title")

    for idx, row in enumerate(result.get("results", []), start=1):
        published = str(row.get("published_at", ""))[:19]
        table.add_row(
            str(idx),
            str(row.get("category", "")),
            str(row.get("source", ""))[:24],
            published,
            str(row.get("title", ""))[:96],
        )

    if not result.get("results"):
        console.print("No matching stories found. Try a broader query or increase --days.")
        return

    console.print(table)
    console.print(f"Total matches: {result.get('total', 0)}")


def _render_word_pack(result: dict) -> None:
    table = Table(title="Word Pack")
    table.add_column("#", justify="right")
    table.add_column("Word")
    table.add_column("Difficulty")
    table.add_column("Meaning")
    table.add_column("Context")

    for idx, row in enumerate(result.get("items", []), start=1):
        table.add_row(
            str(idx),
            str(row.get("word", "")),
            str(row.get("difficulty", "")),
            str(row.get("definition", ""))[:92],
            str(row.get("context_headline", ""))[:84],
        )

    if not result.get("items"):
        console.print("No words selected for pack. Try reducing --no-repeat or switching difficulty.")
        return

    console.print(table)
    console.print(
        f"Pack size: {result.get('count', 0)} | Difficulty: {result.get('difficulty', '')} "
        f"| No-repeat days: {result.get('no_repeat_days', 0)}"
    )


def _render_trending_topics(topics: List[dict]) -> None:
    """Render trending topics as a formatted table."""
    table = Table(title="Trending Topics")
    table.add_column("Rank", justify="right")
    table.add_column("Topic")
    table.add_column("Frequency")
    table.add_column("Top Stories")

    for idx, topic_data in enumerate(topics, start=1):
        topic = topic_data.get("topic", "N/A")
        freq = topic_data.get("frequency", 0)
        pct = topic_data.get("percentage", 0)
        stories = topic_data.get("sample_stories", [])
        story_titles = "; ".join([s.get("title", "")[:40] for s in stories[:2]])
        
        table.add_row(
            str(idx),
            topic,
            f"{freq} ({pct}%)",
            story_titles,
        )

    if not topics:
        console.print("No trending topics found.")
        return

    console.print(table)


def _render_metrics_summary(metrics: dict) -> None:
    """Render metrics summary as a formatted table."""
    table = Table(title="Metrics Summary")
    table.add_column("Phase", style="cyan")
    table.add_column("Calls", justify="right")
    table.add_column("Total (ms)", justify="right")
    table.add_column("Avg (ms)", justify="right")

    for phase_data in metrics.get("phases", []):
        phase = phase_data.get("phase", "unknown")
        calls = phase_data.get("call_count", 0)
        total_ms = phase_data.get("total_ms", 0.0)
        avg_ms = total_ms / calls if calls > 0 else 0
        table.add_row(str(phase), str(calls), f"{total_ms:.2f}", f"{avg_ms:.2f}")

    console.print(table)


def run_cli() -> None:  # noqa: C901
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
                digest = generate_today_india_digest_service(
                    limit_per_source=20,
                    model=session_model or "",
                    max_bullets=12,
                )
                console.print("Generated fresh India-only digest for today.")
                console.print(format_india_digest_text(digest))
            except Exception as exc:
                console.print(f"Error: {exc}")
            continue

        if lower in {"word today", "word", "vocab", "vocab today", "word of the day"}:
            try:
                result = word_of_day_service(limit_per_source=25, difficulty="balanced", no_repeat_days=14)
                console.print("Word of the day (India current affairs):")
                console.print(f"- Word: {result.word}")
                console.print(f"- Context headline: {result.context_headline}")
                console.print(f"- Relevance: {result.relevance_note}")
                console.print(f"- Meaning: {result.definition}")
                console.print(f"- Difficulty: {result.difficulty}")
                console.print(f"- Snapshot: {result.snapshot_id}")
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
                    f"Fetched {response.total_fetched} items. "
                    f"Snapshot: {response.snapshot_id}. "
                    f"Sources: {response.source_breakdown}"
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
            elif cmd == "search":
                query = ""
                if args and not args[0].startswith("--"):
                    query = args[0]
                limit = _parse_int_arg(args, "--limit", 20)
                category = _parse_arg(args, "--category", "")
                source = _parse_arg(args, "--source", "")
                days = _parse_int_arg(args, "--days", 0)
                show_plot = "--plot" in args
                plot_by = _parse_arg(args, "--plot-by", "source")
                search_result = search_stories_service(
                    query=query,
                    limit=limit,
                    category=category,
                    source=source,
                    days=days,
                )
                search_payload = search_result.dict()
                _render_story_search(search_payload)
                if show_plot:
                    _render_search_distribution_plot(search_payload, plot_by=plot_by)
            elif cmd in {"trending", "trending-india", "trending-world"}:
                days = _parse_int_arg(args, "--days", 7)
                limit = _parse_int_arg(args, "--limit", 10 if cmd == "trending" else 5)
                min_occ = _parse_int_arg(args, "--min-occurrences", 3)
                
                if cmd == "trending":
                    topics = detect_trending_topics(days=days, min_occurrences=min_occ, limit=limit)
                    console.print(f"\n[bold cyan]Trending Topics (Last {days} days)[/]")
                elif cmd == "trending-india":
                    topics = get_trending_by_category(category="india", days=days, limit=limit)
                    console.print(f"\n[bold cyan]Trending in India (Last {days} days)[/]")
                else:  # trending-world
                    topics = get_trending_by_category(category="world", days=days, limit=limit)
                    console.print(f"\n[bold cyan]Trending in World (Last {days} days)[/]")
                
                _render_trending_topics(topics)
            elif cmd in {"word", "vocab"}:
                level = _parse_arg(args, "--level", "balanced")
                no_repeat_days = _parse_int_arg(args, "--no-repeat", 14)
                subcmd = "today"
                if args and not args[0].startswith("--"):
                    subcmd = args[0].lower()

                if subcmd == "pack":
                    count = _parse_int_arg(args, "--count", 5)
                    pack = word_pack_service(
                        limit_per_source=25,
                        difficulty=level,
                        count=count,
                        no_repeat_days=no_repeat_days,
                    )
                    _render_word_pack(pack.dict())
                    continue

                if subcmd != "today":
                    console.print("Usage: word today|pack [--level easy|balanced|exam] [--no-repeat DAYS] [--count N]")
                    continue

                result = word_of_day_service(limit_per_source=25, difficulty=level, no_repeat_days=no_repeat_days)
                console.print("Word of the day (India current affairs):")
                console.print(f"- Word: {result.word}")
                console.print(f"- Context headline: {result.context_headline}")
                console.print(f"- Relevance: {result.relevance_note}")
                console.print(f"- Meaning: {result.definition}")
                console.print(f"- Difficulty: {result.difficulty}")
                console.print(f"- No-repeat days: {no_repeat_days}")
                console.print(f"- Snapshot: {result.snapshot_id}")
            elif cmd == "benchmark":
                snapshot_id = _parse_arg(args, "--snapshot", "")
                if not snapshot_id:
                    console.print("Error: --snapshot is required for benchmark")
                    continue
                show_plot = "--plot" in args
                plot_mode = _parse_arg(args, "--plot-mode", "both")
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
                if show_plot:
                    _render_benchmark_plot(report, mode=plot_mode)
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
                phase = _parse_arg(args, "--phase", "")
                trend = _parse_int_arg(args, "--trend", 0)
                show_plot = "--plot" in args
                if trend > 0 or phase:
                    trend_rows = get_metrics_trend_service(
                        snapshot_id=snapshot_id,
                        phase=phase,
                        limit=trend if trend > 0 else limit,
                    )
                    _render_metrics_trend(trend_rows)
                    if show_plot:
                        points = trend_rows.get("points", [])
                        values = [float(row.get("duration_ms", 0.0)) for row in points]
                        plot_phase = str(trend_rows.get("phase", "") or "all")
                        _render_plotext_series(
                            title=f"Phase Trend: {plot_phase}",
                            values=values,
                            y_label="Duration ms",
                        )
                else:
                    metrics = get_metrics_summary_service(snapshot_id=snapshot_id, limit=limit)
                    _render_metrics_summary(metrics)
                    if show_plot:
                        rows = metrics.get("phases", [])
                        labels = [str(row.get("phase", "")) for row in rows]
                        values = [float(row.get("total_ms", 0.0)) for row in rows]
                        _render_plotext_bar(
                            title="Total Phase Duration (ms)",
                            labels=labels,
                            values=values,
                            y_label="Total ms",
                        )
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
