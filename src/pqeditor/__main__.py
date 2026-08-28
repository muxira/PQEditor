"""Entry point."""
from __future__ import annotations

import sys
from pathlib import Path


def main():
    # frozen exe: MainWindow via absolute import, icon via _MEIPASS
    try:
        from PySide6.QtWidgets import QApplication
        try:
            from .ui.main_window import MainWindow  # type: ignore
            from .app_state import AppState  # type: ignore
            from .i18n import load_language  # type: ignore
        except ImportError:
            from pqeditor.ui.main_window import MainWindow  # type: ignore
            from pqeditor.app_state import AppState  # type: ignore
            from pqeditor.i18n import load_language  # type: ignore
    except ImportError as e:
        print("PySide6 is not installed. Install GUI extras with:", file=sys.stderr)
        print("  python -m pip install \"pqeditor[gui]\"  (requires CPython 3.10+, PySide6 wheels)", file=sys.stderr)
        print(f"Import error: {e}", file=sys.stderr)
        print("Alternatively, the core pack I/O library (pqeditor.io / pqeditor.model) works without GUI.", file=sys.stderr)
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName("PQEditor")
    try:
        from PySide6.QtGui import QIcon
        from pathlib import Path as _P
        # frozen: icon в _MEIPASS
        base = Path(getattr(sys, "_MEIPASS", _P(__file__).resolve().parents[2]))
        for cand in [base / "icon.ico", base / "icon_1024x1024.jpg", _P(__file__).resolve().parents[2] / "icon.ico", _P("icon.ico")]:
            if cand.exists():
                app.setWindowIcon(QIcon(str(cand)))
                break
    except: pass
    try:
        load_language()
    except: pass
    # If file paths given on command line, open them
    state = AppState.instance()
    for arg in sys.argv[1:]:
        p = Path(arg)
        if p.exists() and p.suffix.lower() == ".pq":
            try:
                state.open_file(p)
            except Exception as e:
                print(f"Failed to open {p}: {e}", file=sys.stderr)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
