"""Simple web dashboard for current affairs digest and trending topics."""

import html as html_lib
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Union

IST = timezone(timedelta(hours=5, minutes=30))


def generate_dashboard_html(  # noqa: C901
    digest: Optional[Union[Dict, object]] = None,
    trending: Optional[List[Dict]] = None,
    trending_india: Optional[List[Dict]] = None,
) -> str:
    """Generate a simple HTML dashboard showing digest + trending topics."""

    # Convert digest to dict if it's a Pydantic model
    if digest is not None and hasattr(digest, 'dict'):
        digest = digest.dict()

    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")

    # Build India digest section
    india_html = ""
    if digest and "india_points" in digest:
        india_points = digest.get("india_points", [])
        india_html = '<div class="section"><h2>🇮🇳 India</h2><ul class="points">'
        for point in india_points:
            sources = html_lib.escape(", ".join(point.get("sources", [])))
            pt = html_lib.escape(str(point.get("point", "")))
            india_html += f'<li><strong>{pt}</strong> <span class="source">({sources})</span></li>'
        india_html += "</ul></div>"

    # Build World digest section
    world_html = ""
    if digest and "world_points" in digest:
        world_points = digest.get("world_points", [])
        world_html = '<div class="section"><h2>🌍 World</h2><ul class="points">'
        for point in world_points:
            sources = html_lib.escape(", ".join(point.get("sources", [])))
            pt = html_lib.escape(str(point.get("point", "")))
            world_html += f'<li><strong>{pt}</strong> <span class="source">({sources})</span></li>'
        world_html += "</ul></div>"

    # Build trending section
    trending_html = ""
    if trending or trending_india:
        trending_html = '<div class="section"><h2>🔥 Trending Topics</h2><div class="trending-grid">'

        if trending_india:
            trending_html += '<div class="trending-column"><h3>India Trending</h3><ul>'
            for topic_data in trending_india[:5]:
                topic = html_lib.escape(str(topic_data.get("topic", "N/A")))
                freq = int(topic_data.get("frequency", 0))
                trending_html += f'<li>{topic} <span class="frequency">×{freq}</span></li>'
            trending_html += '</ul></div>'

        if trending:
            trending_html += '<div class="trending-column"><h3>All Topics</h3><ul>'
            for topic_data in trending[:5]:
                topic = html_lib.escape(str(topic_data.get("topic", "N/A")))
                pct = topic_data.get("percentage", 0)
                trending_html += f'<li>{topic} <span class="percentage">{pct}%</span></li>'
            trending_html += '</ul></div>'

        trending_html += "</div></div>"

    # Build main template
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📰 Friday - Current Affairs Digest</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            line-height: 1.6;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            overflow: hidden;
        }}
        header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px 20px;
            text-align: center;
        }}
        header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            letter-spacing: 1px;
        }}
        header p {{
            font-size: 0.9em;
            opacity: 0.9;
        }}
        .content {{
            padding: 30px;
        }}
        .section {{
            margin-bottom: 30px;
            border-left: 4px solid #667eea;
            padding-left: 20px;
        }}
        .section h2 {{
            font-size: 1.5em;
            margin-bottom: 15px;
            color: #667eea;
        }}
        .section h3 {{
            font-size: 1.1em;
            margin-bottom: 10px;
            color: #555;
        }}
        .points {{
            list-style: none;
        }}
        .points li {{
            margin-bottom: 12px;
            padding: 10px;
            background: #f5f5f5;
            border-radius: 6px;
            transition: background 0.3s;
        }}
        .points li:hover {{
            background: #e8e8ff;
        }}
        .source {{
            color: #999;
            font-size: 0.85em;
            margin-left: 8px;
        }}
        .frequency {{
            background: #667eea;
            color: white;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.8em;
            font-weight: bold;
            margin-left: 10px;
        }}
        .percentage {{
            background: #764ba2;
            color: white;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.8em;
            font-weight: bold;
            margin-left: 10px;
        }}
        .trending-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
        }}
        .trending-column {{
            background: #f9f9f9;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #eee;
        }}
        .trending-column ul {{
            list-style: none;
        }}
        .trending-column li {{
            padding: 8px 0;
            border-bottom: 1px solid #eee;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .trending-column li:last-child {{
            border-bottom: none;
        }}
        footer {{
            background: #f5f5f5;
            padding: 20px;
            text-align: center;
            border-top: 1px solid #eee;
            font-size: 0.85em;
            color: #999;
        }}
        .empty-state {{
            text-align: center;
            padding: 40px;
            color: #999;
        }}
        .empty-state svg {{
            font-size: 3em;
            margin-bottom: 10px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📰 Friday</h1>
            <p>Your Local Current Affairs Digest</p>
        </header>

        <div class="content">
            {india_html if india_html else
             '<div class="empty-state"><p>📭 No digest available. Run `news today` or `pipeline` to generate.</p></div>'}
            {world_html}
            {trending_html if (trending or trending_india) else
             '<div class="empty-state"><p>🔍 No trending data available yet.</p></div>'}
        </div>

        <footer>
            Generated at {now} | <a href="/docs">API Docs</a>
        </footer>
    </div>
</body>
</html>
"""
    return html


def generate_search_results_html(search_results: Dict) -> str:
    """Generate HTML for search results page."""
    query = search_results.get("query", "")
    total = search_results.get("total", 0)
    results = search_results.get("results", [])

    results_html = ""
    for result in results[:50]:
        title = html_lib.escape(result.get("title", "N/A"))
        source = html_lib.escape(result.get("source", "N/A"))
        category = html_lib.escape(result.get("category", "world"))
        raw_url = result.get("url", "#")
        # Only allow http/https URLs to prevent javascript: XSS
        safe_url = html_lib.escape(raw_url) if raw_url.startswith(("http://", "https://")) else "#"
        results_html += f"""
        <div class="result-item">
            <h3><a href="{safe_url}" target="_blank">{title}</a></h3>
            <p class="meta">
                <span class="source">{source}</span>
                <span class="category">{category}</span>
            </p>
        </div>
        """

    escaped_query = html_lib.escape(str(query))
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Search: {escaped_query} - Friday</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            text-align: center;
        }}
        .header h1 {{
            margin-bottom: 5px;
        }}
        .header p {{
            opacity: 0.9;
        }}
        .container {{
            max-width: 900px;
            margin: 20px auto;
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        }}
        .result-item {{
            padding: 15px;
            margin-bottom: 15px;
            border-left: 4px solid #667eea;
            border-radius: 4px;
            background: #f9f9f9;
        }}
        .result-item h3 {{
            margin-bottom: 8px;
        }}
        .result-item a {{
            color: #667eea;
            text-decoration: none;
        }}
        .result-item a:hover {{
            text-decoration: underline;
        }}
        .meta {{
            font-size: 0.85em;
            color: #999;
        }}
        .source, .category {{
            display: inline-block;
            margin-right: 15px;
            padding: 2px 8px;
            background: #e8e8ff;
            border-radius: 3px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Search Results</h1>
        <p>Query: <strong>{escaped_query}</strong> | Total: {total}</p>
    </div>
    <div class="container">
        {results_html if results_html else '<p>No results found.</p>'}
    </div>
</body>
</html>
"""
    return html
