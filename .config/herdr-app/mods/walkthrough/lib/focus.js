/** One-hop focus only: preserve all layout and data, emphasize the selected
 * component and its incident relationships, including incoming edges. */
export function diagramFocus(graph, selectedId) {
  const active = graph.nodes.some((n) => n.id === selectedId);
  const nodes = new Set(active ? [selectedId] : graph.nodes.map((n) => n.id));
  const edges = new Set();
  graph.edges.forEach((edge, index) => {
    if (!active || edge.from === selectedId || edge.to === selectedId) {
      edges.add(index); nodes.add(edge.from); nodes.add(edge.to);
    }
  });
  const groups = new Set((graph.groups ?? []).filter((g) => g.nodes.some((id) => nodes.has(id))).map((g) => g.id));
  return { active, nodes, edges, groups };
}
