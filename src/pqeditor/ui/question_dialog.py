"""Question edit dialog — handles all question types."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..model import Clue, Question, QuestionType
from ..model import QUESTION_TYPE_LABELS
from ..i18n import tr
from .media_widget import MediaAttachWidget


def _media_type_from_path(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in (".mp3",".wav",".ogg",".flac",".m4a"): return "audio"
    if ext in (".mp4",".avi",".mov",".mkv",".webm"): return "video"
    if ext in (".png",".jpg",".jpeg",".bmp",".gif",".webp"): return "picture"
    return "unknown"


class QuestionDialog(QDialog):
    """Edit a Question. Caller must handle media bytes copying.

    `question` is edited in-place on Save. `media` dict is mutated for new attachments.
    `round_name`/`theme_name` needed to build ZIP paths on attach.
    """
    def __init__(self, question: Question, media: dict, round_name: str, theme_name: str, is_final_round: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Edit question", "Редактировать вопрос"))
        self.question = question
        self.media = media
        self.round_name = round_name
        self.theme_name = theme_name
        self.is_final_round = is_final_round

        # Track pending per media type
        self._pending_q_photo: Optional[tuple[str,str,bytes]] = None
        self._pending_q_video: Optional[tuple[str,str,bytes]] = None
        self._pending_q_audio: Optional[tuple[str,str,bytes]] = None
        self._pending_a_photo: Optional[tuple[str,str,bytes]] = None
        self._pending_a_video: Optional[tuple[str,str,bytes]] = None
        self._pending_a_audio: Optional[tuple[str,str,bytes]] = None
        # compat old
        self._pending_question_media = None
        self._pending_answer_media = None
        # also track pending deletions (paths to remove from media dict if not referenced elsewhere)

        lay = QVBoxLayout(self)

        # Type / Price / Timer row
        top = QHBoxLayout()
        self.type_combo = QComboBox()
        if is_final_round:
            self.type_combo.addItem(tr("Final Question", "Финальный вопрос"))
            self.type_combo.setEnabled(False)
        else:
            # label per type — EN default, RU second, Cat = Cat per user request
            _labels = {
                QuestionType.Normal: tr("Normal", "Обычный"),
                QuestionType.CatInBag: tr("Cat", "Кот в мешке"),
                QuestionType.Auction: tr("Auction", "Аукцион"),
                QuestionType.Quiz: tr("Quiz", "Квиз"),
                QuestionType.LeadingHints: tr("Hints", "Подсказки"),
                QuestionType.GuessNumber: tr("Number", "Число"),
            }
            for qt in QuestionType:
                self.type_combo.addItem(_labels.get(qt, QUESTION_TYPE_LABELS[qt]), qt)
            for i in range(self.type_combo.count()):
                if self.type_combo.itemData(i) == question.Type:
                    self.type_combo.setCurrentIndex(i)
                    break
        self.price_spin = QSpinBox(); self.price_spin.setRange(1, 10000); self.price_spin.setValue(question.Price)
        self.timer_spin = QSpinBox(); self.timer_spin.setRange(0, 600); self.timer_spin.setValue(int(question.TimeToAnswer))
        top.addWidget(QLabel(tr("Type:", "Тип:"))); top.addWidget(self.type_combo, 1)
        top.addWidget(QLabel(tr("Price:", "Цена:"))); top.addWidget(self.price_spin)
        top.addWidget(QLabel(tr("Timer (s):", "Таймер (с):"))); top.addWidget(self.timer_spin)
        lay.addLayout(top)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)

        self.q_text = QTextEdit(question.Text)
        self.q_text.setPlaceholderText(tr("Question text", "Текст вопроса"))
        self.q_group = QGroupBox(tr("Question", "Вопрос"))
        q_lay = QVBoxLayout(self.q_group)
        q_lay.addWidget(QLabel(tr("Text:", "Текст:")))
        q_lay.addWidget(self.q_text)
        self.q_media_widget = MediaAttachWidget(
            tr("Question media — 3 independent buttons", "Медиа вопроса — 3 независимые кнопки"),
            photo_path=question.Picture, video_path=question.Video, audio_path=question.Audio,
            image_params=question.ImageEditParams, audio_params=question.AudioEditParams, video_params=question.VideoEditParams,
            media_bytes_dict=media,
        )
        self.q_media_widget.set_media_bytes(media, "")
        q_lay.addWidget(self.q_media_widget)
        lay.addWidget(self.q_group)

        self.a_text = QTextEdit(question.Answer.Text)
        self.a_text.setPlaceholderText(tr("Answer text", "Текст ответа"))
        self.a_group = QGroupBox(tr("Answer", "Ответ"))
        a_lay = QVBoxLayout(self.a_group)
        a_lay.addWidget(QLabel(tr("Text:", "Текст:")))
        a_lay.addWidget(self.a_text)
        self.a_media_widget = MediaAttachWidget(
            tr("Answer media — photo / video / audio", "Медиа ответа — фото / видео / аудио"),
            photo_path=question.Answer.Picture, video_path=question.Answer.Video, audio_path=question.Answer.Audio,
            image_params=question.Answer.ImageEditParams, audio_params=question.Answer.AudioEditParams, video_params=question.Answer.VideoEditParams,
            media_bytes_dict=media,
        )
        self.a_media_widget.set_media_bytes(media, "")
        a_lay.addWidget(self.a_media_widget)
        lay.addWidget(self.a_group)

        # Type-specific area
        self.type_stack = QWidget()
        self.type_stack_lay = QVBoxLayout(self.type_stack)
        self.type_stack_lay.setContentsMargins(0,0,0,0)
        lay.addWidget(self.type_stack)

        self.quiz_group = QGroupBox(tr("Quiz options (up to 4)", "Варианты квиза (до 4)"))
        qz_lay = QVBoxLayout(self.quiz_group)
        self.quiz_edits: list[QLineEdit] = []
        self.quiz_radios: list[QCheckBox] = []
        for i in range(4):
            row = QHBoxLayout()
            cb = QCheckBox(tr("Correct", "Верно"))
            le = QLineEdit()
            le.setPlaceholderText(tr(f"Option {i+1}", f"Вариант {i+1}"))
            row.addWidget(le, 1); row.addWidget(cb)
            qz_lay.addLayout(row)
            self.quiz_edits.append(le)
            self.quiz_radios.append(cb)
            cb.toggled.connect(lambda checked, idx=i: self._quiz_radio_changed(idx, checked))
        for i, txt in enumerate(question.MultipleChoice):
            if i < 4:
                self.quiz_edits[i].setText(txt)
        if 0 <= question.MultipleChoiceIndex < 4:
            self.quiz_radios[question.MultipleChoiceIndex].setChecked(True)

        self.hints_group = QGroupBox(tr("Hints — up to 5 (drag to reorder)", "Подсказки — до 5 (перетаскивание)"))
        hints_lay = QVBoxLayout(self.hints_group)
        self.hints_list = QListWidget()
        self.hints_list.setDragDropMode(QListWidget.InternalMove)
        hints_lay.addWidget(self.hints_list)
        hint_edit_row = QHBoxLayout()
        self.hint_text_edit = QLineEdit(); self.hint_text_edit.setPlaceholderText(tr("Hint text", "Текст подсказки"))
        self.hint_price_spin = QSpinBox(); self.hint_price_spin.setRange(1, 10000); self.hint_price_spin.setValue(50)
        self.hint_pic_label = QLabel(tr("(no picture)", "(нет картинки)"))
        hint_edit_row.addWidget(self.hint_text_edit, 1); hint_edit_row.addWidget(QLabel(tr("Price:", "Цена:"))); hint_edit_row.addWidget(self.hint_price_spin)
        hints_lay.addLayout(hint_edit_row)
        hint_btn_row = QHBoxLayout()
        self.btn_hint_add = QPushButton(tr("Add hint", "Добавить"))
        self.btn_hint_update = QPushButton(tr("Update", "Обновить"))
        self.btn_hint_del = QPushButton(tr("Delete", "Удалить"))
        self.btn_hint_up = QPushButton("↑")
        self.btn_hint_down = QPushButton("↓")
        for b in (self.btn_hint_add, self.btn_hint_update, self.btn_hint_del, self.btn_hint_up, self.btn_hint_down):
            hint_btn_row.addWidget(b)
        hints_lay.addLayout(hint_btn_row)
        hints_lay.addWidget(self.hint_pic_label)
        self.btn_hint_pic = QPushButton(tr("Attach picture to hint…", "Прикрепить картинку…"))
        hints_lay.addWidget(self.btn_hint_pic)
        for c in question.RevealingClues:
            item = QListWidgetItem(f"[{c.Price}] {c.Text}" + (f" 📷 {c.Picture}" if c.Picture else ""))
            item.setData(Qt.UserRole, (c.Text, c.Picture, c.Price))
            self.hints_list.addItem(item)
        self._pending_hint_pics: dict[int, tuple[str, bytes]] = {}
        self._hint_updating = False
        self.btn_hint_add.clicked.connect(self._hint_add)
        self.btn_hint_update.clicked.connect(self._hint_update)
        self.btn_hint_del.clicked.connect(self._hint_del)
        self.btn_hint_up.clicked.connect(lambda: self._hint_move(-1))
        self.btn_hint_down.clicked.connect(lambda: self._hint_move(1))
        self.btn_hint_pic.clicked.connect(self._hint_attach_pic)
        self.hints_list.itemClicked.connect(self._hint_select)
        self.hints_list.currentRowChanged.connect(self._on_hint_row_changed)
        self.hint_text_edit.textChanged.connect(self._on_hint_text_changed)
        self.hint_price_spin.valueChanged.connect(self._on_hint_price_changed)
        self._update_hint_add_enabled()

        self.guess_label = QLabel(tr("Answer must be numeric for Guess the Number.", "Ответ должен быть числом для Числа."))
        self.guess_label.setStyleSheet("color: #a00;")

        self._on_type_changed()

        btns = QDialogButtonBox()
        self.btn_save = QPushButton(tr("Save", "Сохранить"))
        self.btn_delete = QPushButton(tr("Delete question", "Удалить вопрос"))
        self.btn_delete.setStyleSheet("color: #c00;")
        self.btn_cancel = QPushButton(tr("Cancel", "Отмена"))
        btns.addButton(self.btn_save, QDialogButtonBox.AcceptRole)
        btns.addButton(self.btn_delete, QDialogButtonBox.DestructiveRole)
        btns.addButton(self.btn_cancel, QDialogButtonBox.RejectRole)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        self.btn_delete.clicked.connect(self._delete)
        self.btn_cancel.clicked.connect(self.reject)
        lay.addWidget(btns)

        # Hook media change
        self.q_media_widget.on_change = self._on_q_media_change
        self.a_media_widget.on_change = self._on_a_media_change

        self._delete_requested = False
        self.resize(700, 750)

    # -- quiz --
    def _quiz_radio_changed(self, idx: int, checked: bool):
        if checked:
            for i, cb in enumerate(self.quiz_radios):
                if i != idx:
                    cb.blockSignals(True); cb.setChecked(False); cb.blockSignals(False)

    def _hint_add(self):
        if self.hints_list.count() >= 5:
            QMessageBox.warning(self, tr("Hint", "Подсказка"), tr("Maximum 5 hints", "Максимум 5 подсказок"))
            return
        txt = self.hint_text_edit.text().strip()
        if not txt:
            QMessageBox.warning(self, tr("Hint", "Подсказка"), tr("Hint text is required.", "Нужен текст подсказки."))
            return
        price = self.hint_price_spin.value()
        item = QListWidgetItem(f"[{price}] {txt}")
        item.setData(Qt.UserRole, (txt, "", price))
        self.hints_list.addItem(item)
        self.hints_list.setCurrentRow(self.hints_list.count()-1)
        self.hint_text_edit.clear()
        self._update_hint_add_enabled()

    def _hint_select(self, item: QListWidgetItem):
        self._hint_updating = True
        txt, pic, price = item.data(Qt.UserRole)
        self.hint_text_edit.blockSignals(True)
        self.hint_price_spin.blockSignals(True)
        self.hint_text_edit.setText(txt)
        self.hint_price_spin.setValue(price)
        self.hint_price_spin.blockSignals(False)
        self.hint_text_edit.blockSignals(False)
        self.hint_pic_label.setText(pic or tr("(no picture)", "(нет картинки)"))
        self._hint_updating = False

    def _on_hint_text_changed(self, txt: str):
        if self._hint_updating: return
        row = self.hints_list.currentRow()
        if row < 0: return
        # auto-update without Update button
        self._auto_update_current_hint()

    def _on_hint_price_changed(self, val: int):
        if self._hint_updating: return
        row = self.hints_list.currentRow()
        if row < 0: return
        self._auto_update_current_hint()

    def _on_hint_row_changed(self, row: int):
        # limit button state
        self._update_hint_add_enabled()

    def _auto_update_current_hint(self):
        row = self.hints_list.currentRow()
        if row < 0: return
        txt = self.hint_text_edit.text().strip()
        # allow empty while typing? don't update if empty to avoid clearing
        if not txt:
            return
        price = self.hint_price_spin.value()
        item = self.hints_list.item(row)
        if not item: return
        old_txt, old_pic, _old_price = item.data(Qt.UserRole)
        pic = old_pic
        if row in self._pending_hint_pics:
            pic = self._pending_hint_pics[row][0]
        item.setData(Qt.UserRole, (txt, pic, price))
        item.setText(f"[{price}] {txt}" + (f" 📷 {pic}" if pic else ""))

    def _update_hint_add_enabled(self):
        has_max = self.hints_list.count() >= 5
        self.btn_hint_add.setEnabled(not has_max)
        self.btn_hint_add.setToolTip(tr("Maximum 5 hints", "Максимум 5 подсказок") if has_max else tr("Add hint", "Добавить подсказку"))

    def _hint_update(self):
        row = self.hints_list.currentRow()
        if row < 0:
            return
        txt = self.hint_text_edit.text().strip()
        if not txt:
            QMessageBox.warning(self, tr("Hint", "Подсказка"), tr("Hint text is required.", "Нужен текст подсказки."))
            return
        price = self.hint_price_spin.value()
        item = self.hints_list.item(row)
        old_txt, old_pic, _old_price = item.data(Qt.UserRole)
        pic = old_pic
        if row in self._pending_hint_pics:
            pic = self._pending_hint_pics[row][0]
        item.setData(Qt.UserRole, (txt, pic, price))
        item.setText(f"[{price}] {txt}" + (f" 📷 {pic}" if pic else ""))

    def _hint_del(self):
        row = self.hints_list.currentRow()
        if row >= 0:
            self.hints_list.takeItem(row)
            new_pending = {}
            for k, v in self._pending_hint_pics.items():
                if k < row: new_pending[k]=v
                elif k > row: new_pending[k-1]=v
            self._pending_hint_pics = new_pending
            self._update_hint_add_enabled()

    def _hint_move(self, delta: int):
        row = self.hints_list.currentRow()
        if row < 0: return
        new_row = row + delta
        if 0 <= new_row < self.hints_list.count():
            item = self.hints_list.takeItem(row)
            self.hints_list.insertItem(new_row, item)
            self.hints_list.setCurrentRow(new_row)
            if row in self._pending_hint_pics or new_row in self._pending_hint_pics:
                a = self._pending_hint_pics.pop(row, None)
                b = self._pending_hint_pics.pop(new_row, None)
                if a: self._pending_hint_pics[new_row]=a
                if b: self._pending_hint_pics[row]=b

    def _hint_attach_pic(self):
        row = self.hints_list.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Hint", "Select a hint first.")
            return
        from PySide6.QtWidgets import QFileDialog
        fn, _ = QFileDialog.getOpenFileName(self, "Hint picture", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if not fn:
            return
        data = Path(fn).read_bytes()
        fname = Path(fn).name
        # build arc path: <Round>/<Theme>/<Price>/question/clue<idx>_<fname>
        # price may change after reorder — use current question price as dir price component
        price_dir = self.price_spin.value()
        arc = f"{self.round_name}/{self.theme_name}/{price_dir}/question/clue{row+1}_{fname}"
        self._pending_hint_pics[row] = (arc, data)
        self.media[arc] = data  # immediately add to media dict
        # update item
        item = self.hints_list.item(row)
        txt, _old_pic, price = item.data(Qt.UserRole)
        item.setData(Qt.UserRole, (txt, arc, price))
        item.setText(f"[{price}] {txt} 📷 {arc}")
        self.hint_pic_label.setText(arc)

    # -- media change handlers — 3 независимые типа --
    def _on_q_media_change(self, path: str, kind: str):
        # kind like photo_attach / video_attach / audio_attach / *_clear / *_settings
        if "attach" in kind and path:
            if not os.path.exists(path): return
            data = Path(path).read_bytes()
            fname = Path(path).name
            arc = f"{self.round_name}/{self.theme_name}/{self.price_spin.value()}/question/{fname}"
            if kind.startswith("photo"): 
                self._pending_q_photo = (path, arc, data)
                self.q_media_widget.photo_path = arc
            elif kind.startswith("video"):
                self._pending_q_video = (path, arc, data)
                self.q_media_widget.video_path = arc
            else:
                self._pending_q_audio = (path, arc, data)
                self.q_media_widget.audio_path = arc
            # need to stage bytes already? will do on save, but also put to media dict preview
            self.media[arc] = data
        elif "clear" in kind:
            if kind.startswith("photo"): self._pending_q_photo = None; self.q_media_widget.photo_path = ""
            elif kind.startswith("video"): self._pending_q_video = None; self.q_media_widget.video_path = ""
            else: self._pending_q_audio = None; self.q_media_widget.audio_path = ""
            # clear is signalled by empty path in widget — will be applied on save
        elif "settings" in kind:
            pass

    def _on_a_media_change(self, path: str, kind: str):
        if "attach" in kind and path:
            if not os.path.exists(path): return
            data = Path(path).read_bytes()
            fname = Path(path).name
            arc = f"{self.round_name}/{self.theme_name}/{self.price_spin.value()}/answer/{fname}"
            if kind.startswith("photo"):
                self._pending_a_photo = (path, arc, data)
                self.a_media_widget.photo_path = arc
            elif kind.startswith("video"):
                self._pending_a_video = (path, arc, data)
                self.a_media_widget.video_path = arc
            else:
                self._pending_a_audio = (path, arc, data)
                self.a_media_widget.audio_path = arc
            self.media[arc] = data
        elif "clear" in kind:
            if kind.startswith("photo"): self._pending_a_photo = None; self.a_media_widget.photo_path = ""
            elif kind.startswith("video"): self._pending_a_video = None; self.a_media_widget.video_path = ""
            else: self._pending_a_audio = None; self.a_media_widget.audio_path = ""
        elif "settings" in kind:
            pass

    def _on_type_changed(self):
        # Clear and rebuild type stack
        while self.type_stack_lay.count():
            item = self.type_stack_lay.takeAt(0)
            w = item.widget()
            if w: w.setParent(None)
        if self.is_final_round:
            # no type-specific UI for final
            self.q_group.setVisible(True)
            self.price_spin.setEnabled(False)
            self.timer_spin.setEnabled(False)
            return
        # get selected type
        data = self.type_combo.currentData()
        if data is None:
            data = self.question.Type
        try:
            qt = QuestionType(data)
        except:
            qt = QuestionType.Normal
        # visibility per type
        is_quiz = qt == QuestionType.Quiz
        is_hints = qt == QuestionType.LeadingHints
        is_guess = qt == QuestionType.GuessNumber

        # Timer / Price / Question text locking
        if qt in (QuestionType.Quiz, QuestionType.LeadingHints, QuestionType.GuessNumber):
            self.timer_spin.setEnabled(False)
            self.timer_spin.setValue(0)
        else:
            self.timer_spin.setEnabled(True)
            if self.question.TimeToAnswer == 0 and qt in (QuestionType.Normal, QuestionType.CatInBag, QuestionType.Auction):
                self.timer_spin.setValue(10)
        if qt == QuestionType.LeadingHints:
            self.price_spin.setEnabled(False)
            self.q_group.setVisible(False)
        elif qt == QuestionType.Normal and False:
            pass
        else:
            # Final price locked? handled via is_final_round above
            self.price_spin.setEnabled(qt != QuestionType.LeadingHints)
            self.q_group.setVisible(qt != QuestionType.LeadingHints)

        if is_quiz:
            self.type_stack_lay.addWidget(self.quiz_group)
            self.quiz_group.setVisible(True)
        if is_hints:
            self.type_stack_lay.addWidget(self.hints_group)
            self.hints_group.setVisible(True)
        if is_guess:
            self.type_stack_lay.addWidget(self.guess_label)

    def _save(self):
        # Validation
        price = self.price_spin.value()
        # Collect quiz options
        if not self.is_final_round:
            data = self.type_combo.currentData()
            qt = QuestionType(data) if data is not None else self.question.Type
        else:
            qt = QuestionType.Normal

        if qt == QuestionType.Quiz:
            opts = [e.text().strip() for e in self.quiz_edits]
            opts = [o for o in opts if o]
            if len(opts) < 2:
                QMessageBox.warning(self, "Validation", "Quiz must have at least 2 options.")
                return
            checked = [i for i,cb in enumerate(self.quiz_radios) if cb.isChecked()]
            # map checked index to position in non-empty opts? For simplicity require all 4 filled if quiz; spec says up to 4.
            # We'll validate that checked corresponds to a non-empty
            # Find which original index is checked and ensure that edit has text
            # Simpler: require all filled for now? No — spec allows up to 4.
            # We'll compact opts and adjust index: find first checked with text
            # If user left some empty, we need to map correctly
            # Better: build opts including empty slots but filter? Let's just require 2-4 non-empty and that checked index has text
            # To avoid complexity, if checked is -1, error; if checked edit is empty, error.
            if not checked:
                QMessageBox.warning(self, "Validation", "Quiz: select the correct option.")
                return
            ci = checked[0]
            if not self.quiz_edits[ci].text().strip():
                QMessageBox.warning(self, "Validation", "Correct option cannot be empty.")
                return
            # Also ensure opts count matches original positions? We'll keep MultipleChoice as compacted non-empty list and map index accordingly
            # Need to remap checked index to compacted index
            # Compact: iterate edits, collect non-empty, and if checked index is among them, find its new position
            compact = []
            new_idx = -1
            for i, e in enumerate(self.quiz_edits):
                t = e.text().strip()
                if t:
                    if i == ci:
                        new_idx = len(compact)
                    compact.append(t)
            if new_idx == -1:
                QMessageBox.warning(self, "Validation", "Correct option must be non-empty.")
                return
            # store for later apply
            self._quiz_compact = compact
            self._quiz_index = new_idx
        if qt == QuestionType.LeadingHints:
            if self.hints_list.count() == 0:
                QMessageBox.warning(self, "Validation", "Leading Hints needs at least 1 hint.")
                return
            if self.hints_list.count() > 5:
                QMessageBox.warning(self, "Validation", "At most 5 hints.")
                return
        if qt == QuestionType.GuessNumber:
            txt = self.a_text.toPlainText().strip()
            try:
                float(txt)
            except:
                QMessageBox.warning(self, "Validation", "Guess the Number answer must be numeric.")
                return
        # Apply to question
        self.question.Price = price
        if not self.is_final_round:
            self.question.Type = qt
            self.question.IsFinal = False
        else:
            self.question.IsFinal = True
            self.question.Type = QuestionType.Normal
        # Timer: if enabled, take value else 0
        if self.timer_spin.isEnabled():
            self.question.TimeToAnswer = float(self.timer_spin.value())
        else:
            self.question.TimeToAnswer = 0.0
        # Texts
        if qt != QuestionType.LeadingHints:
            self.question.Text = self.q_text.toPlainText()
        else:
            self.question.Text = ""
            # Price for Leading Hints = max clue price
            # compute from hints
            max_price = 0
            for i in range(self.hints_list.count()):
                _txt, _pic, price_c = self.hints_list.item(i).data(Qt.UserRole)
                max_price = max(max_price, price_c)
            self.question.Price = max_price
        self.question.Answer.Text = self.a_text.toPlainText()

        # Media handling — 3 независимых типа (фото/видео/аудио не блокируют друг друга)
        def apply_side(widget, q_pic, q_aud, q_vid, pend_photo, pend_video, pend_audio):
            # photo
            new_pic = widget.photo_path
            if pend_photo and pend_photo[1]==new_pic:
                self.media[new_pic]=pend_photo[2]
            # video
            new_vid = widget.video_path
            if pend_video and pend_video[1]==new_vid:
                self.media[new_vid]=pend_video[2]
            # audio
            new_aud = widget.audio_path
            if pend_audio and pend_audio[1]==new_aud:
                self.media[new_aud]=pend_audio[2]
            # if widget path empty -> cleared, keep empty; else keep existing path if no pending but path exists
            # also handle case where path was original existing (already in media dict) — keep it
            return new_pic, new_aud, new_vid

        q_new_pic, q_new_aud, q_new_vid = apply_side(self.q_media_widget, self.question.Picture, self.question.Audio, self.question.Video, self._pending_q_photo, self._pending_q_video, self._pending_q_audio)
        self.question.Picture = q_new_pic
        self.question.Audio = q_new_aud
        self.question.Video = q_new_vid
        self.question.ImageEditParams = self.q_media_widget.image_params
        self.question.AudioEditParams = self.q_media_widget.audio_params
        self.question.VideoEditParams = self.q_media_widget.video_params

        a_new_pic, a_new_aud, a_new_vid = apply_side(self.a_media_widget, self.question.Answer.Picture, self.question.Answer.Audio, self.question.Answer.Video, self._pending_a_photo, self._pending_a_video, self._pending_a_audio)
        self.question.Answer.Picture = a_new_pic
        self.question.Answer.Audio = a_new_aud
        self.question.Answer.Video = a_new_vid
        self.question.Answer.ImageEditParams = self.a_media_widget.image_params
        self.question.Answer.AudioEditParams = self.a_media_widget.audio_params
        self.question.Answer.VideoEditParams = self.a_media_widget.video_params

        # Type-specific apply
        if qt == QuestionType.Quiz:
            self.question.MultipleChoice = self._quiz_compact
            self.question.MultipleChoiceIndex = self._quiz_index
            self.question.RevealingClues = []
        elif qt == QuestionType.LeadingHints:
            clues = []
            for i in range(self.hints_list.count()):
                txt, pic, price_c = self.hints_list.item(i).data(Qt.UserRole)
                clues.append(Clue(Text=txt, Picture=pic, Price=price_c))
            self.question.RevealingClues = clues
            self.question.MultipleChoice = []
            self.question.MultipleChoiceIndex = -1
        else:
            self.question.MultipleChoice = []
            self.question.MultipleChoiceIndex = -1
            if qt != QuestionType.LeadingHints:
                self.question.RevealingClues = []

        self.accept()

    def _delete(self):
        ret = QMessageBox.question(self, "Delete question", "Delete this question? This cannot be undone except via Undo.",
                                   QMessageBox.Yes | QMessageBox.No)
        if ret == QMessageBox.Yes:
            self._delete_requested = True
            self.accept()

    @property
    def delete_requested(self) -> bool:
        return self._delete_requested
