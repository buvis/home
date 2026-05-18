import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))
from _lib_cartographer import project_hash, try_import_tree_sitter, append_audit

_FILE_CAP = 50


def _get_head_sha(repo_path: Path) -> Optional[str]:
    r = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path, capture_output=True, text=True,
    )
    return r.stdout.strip() if r.returncode == 0 else None


def _scan_layers(repo_path: Path) -> tuple[dict[str, list[Path]], bool]:
    top_dirs = [
        p for p in repo_path.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    ]
    truncated = False
    layers: dict[str, list[Path]] = {}

    if not top_dirs:
        files = [f for f in repo_path.iterdir() if f.is_file() and not f.name.startswith(".")]
        if len(files) > _FILE_CAP:
            truncated = True
            files = files[:_FILE_CAP]
        layers["root"] = files
        return layers, truncated

    for d in top_dirs:
        all_files = [f for f in d.rglob("*") if f.is_file()]
        if len(all_files) > _FILE_CAP:
            truncated = True
            all_files = all_files[:_FILE_CAP]
        layers[d.name] = all_files

    return layers, truncated


def _classify_name(name: str) -> str:
    if re.match(r"^[A-Z][a-zA-Z0-9]*$", name):
        return "PascalCase"
    if re.match(r"^[a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*$", name):
        return "camelCase"
    if re.match(r"^[a-z][a-z0-9_]*$", name):
        return "snake_case"
    return "other"


_TS_LANG_BY_EXT = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".rs": "rust",
    ".go": "go",
}

# StructureItem.kind (str) -> pinned kind enum.
_TS_KIND_MAP = {
    "Class": "class",
    "Function": "function",
    "Method": "method",
    "Interface": "interface",
    "Trait": "interface",
    "Struct": "type",
    "Enum": "type",
}

# StructureItem.kind values whose body holds methods rather than functions.
_TS_CLASS_KINDS = {"Class", "Struct", "Trait", "Impl"}


def _ts_walk(items, in_class: bool, results: list[tuple[str, str, int]]) -> None:
    for item in items:
        raw_kind = str(item.kind)
        kind = _TS_KIND_MAP.get(raw_kind)
        if kind is not None and item.name:
            if kind == "function" and in_class:
                kind = "method"
            results.append((item.name, kind, item.span.start_line + 1))
        child_in_class = in_class or raw_kind in _TS_CLASS_KINDS
        _ts_walk(item.children, child_in_class, results)


def _extract_tree_sitter(f: Path, ts_module) -> list[tuple[str, str, int]]:
    lang = _TS_LANG_BY_EXT.get(f.suffix)
    if lang is None:
        return []
    try:
        source = f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    try:
        result = ts_module.process(
            source, ts_module.ProcessConfig(language=lang, structure=True)
        )
        results: list[tuple[str, str, int]] = []
        _ts_walk(result.structure, False, results)
        return results
    except Exception:
        return []


def _extract_file_symbols(f: Path) -> list[tuple[str, str, int]]:
    ts_module = try_import_tree_sitter()
    if ts_module is None:
        return _extract_file_symbols_regex(f)
    results = _extract_tree_sitter(f, ts_module)
    if f.suffix == ".go":
        # tree_sitter_language_pack 1.8.0 yields no structure items for Go
        # `type X struct` / `type X interface`; merge them in from the regex
        # extractor so Go types are not dropped from the atlas.
        seen = set(results)
        for sym in _extract_file_symbols_regex(f):
            if sym[1] in ("class", "interface") and sym not in seen:
                results.append(sym)
                seen.add(sym)
    return results


def _extract_file_symbols_regex(f: Path) -> list[tuple[str, str, int]]:
    results = []
    try:
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return results
    ext = f.suffix
    for i, line in enumerate(lines, 1):
        if ext == ".py":
            m = re.match(r"^(?:def|class)\s+(\w+)", line)
            if m:
                kind = "class" if line.lstrip().startswith("class") else "function"
                results.append((m.group(1), kind, i))
        elif ext in (".ts", ".tsx", ".js", ".jsx"):
            m = re.match(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)", line)
            if m:
                results.append((m.group(1), "function", i))
            m = re.match(r"^\s*(?:export\s+)?class\s+(\w+)", line)
            if m:
                results.append((m.group(1), "class", i))
            m = re.match(r"^\s*(?:export\s+)?interface\s+(\w+)", line)
            if m:
                results.append((m.group(1), "interface", i))
        elif ext == ".rs":
            m = re.match(r"^\s*(?:pub\s+)?fn\s+(\w+)", line)
            if m:
                results.append((m.group(1), "function", i))
            m = re.match(r"^\s*(?:pub\s+)?struct\s+(\w+)", line)
            if m:
                results.append((m.group(1), "class", i))
            m = re.match(r"^\s*(?:pub\s+)?trait\s+(\w+)", line)
            if m:
                results.append((m.group(1), "interface", i))
        elif ext == ".go":
            m = re.match(r"^\s*func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)", line)
            if m:
                results.append((m.group(1), "function", i))
            m = re.match(r"^\s*type\s+(\w+)\s+(?:struct|interface)", line)
            if m:
                kind = "interface" if "interface" in line else "class"
                results.append((m.group(1), kind, i))
    return results


