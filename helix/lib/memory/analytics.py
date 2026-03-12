"""Graph topology analytics for insight knowledge structure.

Computes connected components, articulation points (bridges),
density, and isolate detection. Used by strategic_recall for
orchestrator-level structural signals.
"""

try:
    from ..db.connection import get_db
except ImportError:
    from db.connection import get_db

GRAPH_MIN_SIZE = 10  # Below this, topology is trivially small


def graph_analytics(insight_ids=None):
    """Compute structural metrics over the insight graph.

    Args:
        insight_ids: If provided, restrict analysis to subgraph of these IDs.
                     If None, analyze full graph.

    Returns dict with: graph_too_small, node_count, edge_count, clusters,
    largest_cluster, bridges (list of insight names), isolates (list of insight names),
    density (float).
    """
    db = get_db()

    # Load edges
    if insight_ids:
        placeholders = ",".join("?" for _ in insight_ids)
        edges = db.execute(
            f"SELECT src_id, dst_id FROM insight_edges "
            f"WHERE src_id IN ({placeholders}) OR dst_id IN ({placeholders})",
            list(insight_ids) + list(insight_ids)
        ).fetchall()
        all_node_ids = set(insight_ids)
    else:
        edges = db.execute("SELECT src_id, dst_id FROM insight_edges").fetchall()
        # Get all insight IDs
        rows = db.execute("SELECT id FROM insight").fetchall()
        all_node_ids = {r["id"] for r in rows}

    # Build adjacency
    adj = {nid: set() for nid in all_node_ids}
    edge_count = 0
    for e in edges:
        src, dst = e["src_id"], e["dst_id"]
        if src in all_node_ids and dst in all_node_ids:
            adj.setdefault(src, set()).add(dst)
            adj.setdefault(dst, set()).add(src)
            edge_count += 1

    node_count = len(all_node_ids)

    if node_count < GRAPH_MIN_SIZE:
        return {
            "graph_too_small": True,
            "node_count": node_count,
            "edge_count": edge_count,
            "clusters": 0,
            "largest_cluster": 0,
            "bridges": [],
            "isolates": [],
            "density": 0.0,
        }

    # Connected components (iterative BFS)
    visited = set()
    components = []
    for node in all_node_ids:
        if node in visited:
            continue
        component = set()
        queue = [node]
        while queue:
            n = queue.pop()
            if n in visited:
                continue
            visited.add(n)
            component.add(n)
            queue.extend(adj[n] - visited)
        components.append(component)

    # Articulation points (iterative Tarjan's)
    bridges = set()
    disc = {}
    low = {}
    parent = {}
    timer = [0]

    for start in all_node_ids:
        if start in disc:
            continue
        stack = [(start, iter(adj[start]), False)]
        parent[start] = -1
        disc[start] = low[start] = timer[0]
        timer[0] += 1
        child_count = {start: 0}

        while stack:
            node, neighbors, returning = stack[-1]
            if returning:
                stack.pop()
                if stack:
                    p = stack[-1][0]
                    low[p] = min(low[p], low[node])
                    child_count.setdefault(p, 0)
                    # Articulation point conditions
                    if parent[p] == -1:
                        if child_count[p] > 1:
                            bridges.add(p)
                    elif low[node] >= disc[p]:
                        bridges.add(p)
                continue

            found_next = False
            for nbr in neighbors:
                if nbr not in disc:
                    parent[nbr] = node
                    disc[nbr] = low[nbr] = timer[0]
                    timer[0] += 1
                    child_count[node] = child_count.get(node, 0) + 1
                    stack[-1] = (node, neighbors, False)
                    stack.append((nbr, iter(adj[nbr]), False))
                    found_next = True
                    break
                elif nbr != parent.get(node, -1):
                    low[node] = min(low[node], disc[nbr])

            if not found_next:
                stack[-1] = (node, neighbors, True)

    # Isolates
    nodes_with_edges = set()
    for e in edges:
        if e["src_id"] in all_node_ids:
            nodes_with_edges.add(e["src_id"])
        if e["dst_id"] in all_node_ids:
            nodes_with_edges.add(e["dst_id"])
    isolate_ids = all_node_ids - nodes_with_edges

    # Density
    density = (2.0 * edge_count) / (node_count * (node_count - 1)) if node_count > 1 else 0.0

    # Resolve IDs to names
    ids_to_resolve = bridges | isolate_ids
    name_map = {}
    if ids_to_resolve:
        ph = ",".join("?" for _ in ids_to_resolve)
        rows = db.execute(f"SELECT id, name FROM insight WHERE id IN ({ph})", list(ids_to_resolve)).fetchall()
        name_map = {r["id"]: r["name"] for r in rows}

    return {
        "graph_too_small": False,
        "node_count": node_count,
        "edge_count": edge_count,
        "clusters": len(components),
        "largest_cluster": max(len(c) for c in components) if components else 0,
        "bridges": [name_map[bid] for bid in bridges if bid in name_map],
        "isolates": [name_map[iid] for iid in isolate_ids if iid in name_map],
        "density": round(density, 4),
    }
