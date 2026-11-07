"""نقطه‌ی ورود برنامه‌ی کاردکس انبار."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from core.db import Database
from gui.main_window import MainWindow, ask_text


def build_app(db_path=None):
    app = QApplication.instance() or QApplication(sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)
    app.setStyle("Fusion")
    f = QFont()
    f.setFamilies(["Vazirmatn", "Tahoma", "Segoe UI", "Geeza Pro", "Arial"])
    f.setPointSize(10)
    app.setFont(f)
    db = Database(db_path)
    if not db.companies():
        name = ask_text(None, "شروع", "نام اولین شرکت را وارد کنید:", "شرکت من") or "شرکت من"
        db.add_company(name)
    db.undo.clear()                       # ساخت شرکت اولیه قابل بازگردانی نیست
    return app, MainWindow(db)


def main():
    app, win = build_app()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
