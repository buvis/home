import { div, PathBuilder } from "gpui-kit";
import { h_flex } from "gpui-base";
import { diagramFocus } from "./lib/focus.js";
import { layoutDiagram } from "./lib/diagram.js";

/** Mix the live theme rather than fixing the drawing to a dark-only palette. */
function mix(a, b, amount) {
  const channels = (hex) => {
    let s = hex.slice(1, 7);
    if (s.length === 3) s = [...s].map((c) => c + c).join("");
    return [0, 2, 4].map((i) => parseInt(s.slice(i, i + 2), 16));
  };
  const x = channels(a), y = channels(b);
  return /** @type {`#${string}`} */ ("#" + x.map((v, i) => Math.round(v + (y[i] - v) * amount).toString(16).padStart(2, "0")).join(""));
}

/**
 * The layout depends only on the stored diagram, its labels and boundaries
 * (with which evidence went missing), never on zoom or selection: it is kept
 * between renders and redone only when one of those changes.
 */
const layouts = new Map();
function cachedLayout(source, connections, groups) {
  // The whole input: the layout carries each label's and boundary's fields (reason, missing) through to the drawing.
  const key = JSON.stringify([source, connections, groups]);
  if (!layouts.has(key)) {
    if (layouts.size >= 8) layouts.delete(layouts.keys().next().value);
    layouts.set(key, layoutDiagram(source, connections, groups));
  }
  return layouts.get(key);
}

/**
 * The blueprint, drawn natively in the app's own palette: rounded component
 * cards marked by status, wires with pill labels, dashed boundaries. Existing
 * Mermaid reports need no regeneration. It uses the UI font, like the rest of the page.
 */
