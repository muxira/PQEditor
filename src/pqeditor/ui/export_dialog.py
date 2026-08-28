"""Export dialog — PackMetadata form from Step 5."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from ..model import AgeRating, Category, Difficulty, Language, Pack
from ..model import AGERATING_LABELS, CATEGORY_LABELS, DIFFICULTY_LABELS, LANGUAGE_LABELS
from ..model import AGERATING_BY_LABEL, CATEGORY_BY_LABEL, DIFFICULTY_BY_LABEL, LANGUAGE_BY_LABEL
from ..i18n import tr


class ExportDialog(QDialog):
    def __init__(self, pack: Pack, media_keys: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Export pack — metadata", "Экспорт пака — метаданные"))
        self.pack = pack
        self._chosen_cover: str = pack.Icon  # ZIP path or ""
        self._chosen_cover_bytes: Optional[bytes] = None
        self._chosen_cover_filename: str = ""

        form = QFormLayout()
        self.title_edit = QLineEdit(pack.Name)
        self.desc_edit = QTextEdit(pack.Description)
        self.desc_edit.setPlaceholderText(tr("Pack description", "Описание пака"))

        cover_row = QHBoxLayout()
        self.cover_label = QLabel(pack.Icon or tr("(no cover)", "(нет обложки)"))
        self.cover_label.setStyleSheet("color: #555;")
        btn_cover = QPushButton(tr("Choose cover…", "Выбрать обложку…"))
        btn_cover_clear = QPushButton(tr("Clear", "Очистить"))
        cover_row.addWidget(self.cover_label, 1)
        cover_row.addWidget(btn_cover)
        cover_row.addWidget(btn_cover_clear)
        btn_cover.clicked.connect(self._choose_cover)
        btn_cover_clear.clicked.connect(self._clear_cover)

        # Enums
        self.diff_combo = QComboBox()
        for d in Difficulty:
            self.diff_combo.addItem(DIFFICULTY_LABELS[d])
        self.diff_combo.setCurrentText(DIFFICULTY_LABELS[pack.Difficulty])

        self.cat_combo = QComboBox()
        for c in Category:
            self.cat_combo.addItem(CATEGORY_LABELS[c])
        self.cat_combo.setCurrentText(CATEGORY_LABELS[pack.Category])

        self.lang_combo = QComboBox()
        for lang in Language:
            self.lang_combo.addItem(LANGUAGE_LABELS[lang])
        self.lang_combo.setCurrentText(LANGUAGE_LABELS[pack.Language])

        self.age_combo = QComboBox()
        for a in AgeRating:
            self.age_combo.addItem(AGERATING_LABELS[a])
        self.age_combo.setCurrentText(AGERATING_LABELS[pack.AgeRating])

        form.addRow(tr("Title *", "Название *"), self.title_edit)
        form.addRow(tr("Description", "Описание"), self.desc_edit)
        form.addRow(tr("Cover image", "Обложка"), cover_row)
        form.addRow(tr("Difficulty", "Сложность"), self.diff_combo)
        form.addRow(tr("Category", "Категория"), self.cat_combo)
        form.addRow(tr("Language", "Язык"), self.lang_combo)
        form.addRow(tr("Age rating", "Возраст"), self.age_combo)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(btns)
        self.resize(500, 380)

    def _choose_cover(self):
        fn, _ = QFileDialog.getOpenFileName(self, tr("Choose cover image", "Выбрать обложку"), "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if fn:
            self._chosen_cover_filename = Path(fn).name
            try:
                self._chosen_cover_bytes = Path(fn).read_bytes()
            except Exception:
                self._chosen_cover_bytes = None
            self.cover_label.setText(Path(fn).name + tr(" (will be saved as root)", " (сохранится в корне)"))
            self._chosen_cover = Path(fn).name

    def _clear_cover(self):
        self._chosen_cover = ""
        self._chosen_cover_bytes = None
        self._chosen_cover_filename = ""
        self.cover_label.setText(tr("(no cover)", "(нет обложки)"))

    def apply_to_pack(self, pack: Pack) -> Optional[tuple[str, bytes]]:
        """Apply dialog values to pack. Returns (cover_filename, bytes) if a new file was chosen."""
        pack.Name = self.title_edit.text().strip()
        pack.Description = self.desc_edit.toPlainText()
        pack.Difficulty = DIFFICULTY_BY_LABEL[self.diff_combo.currentText()]
        pack.Category = CATEGORY_BY_LABEL[self.cat_combo.currentText()]
        pack.Language = LANGUAGE_BY_LABEL[self.lang_combo.currentText()]
        pack.AgeRating = AGERATING_BY_LABEL[self.age_combo.currentText()]
        # Cover handling
        if self._chosen_cover_bytes is not None and self._chosen_cover_filename:
            # caller should add to media dict
            pack.Icon = self._chosen_cover_filename
            return (self._chosen_cover_filename, self._chosen_cover_bytes)
        else:
            # no new file — keep existing Icon unless cleared
            if self._chosen_cover == "" and pack.Icon != "":
                pack.Icon = ""
            elif self._chosen_cover and self._chosen_cover != pack.Icon:
                # user typed? not possible — keep
                pass
            return None

    def validate(self) -> Optional[str]:
        if not self.title_edit.text().strip():
            return tr("Title is required.", "Название обязательно.")
        return None

    def accept(self):
        err = self.validate()
        if err:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, tr("Validation", "Проверка"), err)
            return
        super().accept()