def _naming_counts(symbols: list[tuple[str, str, int]]) -> dict[str, int]:
    counts: dict[str, int] = {"camelCase": 0, "snake_case": 0, "PascalCase": 0}
    for name, _, _ in symbols:
        c = _classify_name(name)
        if c in counts:
            counts[c] += 1
    return counts


def _compute_error_style(layers: dict[str, list[Path]]) -> str:
    sample: list[Path] = []
    for files in layers.values():
        sample.extend(files)
        if len(sample) >= 50:
            sample = sample[:50]
            break

    result_count = 0
    exception_count = 0
    for f in sample:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        ext = f.suffix
        if ext == ".rs":
            result_count += len(re.findall(r"Result<", text))
            exception_count += len(re.findall(r"panic!", text))
        elif ext in (".ts", ".tsx", ".js", ".jsx"):
            exception_count += len(re.findall(r"\bthrow\b", text))
        elif ext == ".py":
            exception_count += len(re.findall(r"\braise\b", text))
            exception_count += len(re.findall(r"\btry\b", text))

    total = result_count + exception_count
    if total == 0:
        return "unknown"
    if result_count == 0:
        return "exceptions"
    if exception_count == 0:
        return "result"
    dominant = result_count / total
    if dominant >= 0.7:
        return "result"
    if (1 - dominant) >= 0.7:
        return "exceptions"
    return "mixed"


def _compute_dep_edges(layers: dict[str, list[Path]]) -> list[dict]:
    layer_names = set(layers.keys())
    counts: dict[tuple[str, str], int] = {}
    for from_layer, files in layers.items():
        for f in files:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for name in layer_names:
                if name == from_layer:
                    continue
                if re.search(rf"\b{re.escape(name)}\b", text):
                    key = (from_layer, name)
                    counts[key] = counts.get(key, 0) + 1
    return [{"from_layer": f, "to_layer": t, "count": c} for (f, t), c in counts.items()]


def _default_forbidden(layers: dict[str, list[Path]]) -> list[dict]:
    if "ui" in layers and "db" in layers:
        return [{"from": "ui", "to": "db", "reason": "ui must not import db directly"}]
    return []


def _build_atlas_md(atlas: dict, file_syms_by_layer: dict[str, list[tuple[str, str, str, int]]]) -> str:
    layers = atlas.get("layers", {})
    naming = atlas.get("naming", {})
    error_style = atlas.get("error_style", "unknown")

    lines: list[str] = []

    lines.append("## Where things live")
    lines.append("")
    for layer_name, files in layers.items():
        lines.append(f"- **{layer_name}**: {len(files)} files")
    lines.append("")

    lines.append("## Naming conventions")
    lines.append("")
    for layer_name, counts in naming.items():
        dominant = max(counts, key=lambda k: counts[k])
        lines.append(
            f"- **{layer_name}**: {dominant} "
            f"(camelCase={counts['camelCase']}, snake_case={counts['snake_case']}, PascalCase={counts['PascalCase']})"
        )
    lines.append("")

    lines.append("## Error-handling style")
    lines.append("")
    lines.append(f"Detected style: **{error_style}**")
    lines.append("")

    lines.append("## Existing implementations index")
    lines.append("")
    count = 0
    for syms in file_syms_by_layer.values():
        for rel_path, name, kind, lineno in syms:
            if count >= 20:
                break
            lines.append(f"- `{name}` ({kind}) - {rel_path}:{lineno}")
            count += 1
        if count >= 20:
            break
    if count == 0:
        lines.append("_(no symbols found)_")
    lines.append("")

    lines.append("## Extension points")
    lines.append("")
    ext_count = 0
    for syms in file_syms_by_layer.values():
        for rel_path, name, kind, lineno in syms:
            if kind in ("interface", "class") and ext_count < 10:
                lines.append(f"- `{name}` ({kind}) - {rel_path}:{lineno}")
                ext_count += 1
    if ext_count == 0:
        lines.append("_(no interfaces or abstract bases found)_")
    lines.append("")

    return "\n".join(lines)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".tmp.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _fit_to_budget(content: str) -> tuple[str, bool]:
    budget = 5120
    footer = "\n*atlas truncated*"
    if len(content.encode()) <= budget:
        return content, False
    max_bytes = budget - len(footer.encode())
    truncated_text = content.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
    return truncated_text + footer, True


