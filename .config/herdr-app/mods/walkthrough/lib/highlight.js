// Light syntax colouring for one line of a diff. A hunk is read line by line,
// without the lines around it, so this never parses: it finds comments,
// strings, numbers, keywords, calls and type-like names, and leaves the rest
// plain. Wrong guesses cost colour, never text: the tokens always join back
// into the line exactly.

const HASH_COMMENTS = new Set(["py", "rb", "sh", "bash", "zsh", "fish", "yml", "yaml", "toml", "r", "pl", "ex", "exs", "nix", "dockerfile", "makefile", "cmake", "conf", "ini"]);
const PLAIN = new Set(["md", "markdown", "txt", "rst", "json", "lock", "csv", "svg", "xml", "html", "htm"]);

const KEYWORDS = new Set([
  // JavaScript and TypeScript
  "async", "await", "break", "case", "catch", "class", "const", "continue", "debugger", "default", "delete", "do", "else", "export",
  "extends", "finally", "for", "from", "function", "if", "import", "in", "instanceof", "let", "new", "of", "return", "static", "super",
  "switch", "this", "throw", "try", "typeof", "var", "void", "while", "with", "yield", "interface", "type", "enum", "implements",
  "private", "protected", "public", "readonly", "abstract", "as", "declare", "namespace", "keyof",
  // Python, Ruby, shell
  "def", "elif", "except", "lambda", "pass", "raise", "global", "nonlocal", "assert", "and", "or", "not", "is", "end", "then",
  "fi", "done", "esac", "elsif", "unless", "until", "module", "self", "local",
  // Go, Rust, Swift, Kotlin, Java, C
  "func", "go", "chan", "defer", "select", "struct", "package", "range", "map", "fn", "impl", "trait", "mut", "pub", "use", "mod",
  "match", "loop", "where", "crate", "ref", "move", "dyn", "unsafe", "val", "fun", "object", "when", "override", "final", "throws",
  "int", "char", "long", "short", "double", "float", "bool", "unsigned", "sizeof", "typedef", "goto", "register", "guard", "init",
  "extension", "protocol",
]);
const CONSTANTS = new Set(["true", "false", "null", "undefined", "nil", "None", "True", "False", "NaN", "Infinity"]);

/** The file's extension, or a well-known file name, in lower case. */
function kindOf(path) {
  const name = String(path ?? "").split("/").pop().toLowerCase();
  if (name === "dockerfile" || name === "makefile") return name;
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(dot + 1) : "";
}

/**
 * @param {string} text one line of code
 * @param {string} path the file it is in, for its comment style
 * @returns {{ text: string, kind: "plain" | "keyword" | "string" | "number" | "comment" | "function" | "type" | "constant" }[]}
 */
export function tokenize(text, path = "") {
  const kind = kindOf(path);
  if (!text || PLAIN.has(kind)) return text ? [{ text, kind: "plain" }] : [];
  const hash = HASH_COMMENTS.has(kind);
  const out = [];
  const push = (t, k) => {
    if (!t) return;
    const prev = out[out.length - 1];
    if (prev && prev.kind === k) prev.text += t;
    else out.push({ text: t, kind: k });
  };
  let i = 0;
  while (i < text.length) {
    const c = text[i], rest = text.slice(i);
    if ((!hash && rest.startsWith("//")) || (hash && c === "#") || rest.startsWith("/*") || (kind === "sql" && rest.startsWith("--"))) {
      // A block comment ends on this line or runs to its end.
      const close = rest.startsWith("/*") ? rest.indexOf("*/", 2) : -1;
      const len = close >= 0 ? close + 2 : rest.length;
      push(rest.slice(0, len), "comment");
      i += len;
    } else if (c === '"' || c === "'" || c === "`") {
      let j = i + 1;
      while (j < text.length && text[j] !== c) j += text[j] === "\\" ? 2 : 1;
      const len = Math.min(text.length, j + 1) - i;
      push(text.slice(i, i + len), "string");
      i += len;
    } else if (/[0-9]/.test(c) && !/[\w$]/.test(text[i - 1] ?? "")) {
      const m = rest.match(/^(0[xob][0-9a-f_]+|[0-9][0-9_]*(\.[0-9_]+)?(e[+-]?[0-9]+)?)[a-z]*/i);
      push(m[0], "number");
      i += m[0].length;
    } else if (/[A-Za-z_$]/.test(c)) {
      const word = rest.match(/^[A-Za-z_$][\w$]*/)[0];
      const after = text.slice(i + word.length).trimStart()[0];
      push(word, KEYWORDS.has(word) ? "keyword" : CONSTANTS.has(word) ? "constant"
        : after === "(" ? "function" : /^[A-Z][a-z0-9]/.test(word) ? "type" : "plain");
      i += word.length;
    } else {
      push(c, "plain");
      i += 1;
    }
  }
  return out;
}
