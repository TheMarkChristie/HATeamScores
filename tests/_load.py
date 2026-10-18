"""Import the integration's pure modules (const, model) without Home Assistant installed.

The package's __init__ imports Home Assistant, so the package is registered by hand with its path and __init__ is
never run; the relative imports inside model.py then resolve to const.py as usual."""
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "sportsdb_tracker"

if "custom_components.sportsdb_tracker" not in sys.modules:
    top = types.ModuleType("custom_components")
    top.__path__ = [str(ROOT / "custom_components")]
    pkg = types.ModuleType("custom_components.sportsdb_tracker")
    pkg.__path__ = [str(COMPONENT)]
    sys.modules["custom_components"] = top
    sys.modules["custom_components.sportsdb_tracker"] = pkg

from custom_components.sportsdb_tracker import apps, const, model, scorers, streams, tv  # noqa: E402,F401
