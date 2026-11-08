// Fuzzy search for the navigator.
//
// A query follows fzf's extended-search syntax (fzf 0.73, see parseQuery):
// whitespace-separated terms that must all match, each in any one of an
// item's fields. A plain term matches as a subsequence; operators make a
// term exact, anchored, negated or one of several alternatives. A lowercase
// term ignores case; a term with an uppercase letter matches case exactly
// (smart case).
//
// Scoring follows fzf's shape: each matched character scores, characters at
// a word boundary or right after the previous match score extra, and gaps
// between matches cost. So "fl" ranks "fix-login" above "conflict".
//
// `tiered` orders by tier, not by score, and keeps the given order within
// each tier; the score only decides where highlights go (and how Clues
// ranks its rows, through `matchFields`).

const SCORE_MATCH = 16;
const BONUS_BOUNDARY = 10;
const BONUS_CAMEL = 8;
const BONUS_CONSECUTIVE = 8;
const BONUS_FIRST_MULTIPLIER = 2;
const PENALTY_GAP_START = 3;
const PENALTY_GAP_EXTEND = 1;
const SEPARATOR = /[\s\-_/\\.:·›|@()[\]{}"',;=+#~⎇]/u;
const LOWER = /\p{Ll}/u;
const UPPER = /\p{Lu}/u;
const SPACE = /\s/u;
const WORD = /[\p{L}\p{N}]/u;
const ESCAPED_SPACE = "\u0000";

function chars(text) {
  return Array.from(text ?? "");
}

function fold(cs, sensitive) {
  return sensitive ? cs : cs.map((c) => c.toLowerCase());
}

function caseSensitive(text) {
  return text !== text.toLowerCase();
}

function boundaryBonus(cs, i) {
  if (i === 0) return BONUS_BOUNDARY;
  const prev = cs[i - 1];
  if (SEPARATOR.test(prev)) return BONUS_BOUNDARY;
  if (LOWER.test(prev) && UPPER.test(cs[i])) return BONUS_CAMEL;
  return 0;
}

/** A run of `m` code points of `hay` from `s`, scored as fzf would. */
function run(hay, s, m) {
  let score = SCORE_MATCH * m + BONUS_CONSECUTIVE * (m - 1) + boundaryBonus(hay, s) * BONUS_FIRST_MULTIPLIER;
  for (let i = s + 1; i < s + m; i++) score += boundaryBonus(hay, i);
  return { score, indices: Array.from({ length: m }, (_, i) => s + i) };
}

/** Best fuzzy alignment of `needle` in `text`: `{ score, indices }`, or null. */
function align(text, needle, sensitive) {
  const hay = chars(text);
  const q = fold(chars(needle), sensitive);
  const n = hay.length;
  const m = q.length;
  if (m === 0) return { score: 0, indices: [] };
  if (m > n) return null;
  const h = fold(hay, sensitive);
  const bonus = hay.map((_, i) => boundaryBonus(hay, i));

  const NONE = -Infinity;
  const score = [];
  const from = [];
  for (let j = 0; j < m; j++) {
    const row = new Array(n).fill(NONE);
    const back = new Array(n).fill(-1);
    const prev = score[j - 1];
    // Best of prev[k] + EXTEND * k over k <= i - 2: a match with a gap.
    let pool = NONE;
    let poolAt = -1;
    for (let i = j; i < n; i++) {
      if (j > 0 && i >= 2) {
        const k = i - 2;
        const v = prev[k] + PENALTY_GAP_EXTEND * k;
        if (v > pool) { pool = v; poolAt = k; }
      }
      if (h[i] !== q[j]) continue;
      if (j === 0) {
        row[i] = SCORE_MATCH + bonus[i] * BONUS_FIRST_MULTIPLIER;
        continue;
      }
      let best = NONE;
      let bestAt = -1;
      if (prev[i - 1] > NONE) {
        best = prev[i - 1] + BONUS_CONSECUTIVE;
        bestAt = i - 1;
      }
      if (pool > NONE) {
        const gap = pool - PENALTY_GAP_START - PENALTY_GAP_EXTEND * (i - 2);
        if (gap > best) { best = gap; bestAt = poolAt; }
      }
      if (best === NONE) continue;
      row[i] = SCORE_MATCH + bonus[i] + best;
      back[i] = bestAt;
    }
    score.push(row);
    from.push(back);
  }

  const last = score[m - 1];
  let end = -1;
  for (let i = 0; i < n; i++) if (last[i] > NONE && (end < 0 || last[i] > last[end])) end = i;
  if (end < 0) return null;
  const indices = new Array(m);
  for (let j = m - 1, i = end; j >= 0; j--) {
    indices[j] = i;
    i = from[j][i];
  }
  return { score: last[end], indices };
}

/**
 * Best alignment of one term in one text: `{ score, indices }` with indices
 * in code points, or null when the term is not a subsequence of the text.
 */
export function matchTerm(text, term) {
  return align(text, term, caseSensitive(term));
}

/**
 * The best place in one text where `needle` appears unbroken (as one run of
 * consecutive characters): `{ score, indices }`, or null. Of several
 * occurrences, the one fzf would score highest wins, so a run at a word
 * start beats one inside a word. With `whole`, both ends of the run must
 * sit at a word boundary: the text's edge or a character that is neither a
 * letter nor a digit (so `_` is a boundary, as in fzf).
 */
function unbrokenIn(text, needle, sensitive, whole = false) {
  const hay = chars(text);
  const q = fold(chars(needle), sensitive);
  const m = q.length;
  if (m === 0 || m > hay.length) return null;
  const h = fold(hay, sensitive);
  let best = null;
  for (let s = 0; s + m <= h.length; s++) {
    let k = 0;
    while (k < m && h[s + k] === q[k]) k++;
    if (k < m) continue;
    if (whole && (WORD.test(hay[s - 1] ?? "") || WORD.test(hay[s + m] ?? ""))) continue;
    const r = run(hay, s, m);
    if (!best || r.score > best.score) best = r;
  }
  return best;
}

/** `needle` at the start of `text`; as in fzf, the text's leading whitespace doesn't count. */
function prefixOf(text, needle, sensitive) {
  const hay = chars(text);
  const q = fold(chars(needle), sensitive);
  let s = 0;
  if (!SPACE.test(q[0])) while (s < hay.length && SPACE.test(hay[s])) s++;
  if (hay.length - s < q.length) return null;
  const h = fold(hay.slice(s, s + q.length), sensitive);
  return h.every((c, i) => c === q[i]) ? run(hay, s, q.length) : null;
}

/** `needle` at the end of `text`; as in fzf, the text's trailing whitespace doesn't count. */
function suffixOf(text, needle, sensitive) {
  const hay = chars(text);
  const q = fold(chars(needle), sensitive);
  let e = hay.length;
  if (!SPACE.test(q[q.length - 1])) while (e > 0 && SPACE.test(hay[e - 1])) e--;
  const s = e - q.length;
  if (s < 0) return null;
  const h = fold(hay.slice(s, e), sensitive);
  return h.every((c, i) => c === q[i]) ? run(hay, s, q.length) : null;
}

/** `text` is `needle`, surrounding whitespace aside. */
function equalTo(text, needle, sensitive) {
  const p = prefixOf(text, needle, sensitive);
  const s = suffixOf(text, needle, sensitive);
  return p && s && p.indices[0] === s.indices[0] ? p : null;
}

/**
 * A query in fzf's extended-search syntax (fzf 0.73), parsed into groups
 * that must all match. Each term is `{ kind, text, inv, sensitive }`:
 *
 *   abc     "fuzzy"     the letters in order
 *   'abc    "exact"     abc unbroken
 *   'abc'   "boundary"  abc unbroken, both ends at word boundaries
 *   ^abc    "prefix"    a field starts with abc
 *   abc$    "suffix"    a field ends with abc
 *   ^abc$   "equal"     a field is abc
 *   !abc    inv "exact"   no field holds abc unbroken; `!^abc`, `!abc$`
 *                         and `!'abc'` negate those kinds, and `!'abc`
 *                         negates a fuzzy term, as in fzf
 *
 * A lone `|` between terms joins them into one group of alternatives; one
 * with no term before it is a term of its own, and one at the end drops
 * out. `\ ` is a space inside a term. A term with an uppercase letter
 * matches case exactly (smart case). Operators left with no text, such as
 * a lone `!`, drop out, so a query of only those matches everything.
 */
export function parseQuery(query) {
  const tokens = (query ?? "").replaceAll("\\ ", ESCAPED_SPACE).split(/\s+/u).filter(Boolean);
  const groups = [];
  let group = [];
  let afterBar = false;
  let open = false; // the next term starts a new group
  for (const token of tokens) {
    let text = token.replaceAll(ESCAPED_SPACE, " ");
    if (group.length > 0 && !afterBar && text === "|") {
      open = false;
      afterBar = true;
      continue;
    }
    afterBar = false;
    const sensitive = caseSensitive(text);
    let kind = "fuzzy";
    let inv = false;
    if (text.startsWith("!")) { inv = true; kind = "exact"; text = text.slice(1); }
    if (text !== "$" && text.endsWith("$")) { kind = "suffix"; text = text.slice(0, -1); }
    if (text.length > 2 && text.startsWith("'") && text.endsWith("'")) { kind = "boundary"; text = text.slice(1, -1); }
    else if (text.startsWith("'")) { kind = inv ? "fuzzy" : "exact"; text = text.slice(1); }
    else if (text.startsWith("^")) { kind = kind === "suffix" ? "equal" : "prefix"; text = text.slice(1); }
    if (!text) continue;
    if (open) {
      groups.push(group);
      group = [];
    }
    group.push({ kind, text, inv, sensitive });
    open = true;
  }
  if (group.length > 0) groups.push(group);
  return groups;
}

/**
 * How a match is placed, chosen by the caller:
 * - TIERED (typing in every list but Clues, ADR 0002) prefers an unbroken
 *   run: for a fuzzy term's highlight, among fields, and among an OR
 *   group's alternatives; the name (`title`) wins a tie between fields.
 * - RANKED (Clues and its buffer search) goes by score alone, as fzf does:
 *   a fuzzy term takes its best-scoring alignment, the first field wins a
 *   tie, and an OR group takes the first alternative that matched.
 */
const TIERED = { preferUnbroken: true, nameWinsTie: true };
const RANKED = { preferUnbroken: false, nameWinsTie: false };

/**
 * Where one term matches one text: `{ score, indices, unbroken }`, or null.
 * A fuzzy term is unbroken where it appears as one run, and under
 * `preferUnbroken` its highlight goes there; other kinds are unbroken by
 * definition.
 */
function matchIn(text, term, policy) {
  const { text: needle, sensitive } = term;
  let r;
  switch (term.kind) {
    case "fuzzy": {
      const exact = policy.preferUnbroken ? unbrokenIn(text, needle, sensitive) : null;
      if (exact) return { ...exact, unbroken: true };
      r = align(text, needle, sensitive);
      return r && { ...r, unbroken: false };
    }
    case "exact": r = unbrokenIn(text, needle, sensitive); break;
    case "boundary": r = unbrokenIn(text, needle, sensitive, true); break;
    case "prefix": r = prefixOf(text, needle, sensitive); break;
    case "suffix": r = suffixOf(text, needle, sensitive); break;
    case "equal": r = equalTo(text, needle, sensitive); break;
    default: r = null;
  }
  return r && { ...r, unbroken: true };
}

/**
 * Where one term lands among an item's fields: `{ key, indices, score,
 * unbroken }`, or null when it matches no field. Under `preferUnbroken` a
 * field where the term is unbroken beats any fuzzy alignment; then the
 * higher score wins, and a tie goes to the name under `nameWinsTie`, else
 * to the first field.
 */
function placeTerm(fields, term, policy) {
  let best = null;
  const better = (c) => {
    if (!best) return true;
    if (policy.preferUnbroken && c.unbroken !== best.unbroken) return c.unbroken;
    if (c.score !== best.score) return c.score > best.score;
    return policy.nameWinsTie && c.key === "title" && best.key !== "title";
  };
  for (const f of fields) {
    if (!f.text) continue;
    const r = matchIn(f.text, term, policy);
    if (!r) continue;
    const c = { key: f.key, indices: r.indices, score: r.score, unbroken: r.unbroken };
    if (better(c)) best = c;
  }
  return best;
}

/** A negated term's verdict: it holds, lighting nothing and leaving the tier alone. */
const ABSENT = { key: null, indices: [], score: 0, unbroken: true };

/**
 * How one group of alternatives lands, or null when none holds. The
 * alternative that matched decides: of several, the first (as in fzf), or
 * under `preferUnbroken` an unbroken one first. A group held only by a
 * negated term that appears nowhere lands ABSENT.
 */
function placeGroup(fields, group, policy) {
  let pick = null;
  let absent = false;
  for (const term of group) {
    const p = placeTerm(fields, term, policy);
    if (term.inv) {
      absent ||= !p;
      continue;
    }
    if (p && (!pick || (policy.preferUnbroken && p.unbroken && !pick.unbroken))) pick = p;
  }
  return pick ?? (absent ? ABSENT : null);
}

/**
 * Matches parsed groups against an item's fields under a policy (TIERED or
 * RANKED): `{ score, hits, unbroken, first }` (`first` is the indices of the first matched term, or null), or
 * null when some group fails. `unbroken` holds when every group landed
 * unbroken; negated terms don't count.
 */
function evaluate(fields, groups, policy) {
  const hits = {};
  let score = 0;
  let unbroken = true;
  let first = null;
  for (const group of groups) {
    const p = placeGroup(fields, group, policy);
    if (!p) return null;
    score += p.score;
    unbroken &&= p.unbroken;
    if (p.key === null) continue;
    first ??= p.indices;
    hits[p.key] = [...new Set([...(hits[p.key] ?? []), ...p.indices])].sort((a, b) => a - b);
  }
  return { score, hits, unbroken, first };
}

/**
 * A query parsed once for matchLiteralGroups, to read a line literally as
 * Clues reads a pane's buffer: a plain term must appear unbroken, as if
 * quoted, and the other operators work as anywhere else. `exactCase` makes
 * every positive term match case exactly; negated terms keep smart case.
 */
export function literalGroups(query, exactCase = false) {
  return parseQuery(query).map((group) => group.map((t) => ({
    ...t,
    kind: t.kind === "fuzzy" && !t.inv ? "exact" : t.kind,
    sensitive: (exactCase && !t.inv) || t.sensitive,
    folded: foldWhole(t.text),
  })));
}

/**
 * Text lowered in one native call, for substring checks. Whole-string
 * lowering differs from `fold`'s code point by code point only in Greek
 * final sigma (Σ lowers to ς at a word's end), so σ stands for ς on both
 * sides: whatever `fold` matches, this still contains.
 */
function foldWhole(text) {
  return text.toLowerCase().replaceAll("ς", "σ");
}

/**
 * False when `text` cannot hold the groups prepared by literalGroups: some
 * group of positive terms has none of them anywhere in it, checked by
 * native substring search. Every positive literal kind (exact, boundary,
 * prefix, suffix, equal) holds only where its text appears unbroken, so a
 * false here never drops a match; a group with a negated term can hold
 * through an absence, so it is not checked. `text` may be one line or a
 * whole buffer.
 *
 * A render must finish within Herdr's short time limit, and walking a
 * pane's buffer code point by code point exceeds it: this lets Clues skip a
 * buffer or a line natively.
 */
export function literalMayHold(text, literal) {
  let lowered = null;
  for (const group of literal) {
    if (group.some((t) => t.inv)) continue;
    const found = group.some((t) => (t.sensitive ? text.includes(t.text) : (lowered ??= foldWhole(text)).includes(t.folded)));
    if (!found) return false;
  }
  return true;
}

/**
 * Whether a line of text holds the groups prepared by literalGroups. Returns
 * the code-point indices of the first term that matched ([] when only
 * negated terms held), or null.
 */
export function matchLiteralGroups(text, literal) {
  if (literal.length === 0 || !literalMayHold(text, literal)) return null;
  const r = evaluate([{ key: "line", text }], literal, RANKED);
  return r && (r.first ?? []);
}

/**
 * Matches a query against an item's fields (`[{ key, text }]`).
 * Returns `{ score, hits }`, where `hits[key]` lists the matched code-point
 * indices of that field in ascending order, or null when the item doesn't
 * match. A fuzzy term lands where it scores best. An empty query matches
 * with score 0 and no hits.
 */
export function matchFields(fields, query) {
  const r = evaluate(fields, parseQuery(query), RANKED);
  return r && { score: r.score, hits: r.hits };
}

/**
 * Filters items by a query and sorts the matches into two tiers (ADR 0002):
 * items where every term appears unbroken in some field, then the rest.
 * Each tier keeps the items' given order; the fuzzy score only decides
 * where a term's highlight goes. Returns `[{ item, hits }]`.
 */
export function tiered(items, query, fieldsOf) {
  const groups = parseQuery(query);
  if (groups.length === 0) return items.map((item) => ({ item, hits: {} }));
  const upper = [];
  const lower = [];
  for (const item of items) {
    const r = evaluate(fieldsOf(item), groups, TIERED);
    if (r) (r.unbroken ? upper : lower).push({ item, hits: r.hits });
  }
  return [...upper, ...lower];
}

/**
 * Splits text into runs for drawing: `[{ text, hit }]`, where `hit` marks
 * the code points at `indices`. Adjacent code points of the same kind join.
 */
export function segments(text, indices) {
  const cs = chars(text);
  const marked = new Set(indices ?? []);
  const out = [];
  for (let i = 0; i < cs.length; i++) {
    const hit = marked.has(i);
    const tail = out[out.length - 1];
    if (tail && tail.hit === hit) tail.text += cs[i];
    else out.push({ text: cs[i], hit });
  }
  return out;
}
