import json
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Tuple
import re

from .config import settings
from .schemas import NewsItem
from .storage import storage


STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "into",
    "over",
    "under",
    "after",
    "before",
    "amid",
    "says",
    "said",
    "new",
    "news",
    "today",
    "india",
    "world",
    "live",
    "update",
    "updates",
}


@dataclass
class GraphNode:
    node_id: str
    title: str
    source: str
    category: str


@dataclass
class GraphEdge:
    left: str
    right: str
    weight: float


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _tokens(text: str) -> set:
    parts = re.findall(r"[a-zA-Z0-9']+", text.lower())
    return {p for p in parts if len(p) >= 4 and p not in STOPWORDS}


def _relation_score(a: str, b: str) -> Tuple[float, int]:
    set_a = _tokens(a)
    set_b = _tokens(b)
    common = set_a.intersection(set_b)
    union = set_a.union(set_b)
    jaccard = (len(common) / len(union)) if union else 0.0
    seq = _sim(a, b)
    score = (0.65 * jaccard) + (0.35 * seq)
    return score, len(common)


def _shorten(text: str, max_len: int = 72) -> str:
    clean = " ".join(text.split())
    return clean if len(clean) <= max_len else clean[: max_len - 3] + "..."


def _load_ranked_snapshot(snapshot_id: str = "", top_n: int = 36) -> Tuple[str, List[NewsItem]]:
    if snapshot_id:
        sid = snapshot_id
        payload = storage.load_raw(snapshot_id)
    else:
        sid, payload = storage.latest_raw()

    items = [NewsItem(**row) for row in payload.get("items", [])]
    items = items[: max(1, min(top_n, 100))]
    return sid, items


def _build_edges(nodes: List[GraphNode], min_similarity: float) -> List[GraphEdge]:
    edges: List[GraphEdge] = []
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            weight, shared_tokens = _relation_score(nodes[i].title, nodes[j].title)
            # Require either enough shared informative tokens, or a very strong lexical match.
            if weight >= min_similarity and (shared_tokens >= 2 or weight >= 0.68):
                edges.append(GraphEdge(left=nodes[i].node_id, right=nodes[j].node_id, weight=round(weight, 3)))
    return edges


def _count_clusters(nodes: List[GraphNode], edges: List[GraphEdge]) -> List[List[str]]:
    adjacency: Dict[str, List[str]] = defaultdict(list)
    for edge in edges:
        adjacency[edge.left].append(edge.right)
        adjacency[edge.right].append(edge.left)

    visited = set()
    clusters = []
    for node in nodes:
        if node.node_id in visited:
            continue
        stack = [node.node_id]
        cluster_ids = []
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            cluster_ids.append(current)
            stack.extend(adjacency.get(current, []))
        if len(cluster_ids) >= 2:
            clusters.append(cluster_ids)
    return clusters


def build_relationship_graph(
    snapshot_id: str = "",
    top_n: int = 36,
    min_similarity: float = 0.44,
    adaptive: bool = True,
) -> Dict[str, object]:
    sid, items = _load_ranked_snapshot(snapshot_id=snapshot_id, top_n=top_n)

    bounded_min_similarity = max(0.2, min(min_similarity, 0.95))

    nodes: List[GraphNode] = []
    for i, item in enumerate(items, start=1):
        nodes.append(
            GraphNode(
                node_id=f"N{i}",
                title=item.title,
                source=item.source,
                category=item.category,
            )
        )

    used_similarity = bounded_min_similarity
    edges = _build_edges(nodes, min_similarity=used_similarity)
    clusters = _count_clusters(nodes, edges)

    if adaptive and (len(edges) < 2 or len(clusters) == 0) and len(nodes) >= 10:
        for candidate in (0.40, 0.36, 0.33, 0.30, 0.28):
            if candidate >= used_similarity:
                continue
            trial_edges = _build_edges(nodes, min_similarity=candidate)
            trial_clusters = _count_clusters(nodes, trial_edges)
            if len(trial_edges) >= 2 or len(trial_clusters) >= 1:
                used_similarity = candidate
                edges = trial_edges
                clusters = trial_clusters
                break

    lines = ["graph TD"]
    for node in nodes:
        label = _shorten(node.title).replace('"', "'")
        lines.append(f'    {node.node_id}["{label}\\n({node.source})"]')

    for edge in edges:
        lines.append(f"    {edge.left} ---|{edge.weight}| {edge.right}")

    for node in nodes:
        if node.category == "india":
            lines.append(f"    style {node.node_id} fill:#0B5ED7,stroke:#74F7FF,color:#ffffff")

    mermaid = "\n".join(lines)

    graph_dir = Path(settings.data_dir) / "graphs"
    graph_dir.mkdir(parents=True, exist_ok=True)
    mmd_path = graph_dir / f"{sid}.mmd"
    json_path = graph_dir / f"{sid}.json"
    mmd_path.write_text(mermaid, encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "snapshot_id": sid,
                "top_n": top_n,
                "min_similarity": bounded_min_similarity,
                "used_similarity": used_similarity,
                "adaptive": adaptive,
                "node_count": len(nodes),
                "edge_count": len(edges),
                "clusters": clusters,
                "nodes": [n.__dict__ for n in nodes],
                "edges": [e.__dict__ for e in edges],
                "mermaid_file": str(mmd_path),
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "snapshot_id": sid,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "cluster_count": len(clusters),
        "min_similarity": bounded_min_similarity,
        "used_similarity": used_similarity,
        "adaptive": adaptive,
        "mermaid": mermaid,
        "mermaid_file": str(mmd_path),
        "json_file": str(json_path),
        "clusters": clusters,
        "nodes": [n.__dict__ for n in nodes],
    }