def _do_survey(repo_path: Path, atlas_dir: Path, prior_manual: object) -> None:
    degraded = try_import_tree_sitter() is None
    layers, truncated = _scan_layers(repo_path)

    symbols_by_layer: dict[str, list[tuple[str, str, int]]] = {}
    file_syms_by_layer: dict[str, list[tuple[str, str, str, int]]] = {}
    for layer_name, files in layers.items():
        syms: list[tuple[str, str, int]] = []
        file_syms: list[tuple[str, str, str, int]] = []
        for f in files:
            extracted = _extract_file_symbols(f)
            syms.extend(extracted)
            rel_path = str(f.relative_to(repo_path))
            for name, kind, lineno in extracted:
                file_syms.append((rel_path, name, kind, lineno))
        symbols_by_layer[layer_name] = syms
        file_syms_by_layer[layer_name] = file_syms

    naming: dict[str, dict[str, int]] = {k: _naming_counts(v) for k, v in symbols_by_layer.items()}
    error_style = _compute_error_style(layers)
    forbidden_imports = _default_forbidden(layers)
    dependency_edges = _compute_dep_edges(layers)

    layers_out: dict[str, list[str]] = {k: [str(f) for f in v] for k, v in layers.items()}

    atlas: dict = {
        "surveyed_at": datetime.now(timezone.utc).isoformat(),
        "layers": layers_out,
        "forbidden_imports": forbidden_imports,
        "naming": naming,
        "error_style": error_style,
        "dependency_edges": dependency_edges,
        "degraded": degraded,
    }

    head_sha = _get_head_sha(repo_path)
    if head_sha:
        atlas["head_sha"] = head_sha

    if truncated:
        atlas["truncated"] = True

    if prior_manual is not None:
        atlas["[manual]"] = prior_manual

    md_content = _build_atlas_md(atlas, file_syms_by_layer)
    md_content, md_truncated = _fit_to_budget(md_content)
    if md_truncated:
        atlas["truncated"] = True
    # If truncated (file cap or md budget), ensure footer visible in md
    if atlas.get("truncated") and "*atlas truncated*" not in md_content:
        footer = "\n*atlas truncated*"
        budget = 5120
        if len((md_content + footer).encode()) <= budget:
            md_content = md_content + footer
        else:
            max_bytes = budget - len(footer.encode())
            md_content = md_content.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore") + footer

    atlas_path = atlas_dir / "atlas.json"
    md_path = atlas_dir / "atlas.md"

    _atomic_write(atlas_path, json.dumps(atlas, indent=2))
    _atomic_write(md_path, md_content)

    size = atlas_path.stat().st_size
    print(f"surveyed: {repo_path} ({size} bytes)")

    flag = atlas_dir / "staleness.flag"
    if flag.exists():
        flag.unlink()

    append_audit({"event": "survey", "path": str(repo_path)})


def main(_args: argparse.Namespace | None = None, _home: Path | None = None) -> None:
    if _args is None:
        parser = argparse.ArgumentParser()
        parser.add_argument("--refresh", action="store_true")
        parser.add_argument("--if-missing", action="store_true", dest="if_missing")
        _args = parser.parse_args()

    home = _home if _home is not None else Path.home()
    repo_path = Path.cwd()

    h, _, _ = project_hash(str(repo_path))
    atlas_dir = home / ".claude" / "cartographer" / "projects" / h
    atlas_path = atlas_dir / "atlas.json"
    flag_path = atlas_dir / "staleness.flag"

    if _args.if_missing and atlas_path.exists() and not flag_path.exists():
        print(f"skipped: atlas already exists at {atlas_path}")
        return

    prior_manual = None
    if atlas_path.exists():
        try:
            prior_data = json.loads(atlas_path.read_text(encoding="utf-8"))
            prior_manual = prior_data.get("[manual]")
        except (json.JSONDecodeError, OSError):
            pass

    _do_survey(repo_path, atlas_dir, prior_manual)


if __name__ == "__main__":
    main()
