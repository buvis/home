import argparse
import ast
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))
from _lib_cartographer import project_hash


_LAYER_MAP: dict[str, str] = {
    "api": "api", "cli": "cli", "hooks": "hooks", "lib": "lib",
    "libs": "lib", "tests": "tests", "scripts": "scripts",
    "skills": "skills", "config": "config",
}


def _detect_layers(repo_path: Path) -> list[dict]:
    subdirs = [p for p in repo_path.iterdir() if p.is_dir()]
    if not subdirs:
        files = [
            str(f) for f in repo_path.glob("**/*")
            if f.is_file() and "__pycache__" not in str(f) and ".git" not in str(f)
        ][:50]
        return [{"name": "root", "path": str(repo_path), "files": files}]

    layers = []
    for d in subdirs:
        files = [
            str(f) for f in d.glob("**/*")
            if f.is_file() and "__pycache__" not in str(f) and ".git" not in str(f)
        ][:50]
        layers.append({
            "name": _LAYER_MAP.get(d.name, "other"),
            "path": str(d),
            "files": files,
        })
    return layers


def _write_atlas_json(
    atlas_path: Path,
    layers: list,
    symbols: list,
    naming: dict,
    error_handling: dict,
    forbidden_imports: list,
    dependency_edges: list,
) -> None:
    h, _, _ = project_hash(str(atlas_path.parent))
    atlas: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_hash": h,
        "layers": layers,
        "symbols": symbols,
        "naming_conventions": naming,
        "error_handling": error_handling,
        "forbidden_imports": forbidden_imports,
        "dependency_edges": dependency_edges,
    }
    atlas_path.parent.mkdir(parents=True, exist_ok=True)
    atlas_path.write_text(json.dumps(atlas, indent=2))


def _extract_symbols(layers: list[dict]) -> list[dict]:
    _CAP = 500
    results: list[dict] = []
    for layer in layers:
        layer_name = layer["name"]
        for file_path in layer.get("files", []):
            if not file_path.endswith(".py"):
                continue
            try:
                source = Path(file_path).read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source, filename=file_path)
            except SyntaxError:
                continue
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef):
                    results.append({"file": file_path, "kind": "class", "name": node.name, "layer": layer_name})
                elif isinstance(node, ast.FunctionDef):
                    results.append({"file": file_path, "kind": "function", "name": node.name, "layer": layer_name})
                if len(results) >= _CAP:
                    return results
    return results


_NAMING_ORDER = ["snake_case", "CamelCase", "UPPER_SNAKE", "camelCase", "other"]
_NAMING_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("UPPER_SNAKE", re.compile(r"^[A-Z][A-Z0-9_]*$")),
    ("CamelCase",   re.compile(r"^[A-Z][a-zA-Z0-9]*$")),
    ("snake_case",  re.compile(r"^[a-z][a-z0-9_]*$")),
    ("camelCase",   re.compile(r"^[a-z][a-zA-Z0-9]*$")),
]


def _classify_name(name: str) -> str:
    for category, pattern in _NAMING_PATTERNS:
        if pattern.match(name):
            return category
    return "other"


def _compute_naming_conventions(symbols: list[dict]) -> dict:
    if not symbols:
        return {}

    layers: dict[str, dict[str, int]] = {}
    for sym in symbols:
        layer = sym["layer"]
        if layer not in layers:
            layers[layer] = {"snake_case": 0, "CamelCase": 0, "UPPER_SNAKE": 0, "camelCase": 0, "other": 0}
        layers[layer][_classify_name(sym["name"])] += 1

    result = {}
    for layer, counts in layers.items():
        dominant = max(_NAMING_ORDER, key=lambda c: (counts[c], -_NAMING_ORDER.index(c)))
        result[layer] = {**counts, "dominant": dominant}
    return result


