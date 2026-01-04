"""ZettelMaster mechanical toolkit package."""
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

try:
    __version__ = version("zettelmaster")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"

__all__ = [
    "__version__",
    "IngestPipeline",
    "SimplifiedOrchestrator",
    "TOONConverter",
    "ZettelParser",
]

_EXPORT_MAP = {
    "IngestPipeline": ("zettelmaster.ingest_pipeline", "IngestPipeline"),
    "SimplifiedOrchestrator": ("zettelmaster.simplified_orchestrator", "SimplifiedOrchestrator"),
    "TOONConverter": ("zettelmaster.toon_converter", "TOONConverter"),
    "ZettelParser": ("zettelmaster.zettel_parser", "ZettelParser"),
}


def __getattr__(name: str) -> Any:  # pragma: no cover - thin convenience wrapper
    if name in _EXPORT_MAP:
        module_name, attr = _EXPORT_MAP[name]
        module = import_module(module_name)
        value = getattr(module, attr)
        globals()[name] = value
        return value
    raise AttributeError(f"module 'zettelmaster' has no attribute {name!r}")


if TYPE_CHECKING:  # pragma: no cover
    from .ingest_pipeline import IngestPipeline
    from .simplified_orchestrator import SimplifiedOrchestrator
    from .toon_converter import TOONConverter
    from .zettel_parser import ZettelParser
