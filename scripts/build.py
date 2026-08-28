"""Build standalone executable.

Requires CPython 3.10+ (PyPy does not have PySide6 wheels).
Use: python scripts/build.py   # will invoke PyInstaller
Alternative: nuitka --standalone --enable-plugin=pyside6 src/pqeditor/__main__.py

See pqeditor.spec for PyInstaller configuration.
"""
import subprocess
import sys

def main():
    # Check CPython
    if "PyPy" in sys.version:
        print("WARNING: PyPy detected — PySide6 wheels unavailable. Use CPython for GUI build.", file=sys.stderr)
    print("Installing GUI extras...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", ".[gui]", "pyinstaller"])
    print("Running PyInstaller...")
    subprocess.check_call([sys.executable, "-m", "PyInstaller", "pqeditor.spec", "--noconfirm"])
    print("Done. Dist in dist/")

if __name__ == "__main__":
    main()