def _detect_error_handling(layers: list[dict]) -> dict:
    if not layers:
        return {}

    result: dict[str, dict] = {}
    for layer in layers:
        name = layer["name"]
        try_except = 0
        raises = 0
        returns_none_on_error = 0

        for file_path in layer.get("files", []):
            if not file_path.endswith(".py"):
                continue
            try:
                source = Path(file_path).read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source, filename=file_path)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Try):
                    try_except += 1
                elif isinstance(node, ast.Raise):
                    raises += 1

            for func in ast.walk(tree):
                if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for node in ast.walk(func):
                    if not isinstance(node, ast.Try):
                        continue
                    for handler in node.handlers:
                        for stmt in ast.walk(handler):
                            if (
                                isinstance(stmt, ast.Return)
                                and (stmt.value is None or isinstance(stmt.value, ast.Constant) and stmt.value.value is None)
                            ):
                                returns_none_on_error += 1
                                break
                        else:
                            continue
                        break

        if try_except == 0 and raises == 0 and returns_none_on_error == 0:
            dominant_style = "unknown"
        elif (raises + try_except) > returns_none_on_error:
            dominant_style = "exceptions"
        else:
            dominant_style = "return_none"

        result[name] = {
            "try_except": try_except,
            "raises": raises,
            "returns_none_on_error": returns_none_on_error,
            "dominant_style": dominant_style,
        }

    return result


_ATLAS_MD_BUDGET = 5120


def _render_atlas_md(
    atlas: dict,
    symbol_cap: int,
    dependency_edges: list,
    forbidden_imports: list,
) -> str:
    lines: list[str] = []

    # 1. Title
    lines.append(f"# Atlas: {atlas.get('project_hash', 'unknown')}")
    lines.append("")

    # 2. Metadata
    lines.append(f"Generated: {atlas.get('generated_at', '')}")
    lines.append("")

    # 3. Layers table
    lines.append("## Layers")
    lines.append("")
    lines.append("| Layer | Files | Dominant Naming |")
    lines.append("| --- | --- | --- |")
    naming = atlas.get("naming_conventions", {})
    for layer in atlas.get("layers", []):
        name = layer["name"]
        file_count = len(layer.get("files", []))
        dominant = naming.get(name, {}).get("dominant", "—")
        lines.append(f"| {name} | {file_count} | {dominant} |")
    lines.append("")

    # 4. Symbols table (top N)
    lines.append(f"## Symbols (top {symbol_cap})")
    lines.append("")
    lines.append("| File | Kind | Name |")
    lines.append("| --- | --- | --- |")
    for s in atlas.get("symbols", [])[:symbol_cap]:
        fname = Path(s["file"]).name
        lines.append(f"| {fname} | {s['kind']} | {s['name']} |")
    lines.append("")

    # 5. Error Handling table
    lines.append("## Error Handling")
    lines.append("")
    lines.append("| Layer | Style | try/except | raises |")
    lines.append("| --- | --- | --- | --- |")
    for layer_name, info in atlas.get("error_handling", {}).items():
        style = info.get("dominant_style", "—")
        try_except = info.get("try_except", 0)
        raises = info.get("raises", 0)
        lines.append(f"| {layer_name} | {style} | {try_except} | {raises} |")
    lines.append("")

    # 6. Forbidden Imports (skip if empty)
    if forbidden_imports:
        lines.append("## Forbidden Imports")
        lines.append("")
        for item in forbidden_imports:
            lines.append(f"- {item}")
        lines.append("")

    # 7. Key Dependencies (skip if empty)
    if dependency_edges:
        lines.append("## Key Dependencies")
        lines.append("")
        for edge in dependency_edges:
            lines.append(f"- {edge['from_layer']} → {edge['to_layer']}")
        lines.append("")

    return "\n".join(lines)


_ATLAS_MD_BUDGET = 5120


