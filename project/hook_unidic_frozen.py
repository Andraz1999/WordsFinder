"""
hook_unidic_frozen.py
---------------------
PyInstaller runtime hook — loaded before any app code when the exe starts.

Problem:
    unidic locates its dictionary folder via:
        DICDIR = os.path.join(os.path.dirname(__file__), "dicdir")
    When frozen, __file__ points into the read-only sys._MEIPASS bundle,
    which works fine — BUT fugashi calls `unidic.DICDIR` at import time,
    and some versions of unidic also expose it as a module attribute that
    other code checks with `hasattr(unidic, 'DICDIR')`.  If the attribute
    is missing (older unidic builds) or points nowhere (path not yet set),
    you get:
        AttributeError: module 'unidic' has no attribute DICDIR

Fix:
    Before the app imports anything, forcibly set unidic.DICDIR to the
    correct path inside the bundle.
"""

import os
import sys

# sys._MEIPASS is only set when running as a PyInstaller-frozen exe.
# Guard so this hook is also safe to run from source (it becomes a no-op).
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    import importlib

    # Ensure unidic is importable from the bundle
    _meipass = sys._MEIPASS

    # Import the module so we can patch it
    import unidic  # noqa: E402  (imported after sys.path is set by PyInstaller)

    # The dictionary files land at:  _MEIPASS/unidic/dicdir/
    _dicdir = os.path.join(_meipass, "unidic", "dicdir")

    # Patch the module-level attribute that fugashi reads
    unidic.DICDIR = _dicdir

    # Some fugashi versions also read unidic_lite as a fallback; patch that too
    try:
        import unidic_lite
        _lite_dicdir = os.path.join(_meipass, "unidic_lite", "dicdir")
        unidic_lite.DICDIR = _lite_dicdir
    except (ImportError, AttributeError):
        pass