export function diagramView(source, t, { width = 700, zoom = 1, components = [], connections = [], groups = [], selectedId = null, onSelect = null } = {}) {
  let graph;
  try { graph = cachedLayout(source, connections, groups); }
  catch (e) { return div().p(16).text_color(t.blocked).child(`Couldn't render architecture: ${e.message}`); }
  const focus = diagramFocus(graph, selectedId);
  const header = 8;
  const scale = Math.min(1, Math.max(240, width) / graph.width) * zoom;
  const w = Math.max(graph.width * scale, width), footer = w < 420 ? 52 : 36;
  const offsetX = (w - graph.width * scale) / 2;
  const h = graph.height * scale + header + footer;
  const paper = t.background ?? t.surface;
  const ink = t.foreground;
  const grid = mix(paper, ink, 0.05);
  const line = mix(paper, ink, 0.45), muted = mix(paper, ink, 0.6);
  const card = mix(paper, t.raised ?? paper, 0.9);
  const root = div().relative().flex_none().w(w).h(h).bg(paper).rounded(10).overflow_hidden();
  const point = ([x, y]) => /** @type {[number, number]} */ ([x * scale + offsetX, y * scale + header]);
  const paint = (path, color, opacity = 1, id = null) => {
    const drawing = window.paint_path(path.build(), color).absolute().top(0).left(0).size_full().opacity(opacity);
    if (id) drawing.id(id);
    root.child(drawing);
  };

  // A faint dot grid: small crosses every 24px, batched into one path so zooming stays cheap.
  const dots = PathBuilder.stroke(1);
  const spacing = Math.max(16, 24 * scale);
  for (let x = spacing / 2; x <= w; x += spacing) {
    for (let y = header + spacing / 2; y <= h - footer; y += spacing) dots.move_to(x - 0.75, y).line_to(x + 0.75, y);
  }
  paint(dots, grid);

  // Boundaries are behind relationships and cards. Headers occupy reserved
  // lane space, so labels and components cannot cover them.
  for (const group of graph.groups) {
    const selected = group.nodes.includes(selectedId);
    const edge = group.missing ? t.blocked : selected ? t.accent : mix(paper, ink, 0.25);
    root.child(div().id(`diagram-group-${group.id}`).opacity(focus.groups.has(group.id) ? 1 : 0.25).absolute()
      .left(group.x * scale + offsetX).top(group.y * scale + header)
      .w(group.width * scale).h(group.height * scale).rounded(14 * scale).border_1().border_dashed()
      .border_color(edge).bg(mix(paper, selected ? t.accent : ink, 0.025))
      // The layout keeps 40px above a lane's first card: two lines of title (6 + 2 + 2 × 13.5 + 2) fit in it.
      .child(div().id(`diagram-group-title-${group.id}`).absolute().left(12 * scale).top(6 * scale)
        .max_w(Math.min(220, group.width - 24) * scale).px(8 * scale).py(1 * scale).rounded(9 * scale).bg(mix(paper, edge, 0.15))
        .text_size(10.5 * scale).line_height(1.28).font_semibold().text_color(group.missing ? t.blocked : selected ? t.accent : muted)
        .tooltip(`${group.title}${group.reason ? ": " + group.reason : ""}${group.missing ? " (saved boundary; source changed)" : ""}`)
        .children(group.titleLines.map((text) => div().child(text)))));
  }

  for (const [index, edge] of graph.edges.entries()) {
    const related = focus.edges.has(index), opacity = related ? 1 : 0.18;
    const color = !related ? mix(paper, line, 0.18) : focus.active ? t.accent : line;
    const points = edge.points.map(point), arrow = edge.arrow.map(point);
    const path = PathBuilder.stroke(related && focus.active ? 1.8 : 1.4).move_to(...points[0]);
    for (const p of points.slice(1)) path.line_to(...p);
    paint(path, color, opacity, `diagram-edge-${index}`);
    paint(PathBuilder.fill().add_polygon(arrow, true), color, opacity);
  }

  // Labels after wires, before cards: a pill on the paper, so the wire under it doesn't show through.
  for (const [i, edge] of graph.edges.entries()) {
    const box = edge.labelBox;
    if (!box) continue;
    const related = focus.edges.has(i), opacity = related ? 1 : 0.22;
    const [ax, ay] = point(box.anchor);
    const x = box.x * scale + offsetX, y = box.y * scale + header;
    const right = x + box.width * scale, bottom = y + box.height * scale;
    const nearestX = Math.max(x, Math.min(right, ax)), nearestY = Math.max(y, Math.min(bottom, ay));
    const accent = focus.active && related;
    if (box.detached) {
      root.child(div().opacity(opacity).absolute().left(ax - 8 * scale).top(ay - 8 * scale).size(16 * scale).rounded_full()
        .bg(accent ? t.accent : card).border_1().border_color(accent ? t.accent : line).text_color(accent ? "#ffffff" : ink).text_size(9 * scale).font_semibold()
        .flex().items_center().justify_center().tooltip(edge.label).child(String(box.number)));
    } else if (ax !== nearestX || ay !== nearestY) {
      paint(PathBuilder.stroke(0.8).move_to(ax, ay).line_to(nearestX, ay).line_to(nearestX, nearestY), related ? line : mix(paper, line, 0.22), opacity);
    }
    root.child(div().id(`diagram-edge-label-${i}`).opacity(opacity).absolute().left(x).top(y)
      .w(box.width * scale).h(box.height * scale).rounded(Math.min(box.height * scale / 2, 10 * scale)).bg(accent ? mix(paper, t.accent, 0.2) : card)
      .border_1().border_color(accent ? t.accent : mix(paper, ink, 0.18))
      .text_color(edge.missing ? t.blocked : accent ? t.accent : muted).text_size(10.5 * scale).line_height(1.35).font_medium()
      .flex().flex_col().items_center().justify_center().text_center()
      .tooltip(`${edge.from} → ${edge.to}: ${edge.label}${edge.missing ? " (saved label; source changed, regenerate to update)" : ""}`)
      .children(box.lines.map((text) => div().child(text))));
  }

  const metadata = new Map(components.map((c) => [c.id, c]));
  for (const [i, node] of graph.nodes.entries()) {
    const component = metadata.get(node.id);
    const status = component?.status;
    const color = { added: t.ansi2, modified: t.ansi3, context: muted }[status] ?? line;
    const selected = selectedId === node.id;
    const related = focus.nodes.has(node.id);
    const lit = selected || (focus.active && related);
    root.child(div().id(`diagram-node-${node.id}`).opacity(related ? 1 : 0.25).absolute().left(node.x * scale + offsetX).top(node.y * scale + header)
      .w(node.width * scale).h(node.height * scale).rounded(12 * scale).border_1().border_color(lit ? t.accent : status ? color + "88" : mix(paper, ink, 0.2))
      .bg(selected ? mix(card, t.accent, 0.14) : card).when(selected, (el) => el.shadow_md())
      .text_color(status === "context" && !lit ? muted : t.foreground).flex().flex_col().overflow_hidden()
      .tooltip(`${node.label}${status ? " / " + status : ""}: select for details`)
      .when(Boolean(onSelect), (el) => el.cursor_pointer().hover((s) => s.border_color(t.accent))
        .on_mouse_down("left", (_e, cx) => cx.stop_propagation())
        .on_click((_e, cx) => onSelect(node.id, cx)))
      // A coloured strip says the status at a glance; the pill names it.
      .child(div().flex_none().h(3 * scale).w_full().bg(status && status !== "context" ? color : "#00000000"))
      .child(h_flex().flex_none().h(24 * scale).px(10 * scale).items_center().justify_between().text_size(9.5 * scale)
        .child(div().text_color(mix(paper, ink, 0.4)).child(String(i + 1).padStart(2, "0")))
        .when(Boolean(status), (el) => el.child(div().px(6 * scale).h(16 * scale).flex().items_center().rounded_full().bg(color + "24").text_color(color).font_semibold().child(status.toUpperCase()))))
      .child(div().flex_1().min_h(0).px(10 * scale).pb(6 * scale).flex().flex_col().items_center().justify_center()
        .text_center().text_size(12.5 * scale).line_height(1.35).font_medium()
        .children(node.lines.map((text) => div().child(text)))));
  }
  root.child(h_flex().absolute().top(h - footer).left(14).right(14).h(footer).items_center().justify_between()
    .text_size(10.5).text_color(muted)
    .when(w < 420, (el) => el.flex_col().items_start().justify_center().gap(4))
    .child(`${graph.nodes.length} component${graph.nodes.length === 1 ? "" : "s"} · ${graph.edges.length} connection${graph.edges.length === 1 ? "" : "s"}${graph.groups.length ? ` · ${graph.groups.length} group${graph.groups.length === 1 ? "" : "s"}` : ""}`)
    .child(graph.direction === "LR" ? "Flows left to right" : "Flows top to bottom"));
  return root;
}
