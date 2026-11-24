// A printable A4 sheet of 3x3 puzzles plus a solutions page, as a hand-written PDF (ASCII only, built-in Helvetica).
const f = (n) => n.toFixed(2);
const esc = (s) => s.replace(/[\\()]/g, (m) => "\\" + m);
const text = (x, y, size, s, bold) => `BT /${bold ? "F2" : "F1"} ${f(size)} Tf ${f(x)} ${f(y)} Td (${esc(s)}) Tj ET\n`;

const SHADE = 0.86, BOLD = 1.8;

// x, y: the grid's bottom-left corner. Boxes shaded like a checkerboard (corners and centre dark);
// box lines as thick as the border. Givens bold black; filled answers regular grey.
function grid(x, y, size, puz, sol) {
  const c = size / 9, b = size / 3, fs = c * 0.6;
  let s = `${SHADE} g\n`;
  for (let k = 0; k < 9; k += 2) s += `${f(x + (k % 3) * b)} ${f(y + size - (((k / 3) | 0) + 1) * b)} ${f(b)} ${f(b)} re f\n`;
  s += "0 g\n";
  for (let k = 0; k <= 9; k++) {
    s += `${k % 3 ? 0.5 : BOLD} w ${f(x + k * c)} ${f(y)} m ${f(x + k * c)} ${f(y + size)} l S `;
    s += `${f(x)} ${f(y + k * c)} m ${f(x + size)} ${f(y + k * c)} l S\n`;
  }
  for (let i = 0; i < 81; i++) {
    const v = puz[i] || (sol && sol[i]);
    if (!v) continue;
    const r = (i / 9) | 0, col = i % 9;
    s += (puz[i] ? "0 g " : "0.35 g ") + text(x + col * c + (c - 0.556 * fs) / 2, y + size - (r + 1) * c + (c - 0.716 * fs) / 2, fs, String(v), !!puz[i]);
  }
  return s + "0 g\n";
}

// Difficulty as five rising bars; x, y: bottom-left. The same icon as guide.js bars(), drawn with PDF
// operators. Black: the puzzle's level now. Grey: the level extra hints took away (up to `was`). Outline: above.
function bars(x, y, rank, was = rank) {
  let s = "";
  for (let k = 1; k <= 5; k++) {
    const box = `${f(x + (k - 1) * 4.4)} ${f(y)} 3.2 ${f(3 + k * 2)} re`;
    s += k <= rank ? `0 g ${box} f\n` : k <= was ? `0.72 g ${box} f 0 g\n` : `0.55 G 0.5 w ${box} S 0 G\n`;
  }
  return s;
}

// "Given digits changed": a cell with a filled centre, then the signed count (+15 added, -5 hidden).
const badge = (x, y, delta) => `0.6 w ${f(x)} ${f(y)} 8 8 re S ${f(x + 2.5)} ${f(y + 2.5)} 3 3 re f\n` +
  text(x + 11, y + 0.5, 9, `${delta > 0 ? "+" : "-"}${Math.abs(delta)}`, false);

// A drawn check mark marks the solutions page, so the sheet needs no words beyond the puzzle's name.
const check = (x, y) => `2.4 w 1 J 1 j ${f(x)} ${f(y + 6)} m ${f(x + 5)} ${f(y + 1)} l ${f(x + 15)} ${f(y + 14)} l S 2 J 0 j\n`;

// The label is the person's own text (Czech, German, ...). The PDF's built-in Helvetica has these letters but no
// encoding reaches them, so font F3 names each one in a /Differences table at codes 128 and up; the file stays ASCII.
// Letters outside this table print as "?".
const GLYPH = Object.fromEntries(("á aacute Á Aacute ä adieresis Ä Adieresis à agrave ą aogonek č ccaron Č Ccaron " +
  "ć cacute ç ccedilla ď dcaron Ď Dcaron é eacute É Eacute ě ecaron Ě Ecaron è egrave ę eogonek í iacute Í Iacute " +
  "ĺ lacute Ĺ Lacute ľ lcaron Ľ Lcaron ł lslash Ł Lslash ň ncaron Ň Ncaron ń nacute ñ ntilde ó oacute Ó Oacute " +
  "ô ocircumflex Ô Ocircumflex ö odieresis Ö Odieresis ő ohungarumlaut ř rcaron Ř Rcaron ŕ racute Ŕ Racute " +
  "š scaron Š Scaron ś sacute ť tcaron Ť Tcaron ú uacute Ú Uacute ů uring Ů Uring ü udieresis Ü Udieresis " +
  "ű uhungarumlaut ý yacute Ý Yacute ž zcaron Ž Zcaron ź zacute ż zdotaccent ß germandbls – endash — emdash " +
  "’ quoteright ‘ quoteleft “ quotedblleft ” quotedblright … ellipsis").match(/\S+ \S+/g).map((p) => p.split(" ")));
