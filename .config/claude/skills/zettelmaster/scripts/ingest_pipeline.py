from importlib import import_module as _import_module
from pathlib import Path as _Path
from runpy import run_module as _run_module
import sys as _sys

_SRC_ROOT = _Path(__file__).resolve().parents[1] / 'src'
if str(_SRC_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_SRC_ROOT))

_TARGET = 'zettelmaster.ingest_pipeline'

if __name__ == '__main__':
    _run_module(_TARGET, run_name='__main__')
else:
    _module = _import_module(_TARGET)
    globals().update({k: getattr(_module, k) for k in dir(_module) if not k.startswith('__')})
    __all__ = getattr(_module, '__all__', globals().get('__all__', []))
    __doc__ = getattr(_module, '__doc__', __doc__)
