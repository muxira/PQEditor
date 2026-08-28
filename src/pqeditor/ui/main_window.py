"""Main window — multi-pack tabs, round/theme/question grid, toolbars."""
from __future__ import annotations

import random
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabBar,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QFileDialog,
)

from ..app_state import AppState, OpenPack
from ..io import LoadedPack, load_pq, save_pq, validate_loaded_pack
from ..model import QuestionType, RoundType, Question, Theme
from ..i18n import tr, get_language, set_language
from .export_dialog import ExportDialog
from .question_dialog import QuestionDialog


# ---------- Theme widget (shows question tiles) ----------

class ThemeWidget(QFrame):
    def __init__(self, theme: Theme, theme_idx: int, round_obj, open_pack: OpenPack, on_refresh, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.theme_idx = theme_idx
        self.round_obj = round_obj
        self.open_pack = open_pack
        self.on_refresh = on_refresh
        self.setFrameShape(QFrame.Box)
        self.setStyleSheet("ThemeWidget { border: 1px solid #ccc; border-radius: 6px; }")
        self.setMinimumWidth(180)
        lay = QVBoxLayout(self)
        # header with editable name
        hdr = QHBoxLayout()
        self.name_edit = QLineEdit(theme.Name)
        self.name_edit.setPlaceholderText(tr("Theme name", "Название темы"))
        hdr.addWidget(self.name_edit, 1)
        lay.addLayout(hdr)
        self.name_edit.editingFinished.connect(self._rename)

        self.desc_edit = QLineEdit(theme.Description)
        self.desc_edit.setPlaceholderText(tr("Theme description", "Описание темы"))
        lay.addWidget(self.desc_edit)
        self.desc_edit.editingFinished.connect(self._redesc)

        btn_del = QPushButton(tr("× Delete theme", "× Удалить тему"))
        btn_del.setStyleSheet("color: #a00; font-size: 10px;")
        btn_del.clicked.connect(self._delete_theme)
        lay.addWidget(btn_del)

        self.tiles_lay = QGridLayout()
        lay.addLayout(self.tiles_lay)
        self._build_tiles()

        self.btn_add = QPushButton(tr("+ Add question", "+ Добавить вопрос"))
        lay.addWidget(self.btn_add)
        self.btn_add.clicked.connect(self._add_question)
        self._update_add_visibility()

    def _rename(self):
        self.theme.Name = self.name_edit.text()
        self.open_pack.dirty = True
        self.open_pack.undo.push(self.open_pack.pack)
        self.on_refresh()

    def _redesc(self):
        self.theme.Description = self.desc_edit.text()
        self.open_pack.dirty = True

    def _delete_theme(self):
        if len(self.round_obj.Themes) <= 1:
            QMessageBox.warning(self, "Theme", "Round must have at least 1 theme.")
            return
        ret = QMessageBox.question(self, "Delete theme", f"Delete theme '{self.theme.Name}' and all its questions?",
                                   QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        self.round_obj.Themes.pop(self.theme_idx)
        self.open_pack.dirty = True
        self.open_pack.undo.push(self.open_pack.pack)
        self.on_refresh()

    def _build_tiles(self):
        while self.tiles_lay.count():
            item = self.tiles_lay.takeAt(0)
            w = item.widget()
            if w: w.deleteLater()
        for qi, q in enumerate(self.theme.Questions):
            tile = QFrame()
            tile.setFixedSize(160, 96)
            tile.setCursor(Qt.PointingHandCursor)
            # high-contrast type system
            is_final = q.IsFinal
            if is_final:
                bg, border, badge, price_color = "#4A148C", "#6A1B9A", tr("FINAL", "ФИНАЛ"), "#FFFFFF"
                label = badge
            elif q.Type == QuestionType.LeadingHints:
                bg, border, badge = "#6A1B9A", "#8E24AA", tr("HINTS", "ПОДСКАЗКИ")
                price_color = "#FFFFFF"
                label = badge
            elif q.Type == QuestionType.Quiz:
                bg, border, badge = "#1B5E20", "#2E7D32", tr("QUIZ", "КВИЗ")
                price_color = "#FFFFFF"
                label = badge
            elif q.Type == QuestionType.CatInBag:
                bg, border, badge = "#E65100", "#EF6C00", tr("CAT", "КОТ В МЕШКЕ")
                price_color = "#FFFFFF"
                label = badge
            elif q.Type == QuestionType.Auction:
                bg, border, badge = "#B71C1C", "#C62828", tr("AUCTION", "АУКЦИОН")
                price_color = "#FFFFFF"
                label = badge
            elif q.Type == QuestionType.GuessNumber:
                bg, border, badge = "#F57F17", "#F9A825", tr("NUMBER", "ЧИСЛО")
                price_color = "#212121"
                label = badge
            else:
                bg, border, badge = "#0D47A1", "#1565C0", tr("QUESTION", "ВОПРОС")
                price_color = "#FFFFFF"
                label = badge
            tile.setStyleSheet(f"QFrame {{ background: {bg}; border: 2px solid {border}; border-radius: 10px; }} QLabel {{ background: transparent; border: none; }}")
            vl = QVBoxLayout(tile); vl.setContentsMargins(6,6,6,6); vl.setSpacing(2)
            # badge
            badge_lbl = QLabel(label); badge_lbl.setAlignment(Qt.AlignCenter)
            badge_lbl.setStyleSheet(f"color: {price_color}; font-size: 9px; font-weight: 700; letter-spacing: 0.5px;")
            vl.addWidget(badge_lbl)
            # price — large, high contrast
            price_lbl = QLabel(str(q.Price)); price_lbl.setAlignment(Qt.AlignCenter)
            price_lbl.setStyleSheet(f"color: {price_color}; font-size: 26px; font-weight: 900;")
            vl.addWidget(price_lbl, 1)
            # question text preview — small, high contrast on colored bg using white with shadow
            preview = (q.Text or q.Answer.Text or "").strip().replace("\n"," ")[:42]
            if q.Type == QuestionType.LeadingHints and q.RevealingClues:
                preview = q.RevealingClues[0].Text[:42]
            txt_lbl = QLabel(preview if preview else "—")
            txt_lbl.setAlignment(Qt.AlignCenter); txt_lbl.setWordWrap(True)
            txt_lbl.setStyleSheet(f"color: {price_color}; font-size: 8px; font-weight: 600; opacity: 0.95;")
            vl.addWidget(txt_lbl)
            # clickable — whole tile
            def _make_handler(_qi):
                def _handler(evt):
                    if evt.button() == Qt.LeftButton:
                        self._edit_question(_qi)
                return _handler
            tile.mousePressEvent = _make_handler(qi)
            tip = f"{tr('Type:', 'Тип:')} {q.Type.name} IsFinal={q.IsFinal}\nQ: {q.Text[:120]}\nA: {q.Answer.Text[:120]}"
            if q.RevealingClues:
                tip += f"\n{tr('Hints:', 'Подсказок:')} {len(q.RevealingClues)}"
            tile.setToolTip(tip)
            tile.enterEvent = lambda e, t=tile, b=border: t.setStyleSheet(f"QFrame {{ background: {bg}; border: 2px solid #000; border-radius: 10px; }} QLabel {{ background: transparent; border: none; }}")
            tile.leaveEvent = lambda e, t=tile, bg=bg, border=border: t.setStyleSheet(f"QFrame {{ background: {bg}; border: 2px solid {border}; border-radius: 10px; }} QLabel {{ background: transparent; border: none; }}")
            self.tiles_lay.addWidget(tile, qi // 2, qi % 2)
            price_lbl.setToolTip(f"{tr('Price:', 'Цена:')} {q.Price}")

    def _update_add_visibility(self):
        if self.round_obj.Type == RoundType.Final and len(self.theme.Questions) >= 1:
            self.btn_add.setEnabled(False)
            self.btn_add.setToolTip("Final round themes have exactly 1 question.")
        else:
            self.btn_add.setEnabled(len(self.theme.Questions) < 5)
            self.btn_add.setToolTip("" if len(self.theme.Questions) < 5 else "Max 5 questions per theme.")

    def _add_question(self):
        if self.round_obj.Type == RoundType.Final and len(self.theme.Questions) >= 1:
            QMessageBox.warning(self, "Final", "Final themes can have only 1 question.")
            return
        if len(self.theme.Questions) >= 5:
            QMessageBox.warning(self, "Limit", "Max 5 questions per theme.")
            return
        is_final = (self.round_obj.Type == RoundType.Final)
        q = Question(
            Price=self.theme.Questions[-1].Price + 10 if self.theme.Questions else 10,
            Type=QuestionType.Normal,
            Text="Новый вопрос",
            IsFinal=is_final,
        )
        if is_final:
            q.Text = "финалвопрос"
            q.Answer.Text = "финалответ"
        self.theme.Questions.append(q)
        self.open_pack.dirty = True
        self.open_pack.undo.push(self.open_pack.pack)
        self.on_refresh()

    def _edit_question(self, qi: int):
        q = self.theme.Questions[qi]
        dlg = QuestionDialog(q, self.open_pack.loaded.media, self.round_obj.Name, self.theme.Name, is_final_round=(self.round_obj.Type==RoundType.Final), parent=self)
        dlg.exec()
        if dlg.delete_requested:
            # delete
            self.theme.Questions.pop(qi)
            self.open_pack.dirty = True
            self.open_pack.undo.push(self.open_pack.pack)
            self.on_refresh()
            return
        if dlg.result() == QDialog.Accepted:
            # q was mutated in place; handle media moves if price/dir changed? media already in dict
            # need to ensure Price-sync for Leading Hints already done
            self.open_pack.dirty = True
            self.open_pack.undo.push(self.open_pack.pack)
            self.on_refresh()
        else:
            # dialog rejected — revert media additions that were staged but not saved? For simplicity keep them (orphaned files harmless)
            pass


# ---------- Pack tab (one open pack) ----------

class PackTabWidget(QWidget):
    def __init__(self, open_pack: OpenPack, main_window: "MainWindow", parent=None):
        super().__init__(parent)
        self.open_pack = open_pack
        self.main_window = main_window
        self.current_round_idx = 0
        lay = QVBoxLayout(self)

        top = QHBoxLayout()
        self.round_name_edit = QLineEdit()
        self.round_desc_edit = QLineEdit()
        self.round_desc_edit.setPlaceholderText(tr("Round description", "Описание раунда"))
        top.addWidget(QLabel(tr("Round:", "Раунд:")))
        top.addWidget(self.round_name_edit, 1)
        top.addWidget(QLabel(tr("Desc:", "Опис:")))
        top.addWidget(self.round_desc_edit, 1)
        lay.addLayout(top)
        self.round_name_edit.editingFinished.connect(self._round_rename)
        self.round_desc_edit.editingFinished.connect(self._round_redesc)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.themes_container = QWidget()
        self.themes_lay = QHBoxLayout(self.themes_container)
        self.themes_lay.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.themes_container)
        lay.addWidget(self.scroll, 1)

        mid = QHBoxLayout()
        self.btn_add_theme = QPushButton(tr("+ Add theme", "+ Добавить тему"))
        mid.addWidget(self.btn_add_theme); mid.addStretch()
        lay.addLayout(mid)
        self.btn_add_theme.clicked.connect(self._add_theme)

        bottom = QHBoxLayout()
        self.round_tabs = QTabBar()
        self.round_tabs.setMovable(False)
        self.round_tabs.currentChanged.connect(self._switch_round)
        bottom.addWidget(self.round_tabs, 1)
        self.btn_create_round = QPushButton(tr("+ Create round", "+ Создать раунд"))
        bottom.addWidget(self.btn_create_round)
        self.btn_create_round.clicked.connect(self._create_round)
        self.btn_del_round = QPushButton(tr("Delete round", "Удалить раунд"))
        self.btn_del_round.setStyleSheet("color: #a00;")
        bottom.addWidget(self.btn_del_round)
        self.btn_del_round.clicked.connect(self._delete_round)
        lay.addLayout(bottom)

        self.refresh()

    def refresh(self):
        pack = self.open_pack.pack
        # round tabs
        self.round_tabs.blockSignals(True)
        while self.round_tabs.count():
            self.round_tabs.removeTab(0)
        for i, r in enumerate(pack.Rounds):
            typ = " (Final)" if r.Type == RoundType.Final else ""
            self.round_tabs.addTab(f"{r.Name}{typ}")
        if 0 <= self.current_round_idx < len(pack.Rounds):
            self.round_tabs.setCurrentIndex(self.current_round_idx)
        elif pack.Rounds:
            self.current_round_idx = 0
            self.round_tabs.setCurrentIndex(0)
        self.round_tabs.blockSignals(False)

        if not pack.Rounds:
            self.round_name_edit.setText("")
            self.round_desc_edit.setText("")
            self._clear_themes()
            return
        rnd = pack.Rounds[self.current_round_idx]
        self.round_name_edit.setText(rnd.Name)
        self.round_desc_edit.setText(rnd.Description)
        self._rebuild_themes(rnd)

    def _clear_themes(self):
        while self.themes_lay.count():
            item = self.themes_lay.takeAt(0)
            w = item.widget()
            if w: w.deleteLater()

    def _rebuild_themes(self, rnd):
        self._clear_themes()
        for ti, theme in enumerate(rnd.Themes):
            w = ThemeWidget(theme, ti, rnd, self.open_pack, on_refresh=self.refresh)
            self.themes_lay.addWidget(w)
        self.themes_lay.addStretch()

    def _switch_round(self, idx: int):
        if 0 <= idx < len(self.open_pack.pack.Rounds):
            self.current_round_idx = idx
            self.refresh()

    def _round_rename(self):
        if not self.open_pack.pack.Rounds:
            return
        rnd = self.open_pack.pack.Rounds[self.current_round_idx]
        new = self.round_name_edit.text().strip()
        if new and new != rnd.Name:
            rnd.Name = new
            self.open_pack.dirty = True
            self.open_pack.undo.push(self.open_pack.pack)
            self.refresh()
            self.main_window.refresh_pack_tabs()

    def _round_redesc(self):
        rnd = self.open_pack.pack.Rounds[self.current_round_idx]
        rnd.Description = self.round_desc_edit.text()
        self.open_pack.dirty = True

    def _create_round(self):
        # dialog to choose type
        from PySide6.QtWidgets import QInputDialog
        types = ["Normal", "Final"]
        typ, ok = QInputDialog.getItem(self, "Create round", "Round type:", types, 0, False)
        if not ok:
            return
        name, ok = QInputDialog.getText(self, "Create round", "Round name:")
        if not ok or not name.strip():
            return
        rt = RoundType.Final if typ == "Final" else RoundType.Normal
        from ..model import Round, Theme, Question
        # new round with one theme and one question
        is_final = (rt == RoundType.Final)
        q = Question(Price=10 if not is_final else 20, Type=QuestionType.Normal, Text="Новый вопрос", IsFinal=is_final)
        if is_final:
            q.Text = "финалвопрос"; q.Answer.Text = "финалответ"
        theme = Theme(Name="НоваяТема", Description="", Questions=[q])
        theme.MaxQuestionsCount = 1 if is_final else 5
        rnd = __import__("pqeditor.model", fromlist=["Round"]).Round(Name=name.strip(), Description="", Type=rt, Themes=[theme])
        self.open_pack.pack.Rounds.append(rnd)
        self.current_round_idx = len(self.open_pack.pack.Rounds)-1
        self.open_pack.dirty = True
        self.open_pack.undo.push(self.open_pack.pack)
        self.refresh()
        self.main_window.refresh_pack_tabs()

    def _delete_round(self):
        if len(self.open_pack.pack.Rounds) <= 1:
            QMessageBox.warning(self, "Round", "Pack must have at least 1 round.")
            return
        rnd = self.open_pack.pack.Rounds[self.current_round_idx]
        ret = QMessageBox.question(self, "Delete round", f"Delete round '{rnd.Name}'?", QMessageBox.Yes | QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        self.open_pack.pack.Rounds.pop(self.current_round_idx)
        self.current_round_idx = max(0, self.current_round_idx-1)
        self.open_pack.dirty = True
        self.open_pack.undo.push(self.open_pack.pack)
        self.refresh()
        self.main_window.refresh_pack_tabs()

    def _add_theme(self):
        rnd = self.open_pack.pack.Rounds[self.current_round_idx]
        if len(rnd.Themes) >= 5:
            QMessageBox.warning(self, "Theme", "Max 5 themes per round.")
            return
        from ..model import Theme, Question
        is_final = (rnd.Type == RoundType.Final)
        q = Question(Price=10 if not is_final else 20, Type=QuestionType.Normal, Text="Новый вопрос", IsFinal=is_final)
        theme = Theme(Name=f"Тема{len(rnd.Themes)+1}", Description="", Questions=[q])
        rnd.Themes.append(theme)
        self.open_pack.dirty = True
        self.open_pack.undo.push(self.open_pack.pack)
        self.refresh()

    def _sort_by_price(self):
        rnd = self.open_pack.pack.Rounds[self.current_round_idx]
        for theme in rnd.Themes:
            theme.Questions.sort(key=lambda q: q.Price)
        self.open_pack.dirty = True
        self.open_pack.undo.push(self.open_pack.pack)
        self.refresh()

    def _assign_randomly(self):
        rnd = self.open_pack.pack.Rounds[self.current_round_idx]
        if rnd.Type == RoundType.Final:
            QMessageBox.information(self, "Random", "Cannot assign special types in a Final round.")
            return
        # collect all questions
        all_qs = []
        for t in rnd.Themes:
            all_qs.extend(t.Questions)
        if not all_qs:
            return
        # reset all to Normal first
        for q in all_qs:
            if q.Type in (QuestionType.CatInBag, QuestionType.Auction):
                q.Type = QuestionType.Normal
        # randomly pick 1-2 Auction and 1-2 Cat
        n = len(all_qs)
        num_auction = min(2, n // 3 + 1) if n >= 3 else 1
        num_cat = min(2, n // 3 + 1) if n >= 3 else 0
        # ensure not exceeding
        picks = random.sample(all_qs, min(num_auction + num_cat, n))
        for i, q in enumerate(picks):
            if i < num_auction:
                q.Type = QuestionType.Auction
            else:
                q.Type = QuestionType.CatInBag
        self.open_pack.dirty = True
        self.open_pack.undo.push(self.open_pack.pack)
        self.refresh()


# ---------- Main window ----------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PQEditor — Party Quiz Pack Editor")
        self.resize(1200, 800)
        self.state = AppState.instance()
        # icon
        try:
            from PySide6.QtGui import QIcon
            from pathlib import Path as _P
            for cand in [_P(__file__).resolve().parents[3] / "icon.ico", _P(__file__).resolve().parents[3] / "icon_1024x1024.jpg", _P("icon.ico"), _P("icon_1024x1024.jpg")]:
                if cand.exists():
                    self.setWindowIcon(QIcon(str(cand)))
                    break
        except: pass

        # Menu — EN default, RU via tr()
        menubar = self.menuBar()
        file_menu = menubar.addMenu(tr("&File", "&Файл"))
        act_new = QAction(tr("New pack", "Новый пак"), self); act_new.setShortcut(QKeySequence.New)
        act_open = QAction(tr("Open…", "Открыть…"), self); act_open.setShortcut(QKeySequence.Open)
        act_save = QAction(tr("Save", "Сохранить"), self); act_save.setShortcut(QKeySequence.Save)
        act_save_as = QAction(tr("Save As…", "Сохранить как…"), self); act_save_as.setShortcut(QKeySequence.SaveAs)
        act_export = QAction(tr("Export…", "Экспорт…"), self)
        act_close_pack = QAction(tr("Close pack", "Закрыть пак"), self)
        act_quit = QAction(tr("Quit", "Выход"), self)
        for a in (act_new, act_open, act_save, act_save_as, act_export, act_close_pack, act_quit):
            file_menu.addAction(a)
        act_new.triggered.connect(self.new_pack)
        act_open.triggered.connect(self.open_pack)
        act_save.triggered.connect(self.save_current)
        act_save_as.triggered.connect(self.save_as)
        act_export.triggered.connect(self.export_pack)
        act_close_pack.triggered.connect(self.close_current_pack)
        act_quit.triggered.connect(self.close)

        edit_menu = menubar.addMenu(tr("&Edit", "&Правка"))
        act_undo = QAction(tr("Undo", "Отменить"), self); act_undo.setShortcut(QKeySequence.Undo)
        act_redo = QAction(tr("Redo", "Повторить"), self); act_redo.setShortcut(QKeySequence.Redo)
        act_validate = QAction(tr("Validate…", "Проверить…"), self)
        edit_menu.addAction(act_undo); edit_menu.addAction(act_redo); edit_menu.addAction(act_validate)
        act_undo.triggered.connect(self.undo)
        act_redo.triggered.connect(self.redo)
        act_validate.triggered.connect(self.validate_current)

        # Language menu — UI translation EN default / RU
        lang_menu = menubar.addMenu(tr("&Language", "&Язык"))
        from PySide6.QtGui import QAction as _QA
        self.act_lang_en = _QA("English", self); self.act_lang_en.setCheckable(True)
        self.act_lang_ru = _QA("Русский", self); self.act_lang_ru.setCheckable(True)
        # exclusive group
        self.act_lang_en.setChecked(get_language()=="en")
        self.act_lang_ru.setChecked(get_language()=="ru")
        lang_menu.addAction(self.act_lang_en); lang_menu.addAction(self.act_lang_ru)
        self.act_lang_en.triggered.connect(lambda: self._set_ui_lang("en"))
        self.act_lang_ru.triggered.connect(lambda: self._set_ui_lang("ru"))

        # Central: pack tabs
        self.pack_tabs = QTabWidget()
        self.pack_tabs.setTabsClosable(True)
        self.pack_tabs.setMovable(True)
        self.pack_tabs.tabCloseRequested.connect(self._close_tab)
        self.pack_tabs.currentChanged.connect(self._pack_tab_changed)
        self.setCentralWidget(self.pack_tabs)

        # Right sidebar — фиксированный, нельзя закрыть/открепить (pack language теперь только в Экспорте)
        from PySide6.QtWidgets import QDockWidget
        dock = QDockWidget(tr("Pack", "Пак"), self)
        dock.setAllowedAreas(Qt.RightDockWidgetArea)
        dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        side = QWidget(); s_lay = QVBoxLayout(side)
        self.pack_name_edit = QLineEdit()
        self.pack_name_edit.setPlaceholderText(tr("Pack title", "Название пака"))
        s_lay.addWidget(QLabel(tr("Pack name:", "Название пака:")))
        s_lay.addWidget(self.pack_name_edit)
        self.pack_name_edit.editingFinished.connect(self._pack_rename)
        self.btn_sidebar_sort = QPushButton(tr("Sort by price", "Сортировать по цене"))
        self.btn_sidebar_random = QPushButton(tr("Assign randomly", "Назначить случайно"))
        self.btn_import = QPushButton(tr("Import…", "Импорт…"))
        self.btn_export = QPushButton(tr("Export…", "Экспорт…"))
        self.btn_save = QPushButton(tr("Save", "Сохранить"))
        for b in (self.btn_sidebar_sort, self.btn_sidebar_random, self.btn_import, self.btn_export, self.btn_save):
            s_lay.addWidget(b)
        self.btn_sidebar_sort.clicked.connect(self._sidebar_sort)
        self.btn_sidebar_random.clicked.connect(self._sidebar_random)
        self.btn_import.clicked.connect(self.open_pack)
        self.btn_export.clicked.connect(self.export_pack)
        self.btn_save.clicked.connect(self.save_current)
        s_lay.addStretch()
        s_lay.addWidget(QLabel(tr("Recent:", "Недавние:")))
        from PySide6.QtWidgets import QListWidget
        self.recent_list = QListWidget()
        self.recent_list.setMaximumHeight(150)
        s_lay.addWidget(self.recent_list)
        self.recent_list.itemDoubleClicked.connect(self._open_recent)
        self._refresh_recent()
        dock.setWidget(side)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self._dock = dock

        # Ensure at least one pack
        if not self.state.open_packs:
            self.new_pack()

        self.refresh_pack_tabs()
        self._update_title()

    # -- pack tab management
    def refresh_pack_tabs(self):
        # rebuild tabs to reflect dirty markers etc.
        # Keep current index
        cur = self.pack_tabs.currentIndex()
        # Remove all and re-add widgets (PackTabWidgets already created? we store them)
        # Approach: if number of packs changed, rebuild; otherwise just rename tabs
        # For simplicity, rebuild if counts differ
        if self.pack_tabs.count() != len(self.state.open_packs):
            while self.pack_tabs.count():
                self.pack_tabs.removeTab(0)
            for op in self.state.open_packs:
                w = PackTabWidget(op, self)
                # Store reference
                w._open_pack_ref = op
                title = op.title
                idx = self.pack_tabs.addTab(w, title)
                # tooltip with path
                if op.file_path:
                    self.pack_tabs.setTabToolTip(idx, str(op.file_path))
            if 0 <= self.state.current_index < self.pack_tabs.count():
                self.pack_tabs.setCurrentIndex(self.state.current_index)
            cur = self.pack_tabs.currentIndex()
        else:
            for i, op in enumerate(self.state.open_packs):
                self.pack_tabs.setTabText(i, op.title)
        self._update_title()
        self._refresh_recent()
        cp = self.state.current_pack()
        if cp:
            self.pack_name_edit.blockSignals(True)
            self.pack_name_edit.setText(cp.pack.Name)
            self.pack_name_edit.blockSignals(False)
            self.pack_name_edit.setEnabled(True)
        else:
            self.pack_name_edit.setEnabled(False)

    def _set_ui_lang(self, lang: str):
        set_language(lang)
        self.act_lang_en.setChecked(lang=="en")
        self.act_lang_ru.setChecked(lang=="ru")
        QMessageBox.information(self, tr("Language", "Язык"), tr("Restart to apply language.\nПерезапустите для применения языка.", "Перезапустите приложение для применения языка."))
        # update menu titles immediately
        try:
            self.menuBar().actions()[0].setText(tr("&File", "&Файл"))
            self.menuBar().actions()[1].setText(tr("&Edit", "&Правка"))
            self.menuBar().actions()[2].setText(tr("&Language", "&Язык"))
            self._dock.setWindowTitle(tr("Pack", "Пак"))
        except: pass

    def _pack_tab_changed(self, idx: int):
        if 0 <= idx < len(self.state.open_packs):
            self.state.current_index = idx
            cp = self.state.current_pack()
            if cp:
                self.pack_name_edit.blockSignals(True)
                self.pack_name_edit.setText(cp.pack.Name)
                self.pack_name_edit.blockSignals(False)
        self._update_title()

    def _close_tab(self, idx: int):
        op = self.state.open_packs[idx]
        if op.dirty:
            ret = QMessageBox.question(self, "Unsaved changes", f"Pack '{op.pack.Name}' has unsaved changes. Close without saving?",
                                       QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if ret == QMessageBox.Cancel:
                return
            if ret == QMessageBox.No:
                return
            # Yes = discard
        self.state.close_pack(idx)
        self.pack_tabs.removeTab(idx)
        if not self.state.open_packs:
            self.new_pack()
        else:
            self.refresh_pack_tabs()

    def _update_title(self):
        cp = self.state.current_pack()
        if cp:
            dirty = " *" if cp.dirty else ""
            path = f" — {cp.file_path}" if cp.file_path else ""
            self.setWindowTitle(f"PQEditor — {cp.pack.Name}{dirty}{path}")
        else:
            self.setWindowTitle("PQEditor")

    # -- actions
    def new_pack(self):
        from ..io import new_empty_pack
        loaded = new_empty_pack()
        self.state.add_pack(loaded, None)
        # add tab
        w = PackTabWidget(self.state.open_packs[-1], self)
        idx = self.pack_tabs.addTab(w, self.state.open_packs[-1].title)
        self.pack_tabs.setCurrentIndex(idx)
        self.state.current_index = idx
        self.refresh_pack_tabs()

    def open_pack(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Open pack", "", "Party Quiz packs (*.pq);;All files (*.*)")
        if not fn:
            return
        try:
            idx = self.state.open_file(Path(fn))
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))
            return
        # add tab
        op = self.state.open_packs[idx]
        w = PackTabWidget(op, self)
        tab_idx = self.pack_tabs.addTab(w, op.title)
        self.pack_tabs.setCurrentIndex(tab_idx)
        self.state.current_index = idx
        self.refresh_pack_tabs()

    def save_current(self):
        cp = self.state.current_pack()
        if not cp:
            return
        errs = validate_loaded_pack(cp.loaded)
        if errs:
            ret = QMessageBox.question(self, "Validation warnings", "\n".join(errs) + "\n\nSave anyway?", QMessageBox.Yes | QMessageBox.No)
            if ret != QMessageBox.Yes:
                return
        if cp.file_path is None:
            self.save_as()
            return
        try:
            cp.save()
            QMessageBox.information(self, "Saved", f"Saved to {cp.file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))
        self.refresh_pack_tabs()

    def save_as(self):
        cp = self.state.current_pack()
        if not cp:
            return
        fn, _ = QFileDialog.getSaveFileName(self, "Save pack as", cp.pack.Name + ".pq", "Party Quiz packs (*.pq)")
        if not fn:
            return
        if not fn.lower().endswith(".pq"):
            fn += ".pq"
        try:
            cp.save(Path(fn))
            QMessageBox.information(self, "Saved", f"Saved to {fn}")
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))
        self.refresh_pack_tabs()

    def export_pack(self):
        cp = self.state.current_pack()
        if not cp:
            return
        dlg = ExportDialog(cp.pack, list(cp.loaded.media.keys()), self)
        if dlg.exec() != QDialog.Accepted:
            return
        cover_result = dlg.apply_to_pack(cp.pack)
        if cover_result:
            fname, data = cover_result
            cp.loaded.media[fname] = data
            # Also need to ensure Icon points to root file — done
        # Now choose file
        default = (cp.file_path or Path(cp.pack.Name + ".pq"))
        fn, _ = QFileDialog.getSaveFileName(self, "Export pack", str(default), "Party Quiz packs (*.pq)")
        if not fn:
            return
        if not fn.lower().endswith(".pq"):
            fn += ".pq"
        errs = validate_loaded_pack(cp.loaded)
        if errs:
            ret = QMessageBox.question(self, "Validation warnings", "\n".join(errs) + "\n\nExport anyway?", QMessageBox.Yes | QMessageBox.No)
            if ret != QMessageBox.Yes:
                return
        try:
            # Before export, rebuild media paths to reflect current round/theme names & prices?
            # For now, keep paths as-is; io.save_pq writes whatever is in media dict
            # But ensure all Picture/Audio/Video paths exist in media dict — already validated
            cp.save(Path(fn))
            cp.dirty = False
            QMessageBox.information(self, "Exported", f"Exported to {fn}")
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))
        self.refresh_pack_tabs()

    def close_current_pack(self):
        idx = self.pack_tabs.currentIndex()
        if idx >= 0:
            self._close_tab(idx)

    def undo(self):
        cp = self.state.current_pack()
        if cp and cp.undo_action():
            # refresh current tab's view
            w = self.pack_tabs.currentWidget()
            if isinstance(w, PackTabWidget):
                w.refresh()
            self.refresh_pack_tabs()

    def redo(self):
        cp = self.state.current_pack()
        if cp and cp.redo_action():
            w = self.pack_tabs.currentWidget()
            if isinstance(w, PackTabWidget):
                w.refresh()
            self.refresh_pack_tabs()

    def validate_current(self):
        cp = self.state.current_pack()
        if not cp:
            return
        errs = validate_loaded_pack(cp.loaded)
        if not errs:
            QMessageBox.information(self, "Validation", "Pack is valid ✓")
        else:
            QMessageBox.warning(self, "Validation", "\n".join(errs))

    def _pack_rename(self):
        cp = self.state.current_pack()
        if not cp:
            return
        cp.pack.Name = self.pack_name_edit.text()
        cp.dirty = True
        self.refresh_pack_tabs()
        # also refresh current tab's round display? pack name not in round view
        w = self.pack_tabs.currentWidget()
        if isinstance(w, PackTabWidget):
            w.refresh()

    def _sidebar_sort(self):
        w = self.pack_tabs.currentWidget()
        if isinstance(w, PackTabWidget):
            w._sort_by_price()

    def _sidebar_random(self):
        w = self.pack_tabs.currentWidget()
        if isinstance(w, PackTabWidget):
            w._assign_randomly()

    def _refresh_recent(self):
        self.recent_list.clear()
        for p in self.state.recent:
            self.recent_list.addItem(p)

    def _open_recent(self, item):
        path = Path(item.text())
        if not path.exists():
            QMessageBox.warning(self, "Recent", f"File not found: {path}")
            return
        try:
            idx = self.state.open_file(path)
            op = self.state.open_packs[idx]
            w = PackTabWidget(op, self)
            tab_idx = self.pack_tabs.addTab(w, op.title)
            self.pack_tabs.setCurrentIndex(tab_idx)
            self.state.current_index = idx
            self.refresh_pack_tabs()
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))

    def closeEvent(self, event):
        # check unsaved
        unsaved = [op for op in self.state.open_packs if op.dirty]
        if unsaved:
            ret = QMessageBox.question(self, "Unsaved changes", f"{len(unsaved)} pack(s) have unsaved changes. Quit without saving?",
                                       QMessageBox.Yes | QMessageBox.No)
            if ret != QMessageBox.Yes:
                event.ignore()
                return
        event.accept()
