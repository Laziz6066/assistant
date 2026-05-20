# installer/runtime_hook.py
# Runs before user code. Fixes stdout/stderr encoding so Cyrillic and other
# non-ASCII text doesn't crash the console on Windows code page 1251 / 866.
import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