function encodeLabel(label) {
  const names = [];
  let s = "";
  for (const ch of [...label].slice(0, 45)) {
    if (ch >= " " && ch <= "~") s += esc(ch);
    else if (GLYPH[ch]) {
      let k = names.indexOf(GLYPH[ch]);
      if (k < 0) k = names.push(GLYPH[ch]) - 1;
      s += "\\" + (128 + k).toString(8);
    } else s += "?";
  }
  return { s, names };
}

// rows: [{ rank, games: [{ puz, sol, rank?, delta? }, x3] }, x3]: the row's chosen level; each puzzle's
// level after hints were added or hidden, and how many. label: optional, printed after "Sudoku" (max 45 letters).
// Returns the puzzle page and the solutions page, plus .names: the label's extra letters for pdf().
export function sheetPages(rows, date, label = "") {
  const size = 165, gap = 25, x0 = (595 - 3 * size - 2 * gap) / 2, lab = encodeLabel(label.trim());
  const page = (withSol) => {
    // date: the sheet's id as printed ("2026-11-17 10:45"), right-aligned (Helvetica digits are 0.556 em wide).
    let s = "2 J 0 G 0 g\n" + text(x0, 800, 18, "Sudoku", true) + text(x0 + 3 * size + 2 * gap - 0.556 * 9 * date.length, 803, 9, date, false);
    if (withSol) s += check(x0 + 86, 800);
    if (lab.s) s += `BT /F3 14 Tf ${f(x0 + (withSol ? 112 : 86))} 800 Td (${lab.s}) Tj ET\n`;
    rows.forEach((row, r) => {
      const top = 772 - r * 228;
      row.games.forEach((g, c) => {
        const x = x0 + c * (size + gap);
        s += text(x, top - 12, 9, String(r * 3 + c + 1), false) + bars(x + 14, top - 12, g.rank ?? row.rank, row.rank);
        if (g.delta) s += badge(x + 14 + 5 * 4.4 + 8, top - 12, g.delta);
        s += grid(x, top - 20 - size, size, g.puz, withSol && g.sol);
      });
    });
    return s;
  };
  return Object.assign([page(false), page(true)], { names: lab.names });
}
export const sheetPdf = (rows, date, label) => { const p = sheetPages(rows, date, label); return pdf(p, p.names); };

// names: glyphs for codes 128 and up in font F3 (the label's letters outside ASCII).
export function pdf(pages, names = []) {
  const diffs = names.length ? ` /Differences [128 ${names.map((n) => `/${n}`).join(" ")}]` : "";
  const objs = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    `<< /Type /Pages /Kids [${pages.map((_, i) => `${6 + 2 * i} 0 R`).join(" ")}] /Count ${pages.length} >>`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    `<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding << /Type /Encoding /BaseEncoding /WinAnsiEncoding${diffs} >> >>`,
  ];
  for (const [i, c] of pages.entries()) objs.push(
    `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >> /Contents ${7 + 2 * i} 0 R >>`,
    `<< /Length ${c.length} >>\nstream\n${c}\nendstream`);
  let out = "%PDF-1.4\n";
  const at = objs.map((o, i) => { const pos = out.length; out += `${i + 1} 0 obj\n${o}\nendobj\n`; return pos; });
  const xref = out.length;
  out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n` + at.map((p) => `${String(p).padStart(10, "0")} 00000 n \n`).join("");
  return out + `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
}