def _write_atlas_md(md_path: Path, atlas: dict) -> None:
    edges = atlas.get("dependency_edges", [])
    forbidden = atlas.get("forbidden_imports", [])

    # Render full content first (top 20 symbols, all edges/imports)
    content = _render_atlas_md(atlas, 20, edges, forbidden)
    truncated = False

    # Progressively reduce symbol rows
    if len(content.encode()) > _ATLAS_MD_BUDGET:
        truncated = True
        for cap in (15, 10, 5, 0):
            content = _render_atlas_md(atlas, cap, edges, forbidden)
            if len(content.encode()) <= _ATLAS_MD_BUDGET:
                break

    # Drop dependency edges
    if len(content.encode()) > _ATLAS_MD_BUDGET:
        truncated = True
        content = _render_atlas_md(atlas, 0, [], forbidden)

    # Drop forbidden imports
    if len(content.encode()) > _ATLAS_MD_BUDGET:
        truncated = True
        content = _render_atlas_md(atlas, 0, [], [])

    if truncated:
        content = content + "\n<!-- truncated to 5KB budget -->"

    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(content)


_FORBIDDEN_MODULES: set[str] = {
    "subprocess", "pickle", "ctypes", "eval", "exec",
    "os.system", "commands", "popen",
}


def _detect_forbidden_imports(layers: list[dict]) -> list[dict]:
    results: list[dict] = []
    for layer in layers:
        layer_name = layer["name"]
        for file_path in layer.get("files", []):
            if not file_path.endswith(".py"):
                continue
            try:
                source = Path(file_path).read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source, filename=file_path)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in _FORBIDDEN_MODULES:
                            results.append({"module": alias.name, "file": file_path, "layer": layer_name})
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module in _FORBIDDEN_MODULES:
                        results.append({"module": module, "file": file_path, "layer": layer_name})
    return results


def _detect_dependency_edges(layers: list[dict], repo_path: Path) -> list[dict]:
    layer_names: set[str] = {layer["name"] for layer in layers}
    counts: dict[tuple[str, str], int] = {}
    for layer in layers:
        from_name = layer["name"]
        for file_path in layer.get("files", []):
            if not file_path.endswith(".py"):
                continue
            try:
                source = Path(file_path).read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source, filename=file_path)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".")[0]
                        if root in layer_names and root != from_name:
                            counts[(from_name, root)] = counts.get((from_name, root), 0) + 1
                elif isinstance(node, ast.ImportFrom):
                    root = (node.module or "").split(".")[0]
                    if root in layer_names and root != from_name:
                        counts[(from_name, root)] = counts.get((from_name, root), 0) + 1
    return [{"from_layer": f, "to_layer": t, "count": c} for (f, t), c in counts.items()]


def main(_args: argparse.Namespace | None = None, _home: Path | None = None) -> None:
    if _args is None:
        parser = argparse.ArgumentParser()
        parser.add_argument("--refresh", action="store_true")
        parser.add_argument("--if-missing", action="store_true", dest="if_missing")
        _args = parser.parse_args()

    home = _home if _home is not None else Path.home()
    repo_path = Path.cwd()
    h, _, _ = project_hash(str(repo_path))
    atlas_path = home / ".claude" / "cartographer" / "projects" / h / "atlas.json"
    if _args.if_missing and atlas_path.exists():
        return

    if _args.refresh:
        flag = atlas_path.parent / "staleness.flag"
        if flag.exists():
            flag.unlink()

    md_path = atlas_path.parent / "atlas.md"

    layers = _detect_layers(repo_path) or []
    symbols = _extract_symbols(layers) or []
    naming = _compute_naming_conventions(symbols) or {}
    error_handling = _detect_error_handling(layers) or {}
    forbidden_imports = _detect_forbidden_imports(layers) or []
    dependency_edges = _detect_dependency_edges(layers, repo_path) or []
    _write_atlas_json(atlas_path, layers, symbols, naming, error_handling, forbidden_imports, dependency_edges)
    _write_atlas_md(md_path, {})


if __name__ == "__main__":
    main()
