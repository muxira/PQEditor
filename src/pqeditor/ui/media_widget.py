"""Media attachment widget with preview + interactive per-media settings."""
import os
import math
import tempfile
import struct
import wave
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, QRectF, Signal, QPointF, QUrl
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..model import AudioEditParams, ImageEditParams, VideoEditParams
from ..i18n import tr


# ---------- Interactive crop view ----------

class CropView(QWidget):
    changed = Signal(float, float, float, float)

    def __init__(self, pixmap: QPixmap, cropL=0.0, cropT=0.0, cropR=1.0, cropB=1.0, parent=None):
        super().__init__(parent)
        self.orig_pix = pixmap
        self.cropL, self.cropT, self.cropR, self.cropB = cropL, cropT, cropR, cropB
        self.setMinimumSize(320, 220)
        self._drag = None
        self._start = None
        self._orig_crop = None
        self.setMouseTracking(True)

    def _image_rect(self) -> QRectF:
        if self.orig_pix.isNull():
            return QRectF(0,0,self.width(), self.height())
        pw, ph = self.orig_pix.width(), self.orig_pix.height()
        scale = min(self.width()/pw, self.height()/ph)
        w, h = pw*scale, ph*scale
        x = (self.width()-w)/2
        y = (self.height()-h)/2
        return QRectF(x,y,w,h)

    def _crop_rect(self) -> QRectF:
        ir = self._image_rect()
        return QRectF(
            ir.x() + self.cropL*ir.width(),
            ir.y() + self.cropT*ir.height(),
            (self.cropR-self.cropL)*ir.width(),
            (self.cropB-self.cropT)*ir.height(),
        )

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#222"))
        ir = self._image_rect()
        if not self.orig_pix.isNull():
            p.drawPixmap(ir.toRect(), self.orig_pix)
        else:
            p.setPen(QColor("#888"))
            p.drawText(self.rect(), Qt.AlignCenter, tr("No image", "Нет изображения"))
            return
        cr = self._crop_rect()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0,0,0,120))
        p.drawRect(QRectF(ir.x(), ir.y(), ir.width(), cr.y()-ir.y()))
        p.drawRect(QRectF(ir.x(), cr.bottom(), ir.width(), ir.bottom()-cr.bottom()))
        p.drawRect(QRectF(ir.x(), cr.y(), cr.x()-ir.x(), cr.height()))
        p.drawRect(QRectF(cr.right(), cr.y(), ir.right()-cr.right(), cr.height()))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor("#00E5FF"), 2))
        p.drawRect(cr)
        p.setPen(QPen(QColor(255,255,255,90), 1, Qt.DashLine))
        for i in (1,2):
            p.drawLine(QPointF(cr.x()+cr.width()*i/3, cr.y()), QPointF(cr.x()+cr.width()*i/3, cr.bottom()))
            p.drawLine(QPointF(cr.x(), cr.y()+cr.height()*i/3), QPointF(cr.right(), cr.y()+cr.height()*i/3))
        p.setPen(QPen(QColor("#00E5FF"), 1))
        p.setBrush(QColor("#00E5FF"))
        hs = 8
        for pt in [cr.topLeft(), cr.topRight(), cr.bottomLeft(), cr.bottomRight(),
                   QPointF(cr.center().x(), cr.y()), QPointF(cr.center().x(), cr.bottom()),
                   QPointF(cr.x(), cr.center().y()), QPointF(cr.right(), cr.center().y())]:
            p.drawRect(QRectF(pt.x()-hs/2, pt.y()-hs/2, hs, hs))
        p.setPen(QColor("#FFFFFF"))
        p.drawText(QRectF(ir.x(), ir.y()-18, ir.width(), 16), Qt.AlignCenter, tr("Drag frame / corners — crop is live", "Тяни рамку / углы — сразу видно обрезку"))

    def mousePressEvent(self, e):
        if e.button()!=Qt.LeftButton or self.orig_pix.isNull():
            return
        cr = self._crop_rect()
        pos = e.position()
        hs = 10
        def near(pt): return abs(pos.x()-pt.x())<hs and abs(pos.y()-pt.y())<hs
        if near(cr.topLeft()): self._drag='tl'
        elif near(cr.topRight()): self._drag='tr'
        elif near(cr.bottomLeft()): self._drag='bl'
        elif near(cr.bottomRight()): self._drag='br'
        elif near(QPointF(cr.center().x(), cr.y())): self._drag='t'
        elif near(QPointF(cr.center().x(), cr.bottom())): self._drag='b'
        elif near(QPointF(cr.x(), cr.center().y())): self._drag='l'
        elif near(QPointF(cr.right(), cr.center().y())): self._drag='r'
        elif cr.contains(pos): self._drag='move'
        else: self._drag=None; return
        self._start = pos
        self._orig_crop = (self.cropL,self.cropT,self.cropR,self.cropB)

    def mouseMoveEvent(self, e):
        if self._drag is None or self._start is None:
            if self.orig_pix.isNull(): return
            cr = self._crop_rect(); pos=e.position(); hs=10
            def near(pt): return abs(pos.x()-pt.x())<hs and abs(pos.y()-pt.y())<hs
            if near(cr.topLeft()) or near(cr.bottomRight()): self.setCursor(Qt.SizeFDiagCursor)
            elif near(cr.topRight()) or near(cr.bottomLeft()): self.setCursor(Qt.SizeBDiagCursor)
            elif near(QPointF(cr.center().x(), cr.y())) or near(QPointF(cr.center().x(), cr.bottom())): self.setCursor(Qt.SizeVerCursor)
            elif near(QPointF(cr.x(), cr.center().y())) or near(QPointF(cr.right(), cr.center().y())): self.setCursor(Qt.SizeHorCursor)
            elif cr.contains(pos): self.setCursor(Qt.SizeAllCursor)
            else: self.setCursor(Qt.ArrowCursor)
            return
        ir = self._image_rect()
        dx = (e.position().x()-self._start.x())/ir.width()
        dy = (e.position().y()-self._start.y())/ir.height()
        L,T,R,B = self._orig_crop
        if self._drag=='move':
            w=R-L; h=B-T
            L = max(0, min(1-w, L+dx)); T = max(0, min(1-h, T+dy))
            R = L+w; B = T+h
        elif self._drag=='l': L = max(0, min(R-0.05, L+dx))
        elif self._drag=='r': R = min(1, max(L+0.05, R+dx))
        elif self._drag=='t': T = max(0, min(B-0.05, T+dy))
        elif self._drag=='b': B = min(1, max(T+0.05, B+dy))
        elif self._drag=='tl': L = max(0, min(R-0.05, L+dx)); T = max(0, min(B-0.05, T+dy))
        elif self._drag=='tr': R = min(1, max(L+0.05, R+dx)); T = max(0, min(B-0.05, T+dy))
        elif self._drag=='bl': L = max(0, min(R-0.05, L+dx)); B = min(1, max(T+0.05, B+dy))
        elif self._drag=='br': R = min(1, max(L+0.05, R+dx)); B = min(1, max(T+0.05, B+dy))
        self.cropL, self.cropT, self.cropR, self.cropB = L,T,R,B
        self.update()
        self.changed.emit(L,T,R,B)

    def mouseReleaseEvent(self, e):
        self._drag=None; self._start=None

    def set_crop(self, L,T,R,B):
        self.cropL, self.cropT, self.cropR, self.cropB = L,T,R,B
        self.update()


class ImageSettingsDialog(QDialog):
    def __init__(self, params: ImageEditParams, pixmap: Optional[QPixmap]=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Photo — interactive crop", "Фото — интерактивная обрезка"))
        self.resize(720, 520)
        lay = QVBoxLayout(self)
        if pixmap is None or pixmap.isNull():
            pixmap = QPixmap(640, 360); pixmap.fill(QColor("#333"))
        self.crop_view = CropView(pixmap, params.CropL, params.CropT, params.CropR, params.CropB)
        lay.addWidget(self.crop_view, 1)
        form = QFormLayout()
        self.cropL = QDoubleSpinBox(); self.cropL.setRange(0,1); self.cropL.setSingleStep(0.02); self.cropL.setValue(params.CropL)
        self.cropT = QDoubleSpinBox(); self.cropT.setRange(0,1); self.cropT.setSingleStep(0.02); self.cropT.setValue(params.CropT)
        self.cropR = QDoubleSpinBox(); self.cropR.setRange(0,1); self.cropR.setSingleStep(0.02); self.cropR.setValue(params.CropR)
        self.cropB = QDoubleSpinBox(); self.cropB.setRange(0,1); self.cropB.setSingleStep(0.02); self.cropB.setValue(params.CropB)
        self.zoom = QDoubleSpinBox(); self.zoom.setRange(0.1,5.0); self.zoom.setSingleStep(0.1); self.zoom.setValue(params.Zoom)
        self.flipX = QCheckBox(); self.flipX.setChecked(params.FlipX)
        self.flipY = QCheckBox(); self.flipY.setChecked(params.FlipY)
        for w, name in [(self.cropL,"Crop L"),(self.cropT,"Crop T"),(self.cropR,"Crop R"),(self.cropB,"Crop B")]:
            form.addRow(name, w)
        form.addRow("Zoom", self.zoom)
        form.addRow("Flip X", self.flipX); form.addRow("Flip Y", self.flipY)
        lay.addLayout(form)
        row = QHBoxLayout(); btn_reset = QPushButton(tr("Reset (full frame)", "Сброс (весь кадр)")); row.addWidget(btn_reset); row.addStretch()
        lay.addLayout(row)
        btn_reset.clicked.connect(lambda: [self.cropL.setValue(0), self.cropT.setValue(0), self.cropR.setValue(1), self.cropB.setValue(1)])
        self.crop_view.changed.connect(self._from_view)
        for sp in (self.cropL, self.cropT, self.cropR, self.cropB):
            sp.valueChanged.connect(self._to_view)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _from_view(self, L,T,R,B):
        self.cropL.blockSignals(True); self.cropT.blockSignals(True); self.cropR.blockSignals(True); self.cropB.blockSignals(True)
        self.cropL.setValue(L); self.cropT.setValue(T); self.cropR.setValue(R); self.cropB.setValue(B)
        self.cropL.blockSignals(False); self.cropT.blockSignals(False); self.cropR.blockSignals(False); self.cropB.blockSignals(False)

    def _to_view(self):
        self.crop_view.set_crop(self.cropL.value(), self.cropT.value(), self.cropR.value(), self.cropB.value())

    def result_params(self) -> ImageEditParams:
        return ImageEditParams(CropL=self.cropL.value(), CropT=self.cropT.value(), CropR=self.cropR.value(), CropB=self.cropB.value(), Zoom=self.zoom.value(), FlipX=self.flipX.isChecked(), FlipY=self.flipY.isChecked())


# ---------- Waveform / timeline ----------

class WaveformWidget(QWidget):
    trimChanged = Signal(float, float)

    def __init__(self, samples=None, duration_sec: float = 0.0, parent=None):
        super().__init__(parent)
        self.samples = samples
        self.duration = duration_sec if duration_sec>0 else 10.0
        self.trim_start = 0.0
        self.trim_end = 0.0
        self.play_pos = -1  # seconds, -1 = hidden
        self._drag = None
        self.setMinimumHeight(96)
        self.setMinimumWidth(360)

    def set_trim(self, start: float, end: float):
        self.trim_start = start; self.trim_end = end; self.update()

    def set_play_pos(self, sec: float):
        self.play_pos = sec
        self.update()

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(8,8, -8, -28)
        p.fillRect(self.rect(), QColor("#1E1E1E"))
        p.setPen(QPen(QColor("#333"),1))
        for i in range(5):
            x = r.x()+r.width()*i/4
            p.drawLine(int(x), r.y(), int(x), r.bottom())
        mid = r.center().y()
        if self.samples:
            p.setPen(QPen(QColor("#00E5FF"),1))
            step = max(1, len(self.samples)//max(1,r.width()))
            for x in range(r.width()):
                idx = x*step
                if idx >= len(self.samples): break
                v = self.samples[idx]
                h = v * (r.height()/2*0.9)
                p.drawLine(int(r.x()+x), int(mid-h), int(r.x()+x), int(mid+h))
        else:
            p.setPen(QPen(QColor("#00E5FF"),1))
            for x in range(r.width()):
                v = math.sin(x*0.07)*0.5 + math.sin(x*0.023)*0.3 + (math.sin(x*0.11)*0.15)
                h = v * (r.height()/2*0.8)
                p.drawLine(int(r.x()+x), int(mid-h), int(r.x()+x), int(mid+h))
        total = self.duration
        def sec_to_x(s):
            if s<=0: return r.x()
            return r.x() + min(1, s/total)*r.width()
        start_x = sec_to_x(self.trim_start) if self.trim_start>0 else r.x()
        end_x = sec_to_x(self.trim_end) if self.trim_end>0 else r.right()
        p.fillRect(QRectF(r.x(), r.y(), start_x - r.x(), r.height()), QColor(0,0,0,140))
        p.fillRect(QRectF(end_x, r.y(), r.right()-end_x, r.height()), QColor(0,0,0,140))
        p.setPen(QPen(QColor("#FFEB3B"),2)); p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(start_x, r.y(), end_x-start_x, r.height()))
        p.setBrush(QColor("#FFEB3B")); p.setPen(QPen(QColor("#000"),1))
        p.drawRect(QRectF(start_x-6, r.y()-4, 12, r.height()+8))
        p.drawRect(QRectF(end_x-6, r.y()-4, 12, r.height()+8))
        p.setPen(QColor("#FFEB3B")); p.drawText(QRectF(start_x-20, r.y()-14, 40, 12), Qt.AlignCenter, "◀")
        p.drawText(QRectF(end_x-20, r.y()-14, 40, 12), Qt.AlignCenter, "▶")
        # red playhead
        if self.play_pos >= 0:
            px = sec_to_x(self.play_pos)
            p.setPen(QPen(QColor("#FF1744"), 2))
            p.drawLine(int(px), int(r.y()), int(px), int(r.bottom()))
            # triangle
            p.setBrush(QColor("#FF1744")); p.setPen(Qt.NoPen)
            p.drawPolygon([QPointF(px-6, r.y()-6), QPointF(px+6, r.y()-6), QPointF(px, r.y())])
            p.drawPolygon([QPointF(px-6, r.bottom()+6), QPointF(px+6, r.bottom()+6), QPointF(px, r.bottom())])
        p.setPen(QColor("#AAA")); p.setBrush(Qt.NoBrush)
        p.drawText(QRectF(r.x(), r.bottom()+4, r.width(), 14), Qt.AlignCenter, f"{self._fmt(self.trim_start)} — {self._fmt(self.trim_end if self.trim_end>0 else total)} / {self._fmt(total)}  {tr('(drag yellow handles)', '(тяни жёлтые ползунки)')}")
        p.setPen(QColor("#FFFFFF")); p.drawText(self.rect().adjusted(8,0,-8,0), Qt.AlignRight|Qt.AlignTop, tr("drag — live preview", "тяни — сразу видно отрезок"))

    def _fmt(self, s):
        if s<=0: return "0:00.0"
        m=int(s//60); sec=int(s%60); ms=int((s%1)*10)
        return f"{m}:{sec:02d}.{ms}"

    def mousePressEvent(self, e):
        if e.button()!=Qt.LeftButton: return
        r = self.rect().adjusted(8,8,-8,-28)
        def sec_to_x(s): return r.x() + min(1,s/self.duration)*r.width() if s>0 else r.x()
        sx = sec_to_x(self.trim_start) if self.trim_start>0 else r.x()
        ex = sec_to_x(self.trim_end) if self.trim_end>0 else r.right()
        x=e.position().x()
        if abs(x-sx)<12: self._drag='start'
        elif abs(x-ex)<12: self._drag='end'
        else: self._drag=None

    def mouseMoveEvent(self, e):
        if self._drag is None: return
        r = self.rect().adjusted(8,8,-8,-28)
        def x_to_sec(x): return max(0, min(self.duration, (x - r.x())/r.width()*self.duration))
        x = max(r.x(), min(r.right(), e.position().x()))
        sec = x_to_sec(x)
        if self._drag=='start':
            end = self.trim_end if self.trim_end>0 else self.duration
            sec = min(sec, end-0.1)
            self.trim_start = round(sec,2)
        elif self._drag=='end':
            sec = max(sec, self.trim_start+0.1)
            self.trim_end = round(sec if sec < self.duration-0.05 else 0.0,2)
        self.update(); self.trimChanged.emit(self.trim_start, self.trim_end if self.trim_end!=0 else 0)

    def mouseReleaseEvent(self, e): self._drag=None


def _load_audio_samples(path_or_bytes, max_points=800):
    try:
        import io
        data = None
        if isinstance(path_or_bytes, (bytes, bytearray)):
            data = bytes(path_or_bytes)
            bio = io.BytesIO(data)
            if data[:4]==b'RIFF':
                try:
                    with wave.open(bio) as wf:
                        n = wf.getnframes()
                        frames = wf.readframes(n)
                        fmt = "<{}h".format(len(frames)//2)
                        try: vals = struct.unpack(fmt, frames)
                        except: vals = []
                        if vals:
                            step = max(1, len(vals)//max_points)
                            out=[]
                            for i in range(0, len(vals), step):
                                chunk = vals[i:i+step]
                                if not chunk: break
                                out.append(max(chunk, key=lambda v: abs(v))/32768.0)
                                if len(out)>=max_points: break
                            dur = n / wf.getframerate()
                            return out, dur
                except: pass
        else:
            p = Path(path_or_bytes)
            if p.exists() and p.suffix.lower()=='.wav':
                with wave.open(str(p)) as wf:
                    n = wf.getnframes()
                    frames = wf.readframes(n)
                    fmt = "<{}h".format(len(frames)//2)
                    try: vals = struct.unpack(fmt, frames)
                    except: vals=[]
                    if vals:
                        step = max(1, len(vals)//max_points)
                        out=[max(vals[i:i+step], key=lambda v: abs(v))/32768.0 for i in range(0,len(vals),step)]
                        return out[:max_points], n / wf.getframerate()
    except Exception:
        pass
    return None, 0.0


class AVSettingsDialog(QDialog):
    def __init__(self, params, media_path: str = "", media_bytes: Optional[bytes]=None, title: str="Trim / Volume / Speed", is_video=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title + tr(" — interactive preview", " — интерактивный предпросмотр"))
        self.resize(760, 560)
        self.params = params
        self.is_video = is_video
        self.media_path = media_path
        self.media_bytes = media_bytes
        self._tmp_file = None
        self._paused_pos = 0  # for pause/resume

        lay = QVBoxLayout(self)
        samples, dur = None, 0.0
        if media_bytes:
            samples, dur = _load_audio_samples(media_bytes)
        elif media_path and Path(media_path).exists():
            samples, dur = _load_audio_samples(Path(media_path))
        if is_video and dur==0:
            dur = (params.TrimEnd if params.TrimEnd>0 else 15.0)
            if dur<3: dur=15.0
        if not is_video and dur==0:
            dur = (params.TrimEnd if params.TrimEnd>0 else 10.0)
            if dur<1: dur=10.0
        self.wave = WaveformWidget(samples, dur)
        self.wave.set_trim(params.TrimStart, params.TrimEnd)
        lay.addWidget(self.wave)

        self.video_widget = None
        if is_video:
            try:
                from PySide6.QtMultimediaWidgets import QVideoWidget
                self.video_widget = QVideoWidget()
                self.video_widget.setMinimumHeight(260)
                self.video_widget.setStyleSheet("background:#000; border:1px solid #333;")
                lay.addWidget(self.video_widget, 1)
            except Exception:
                lbl = QLabel("Видео превью недоступно")
                lbl.setAlignment(Qt.AlignCenter); lbl.setStyleSheet("background:#000; color:#888; padding:18px;")
                lay.addWidget(lbl)

        form = QFormLayout()
        self.trimStart = QDoubleSpinBox(); self.trimStart.setRange(0, 1e6); self.trimStart.setSingleStep(0.1); self.trimStart.setValue(params.TrimStart)
        self.trimEnd = QDoubleSpinBox(); self.trimEnd.setRange(0, 1e6); self.trimEnd.setSingleStep(0.1); self.trimEnd.setValue(params.TrimEnd)
        self.volume = QDoubleSpinBox(); self.volume.setRange(0,1); self.volume.setSingleStep(0.05); self.volume.setValue(params.Volume)
        self.speed = QDoubleSpinBox(); self.speed.setRange(0.1,2.0); self.speed.setSingleStep(0.1); self.speed.setValue(params.Speed)
        form.addRow(tr("Trim Start (sec)", "Trim Start (сек)"), self.trimStart)
        form.addRow(tr("Trim End (0 = end)", "Trim End (0 = конец)"), self.trimEnd)
        form.addRow(tr("Volume 0..1", "Volume 0..1"), self.volume)
        form.addRow(tr("Speed 0.1..2.0", "Speed 0.1..2.0"), self.speed)
        lay.addLayout(form)
        self.wave.trimChanged.connect(self._from_wave)
        self.trimStart.valueChanged.connect(self._to_wave)
        self.trimEnd.valueChanged.connect(self._to_wave)

        self._player = None
        self._audio_output = None
        self._init_player()
        play_row = QHBoxLayout()
        self.btn_play = QPushButton(tr("▶ Play", "▶ Играть"))
        self.btn_pause = QPushButton(tr("⏸ Pause", "⏸ Пауза"))
        self.btn_stop = QPushButton(tr("■ Stop", "■ Стоп"))
        self.lbl_status = QLabel(tr("Ready", "Готов"))
        self.lbl_status.setStyleSheet("color:#888;")
        play_row.addWidget(self.btn_play); play_row.addWidget(self.btn_pause); play_row.addWidget(self.btn_stop); play_row.addWidget(self.lbl_status, 1)
        lay.addLayout(play_row)
        self.btn_play.clicked.connect(self._play)
        self.btn_pause.clicked.connect(self._pause)
        self.btn_stop.clicked.connect(self._stop)

        note = QLabel(tr("Drag yellow handles — Trim will update. Red cursor shows position. Pause to resume, Stop to beginning.", "Тяни жёлтые ползунки — Trim обновится. Красный курсор показывает позицию. Пауза — продолжить, Стоп — в начало отрезка."))
        note.setWordWrap(True); note.setStyleSheet("color:#666; font-size:11px;")
        lay.addWidget(note)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _from_wave(self, s,e):
        self.trimStart.blockSignals(True); self.trimEnd.blockSignals(True)
        self.trimStart.setValue(s); self.trimEnd.setValue(e)
        self.trimStart.blockSignals(False); self.trimEnd.blockSignals(False)

    def _to_wave(self):
        self.wave.set_trim(self.trimStart.value(), self.trimEnd.value())

    def _init_player(self):
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            self._player = QMediaPlayer(self)
            self._audio_output = QAudioOutput(self)
            self._player.setAudioOutput(self._audio_output)
            if self.video_widget is not None:
                try: self._player.setVideoOutput(self.video_widget)
                except: pass
            if self.media_bytes:
                suffix = Path(self.media_path).suffix if self.media_path else (".mp4" if self.is_video else ".mp3")
                tf = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                tf.write(self.media_bytes); tf.close()
                self._tmp_file = tf.name
                self._player.setSource(QUrl.fromLocalFile(self._tmp_file))
            elif self.media_path and Path(self.media_path).exists():
                self._player.setSource(QUrl.fromLocalFile(self.media_path))
            try:
                self._player.durationChanged.connect(self._on_duration)
                self._player.positionChanged.connect(self._on_pos)
                self._player.playbackStateChanged.connect(self._on_state)
            except: pass
        except Exception:
            self._player=None

    def _on_duration(self, ms):
        if ms>0:
            sec = ms/1000.0
            self.wave.duration = sec
            self.wave.update()

    def _on_pos(self, ms):
        sec = ms/1000.0
        self.wave.set_play_pos(sec)
        if self._player and self._player.playbackState() == self._player.PlaybackState.PlayingState:
            self.lbl_status.setText(f"{tr('Playing', 'Играет')} {sec:.1f}{tr('s', 'с')} / {self.wave._fmt(self.wave.duration)}")
        end = self.trimEnd.value()
        if end>0 and sec >= end - 0.05:
            self._stop()

    def _on_state(self, state):
        pass

    def _play(self):
        if not self._player:
            self.lbl_status.setText(tr("Player unavailable", "Плеер недоступен"))
            return
        from PySide6.QtMultimedia import QMediaPlayer
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PausedState:
            self._player.play()
            self.lbl_status.setText(f"{tr('Resuming from', 'Продолжает с')} {self._player.position()/1000:.1f}{tr('s', 'с')}")
            return
        start = self.trimStart.value()
        if self._paused_pos >= start and (self.trimEnd.value()==0 or self._paused_pos < self.trimEnd.value()):
            start = self._paused_pos
        self._player.setPosition(int(start*1000))
        if self._audio_output:
            self._audio_output.setVolume(self.volume.value())
        try: self._player.setPlaybackRate(self.speed.value())
        except: pass
        self._player.play()
        self.lbl_status.setText(f"{tr('Playing from', 'Играет с')} {start:.1f}{tr('s…', 'с…')}")

    def _pause(self):
        if not self._player: return
        from PySide6.QtMultimedia import QMediaPlayer
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._paused_pos = self._player.position()/1000.0
            self._player.pause()
            self.lbl_status.setText(f"{tr('Paused at', 'Пауза на')} {self._paused_pos:.1f}{tr('s — press Play to resume', 'с — нажми Играть чтобы продолжить')}")
        elif self._player.playbackState() == QMediaPlayer.PlaybackState.PausedState:
            self._play()

    def _stop(self):
        try:
            if self._player:
                self._player.stop()
                self._paused_pos = self.trimStart.value()
                self.wave.set_play_pos(self._paused_pos)
            self.lbl_status.setText(tr("Stopped — to beginning", "Стоп — в начало отрезка"))
        except: pass

    def closeEvent(self, e):
        try:
            if self._player: self._player.stop()
            if self._tmp_file and Path(self._tmp_file).exists(): os.unlink(self._tmp_file)
        except: pass
        super().closeEvent(e)

    def result_audio(self) -> AudioEditParams:
        return AudioEditParams(TrimStart=self.trimStart.value(), TrimEnd=self.trimEnd.value(), Volume=self.volume.value(), Speed=self.speed.value())
    def result_video(self) -> VideoEditParams:
        return VideoEditParams(TrimStart=self.trimStart.value(), TrimEnd=self.trimEnd.value(), Volume=self.volume.value(), Speed=self.speed.value())
    def accept(self):
        self._stop()
        super().accept()
    def reject(self):
        self._stop()
        super().reject()


# ---------- Media attach widget — 3 независимые кнопки ----------

class MediaAttachWidget(QWidget):
    """Три отдельные кнопки: Фото / Видео / Аудио — не блокируют друг друга."""
    def __init__(self, label: str, photo_path: str = "", video_path: str = "", audio_path: str = "",
                 image_params: Optional[ImageEditParams]=None, audio_params: Optional[AudioEditParams]=None, video_params: Optional[VideoEditParams]=None,
                 on_change: Optional[Callable]=None, parent=None, media_bytes_dict: Optional[dict]=None, **kwargs):
        # backward compat: если вызвали как MediaAttachWidget(label, current_path, img, aud, vid)
        # то current_path — это второй позиционный аргумент, а image_params передаётся третьим
        # detect legacy: если photo_path выглядит как ImageEditParams
        if isinstance(photo_path, ImageEditParams) or isinstance(photo_path, VideoEditParams) or isinstance(photo_path, AudioEditParams):
            # legacy order mis-match — ignore, will be handled via kwargs fallback
            photo_path = ""
        # handle legacy single-path call: label, current_path, image_params, audio_params, video_params
        # we keep compatibility: if video_path is ImageEditParams etc.
        if isinstance(video_path, ImageEditParams):
            # actually current_path was passed as photo_path, and image_params as video_path
            # need to reinterpret
            pass
        super().__init__(parent)
        # normalize: support both new (photo,video,audio) and old (current_path)
        # old call: MediaAttachWidget(label, current_path, image_params, audio_params, video_params, on_change)
        # in that case photo_path = current_path string, video_path = ImageEditParams, etc.
        # Detect by type
        self.on_change = on_change
        # try to extract from kwargs / positional confusion
        # The clean new API: photo_path/video_path/audio_path are strings, image_params etc are objects
        # If caller used old API, image_params will be AudioEditParams etc. and photo_path is string path
        # We detect and remap
        if isinstance(image_params, str) or image_params is None and isinstance(audio_params, ImageEditParams):
            # unlikely
            pass

        # If called with old signature: (label, current_path, image_params, audio_params, video_params)
        # then photo_path is current_path (str), video_path is image_params (object), audio_path is audio_params (object)
        # So we need to detect
        _legacy = False
        if isinstance(video_path, ImageEditParams) or isinstance(video_path, AudioEditParams) or isinstance(video_path, VideoEditParams):
            _legacy = True
        if _legacy:
            cur = photo_path or ""
            img_p = video_path if isinstance(video_path, ImageEditParams) else ImageEditParams()
            aud_p = audio_path if isinstance(audio_path, AudioEditParams) else AudioEditParams()
            vid_p = image_params if isinstance(image_params, VideoEditParams) else VideoEditParams()
            # also on_change may be in audio_params position?
            if callable(video_path) and on_change is None:
                on_change = video_path
            # remap
            photo_path, video_path, audio_path = "", "", ""
            ext = Path(cur).suffix.lower() if cur else ""
            if ext in (".png",".jpg",".jpeg",".bmp",".gif",".webp"): photo_path = cur
            elif ext in (".mp4",".avi",".mov",".mkv",".webm"): video_path = cur
            elif ext in (".mp3",".wav",".ogg",".flac",".m4a"): audio_path = cur
            else:
                # unknown — treat as photo if not empty
                if cur: photo_path = cur
            image_params, audio_params, video_params = img_p, aud_p, vid_p
            self.on_change = on_change if callable(on_change) else kwargs.get('on_change', on_change)

        self.label_text = label
        self.photo_path = photo_path or ""
        self.video_path = video_path or ""
        self.audio_path = audio_path or ""
        self.image_params = image_params if isinstance(image_params, ImageEditParams) else ImageEditParams()
        self.audio_params = audio_params if isinstance(audio_params, AudioEditParams) else AudioEditParams()
        self.video_params = video_params if isinstance(video_params, VideoEditParams) else VideoEditParams()
        # compat: also keep current_path as photo for old code that reads it
        self.current_path = self.photo_path or self.video_path or self.audio_path
        self.media_bytes_dict = media_bytes_dict or {}
        self.setAcceptDrops(True)

        lay = QVBoxLayout(self); lay.setContentsMargins(0,0,0,0)
        lay.addWidget(QLabel(f"<b>{label}</b>"))

        def make_row(icon, name, path, tag):
            row = QHBoxLayout(); row.setSpacing(6); row.setContentsMargins(0,2,0,2)
            lbl = QLabel(f"{icon} {name}:"); lbl.setFixedWidth(62); lbl.setStyleSheet("color:#ddd; background:transparent; border:none;")
            info = QLabel(path if path else tr("(none)", tr("(none)", "(нет)"))); info.setWordWrap(True); info.setStyleSheet("border:1px solid #3a3a3a; padding:4px 6px; background:#2a2a2a; color:#e0e0e0; border-radius:4px;")
            info.setMinimumHeight(26)
            btn_attach = QPushButton(tr("Choose…", "Выбрать…")); btn_attach.setFixedWidth(88); btn_attach.setStyleSheet("padding:4px;")
            btn_clear = QPushButton("✕"); btn_clear.setFixedWidth(30); btn_clear.setStyleSheet("padding:2px;")
            btn_set = QPushButton(tr("Settings…", "Настройки…")); btn_set.setFixedWidth(108); btn_set.setStyleSheet("padding:4px;")
            row.addWidget(lbl); row.addWidget(info,1); row.addWidget(btn_attach); row.addWidget(btn_clear); row.addWidget(btn_set)
            return row, info, btn_attach, btn_clear, btn_set

        self._rows = {}
        for icon, name, path, tag in [("🖼️", tr("Photo", "Фото"), self.photo_path, "photo"), ("🎬", tr("Video", "Видео"), self.video_path, "video"), ("🎵", tr("Audio", "Аудио"), self.audio_path, "audio")]:
            row, info, ba, bc, bs = make_row(icon, name, path, tag)
            lay.addLayout(row)
            self._rows[tag] = (info, ba, bc, bs)
            ba.clicked.connect(lambda _=False, t=tag: self._attach(t))
            bc.clicked.connect(lambda _=False, t=tag: self._clear(t))
            bs.clicked.connect(lambda _=False, t=tag: self._settings(t))
            # disable clear if empty
            bc.setEnabled(bool(path))

        self.preview = QLabel(); self.preview.setAlignment(Qt.AlignCenter); self.preview.setVisible(False); self.preview.setStyleSheet("border:1px solid #3a3a3a; background:#1a1a1a; color:#0ff; padding:6px; border-radius:4px;")
        self.preview.setMinimumHeight(0)
        lay.addWidget(self.preview)
        self._refresh_previews()
        self._sync_buttons()

    def _refresh_previews(self):
        # show first available preview
        if self.photo_path and self.photo_path in self.media_bytes_dict:
            try:
                data = self.media_bytes_dict[self.photo_path]
                pm = QPixmap(); pm.loadFromData(data)
                if not pm.isNull():
                    self.preview.setPixmap(pm.scaled(360,200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    self.preview.setVisible(True)
                    return
            except: pass
        if self.photo_path and Path(self.photo_path).exists():
            try:
                pm = QPixmap(self.photo_path)
                if not pm.isNull():
                    self.preview.setPixmap(pm.scaled(360,200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    self.preview.setVisible(True)
                    return
            except: pass
        if self.video_path:
            self.preview.setText(tr("🎬 video selected — open Settings for preview/trim", "🎬 видео выбрано — открой Настройки для превью/трима"))
            self.preview.setVisible(True)
            return
        if self.audio_path:
            self.preview.setText(tr("🎵 audio selected — open Settings for waveform", "🎵 аудио выбрано — открой Настройки для волнограммы"))
            self.preview.setVisible(True)
            return
        self.preview.setVisible(False)

    def _sync_buttons(self):
        has_photo = bool(self.photo_path)
        has_video = bool(self.video_path)
        has_audio = bool(self.audio_path)
        for tag in ("photo","video","audio"):
            _, ba, bc, bs = self._rows[tag]
            has = bool({"photo": self.photo_path, "video": self.video_path, "audio": self.audio_path}[tag])
            bc.setEnabled(has)
            bs.setEnabled(has)
            # правило: фото+аудио совместимы, видео эксклюзивно
            # Если фото -> можно аудио, нельзя видео
            # Если аудио -> можно фото, нельзя видео
            # Если видео -> нельзя ни фото ни аудио
            if tag == "photo":
                # выбрать фото можно только если нет фото и нет видео
                can_choose = (not has_photo) and (not has_video)
                ba.setEnabled(can_choose)
                if has_video:
                    ba.setToolTip("Видео уже выбрано — очисти видео чтобы добавить фото")
                elif has_photo:
                    ba.setToolTip("Фото уже выбрано — очисти чтобы выбрать заново")
                else:
                    ba.setToolTip("Выбрать файл")
            elif tag == "audio":
                can_choose = (not has_audio) and (not has_video)
                ba.setEnabled(can_choose)
                if has_video:
                    ba.setToolTip("Видео уже выбрано — очисти видео чтобы добавить аудио")
                elif has_audio:
                    ba.setToolTip("Аудио уже выбрано — очисти чтобы выбрать заново")
                else:
                    ba.setToolTip("Выбрать файл")
            else:  # video
                can_choose = (not has_video) and (not has_photo) and (not has_audio)
                ba.setEnabled(can_choose)
                if has_video:
                    ba.setToolTip("Видео уже выбрано — очисти чтобы выбрать заново")
                elif has_photo or has_audio:
                    ba.setToolTip("Фото/Аудио уже выбраны — очисти их чтобы добавить видео")
                else:
                    ba.setToolTip("Выбрать файл")
            bs.setToolTip("Настройки доступны только когда файл выбран" if not has else "")

    def set_media_bytes(self, path_to_bytes: dict, current_path: str = ""):
        self.media_bytes_dict = path_to_bytes
        for tag in ("photo","video","audio"):
            p = {"photo": self.photo_path, "video": self.video_path, "audio": self.audio_path}[tag]
            info, _, _, _ = self._rows[tag]
            info.setText(p if p else tr("(none)", "(нет)"))
        self._sync_buttons()
        self._refresh_previews()
        self.current_path = self.photo_path or self.video_path or self.audio_path

    def _attach(self, tag):
        filt = {"photo": "Изображения (*.png *.jpg *.jpeg *.bmp *.webp)", "video": "Видео (*.mp4 *.avi *.mov *.mkv *.webm)", "audio": "Аудио (*.mp3 *.wav *.ogg *.flac *.m4a)"}[tag]
        fn, _ = QFileDialog.getOpenFileName(self, f"Выбрать {tag}", "", f"{filt};;Все файлы (*.*)")
        if not fn: return
        if tag=="photo": self.photo_path = fn
        elif tag=="video": self.video_path = fn
        else: self.audio_path = fn
        self.current_path = self.photo_path or self.video_path or self.audio_path
        info, _, _, _ = self._rows[tag]
        info.setText(fn)
        self._sync_buttons()
        self._refresh_previews()
        if self.on_change:
            self.on_change(fn, f"{tag}_attach")

    def _clear(self, tag):
        if tag=="photo": self.photo_path = ""
        elif tag=="video": self.video_path = ""
        else: self.audio_path = ""
        self.current_path = self.photo_path or self.video_path or self.audio_path
        info, _, _, _ = self._rows[tag]
        info.setText(tr("(none)", "(нет)"))
        self._sync_buttons()
        self._refresh_previews()
        if self.on_change:
            self.on_change("", f"{tag}_clear")

    def _settings(self, tag):
        # pick params and bytes
        if tag=="photo":
            b = self.media_bytes_dict.get(self.photo_path) if self.photo_path in self.media_bytes_dict else None
            if b is None and self.photo_path and Path(self.photo_path).exists():
                try: b = Path(self.photo_path).read_bytes()
                except: b=None
            pm = QPixmap()
            if b: pm.loadFromData(b)
            elif self.photo_path and Path(self.photo_path).exists(): pm.load(self.photo_path)
            dlg = ImageSettingsDialog(self.image_params, pm, self)
            if dlg.exec()==QDialog.Accepted:
                self.image_params = dlg.result_params()
                if self.on_change: self.on_change(self.photo_path, "image_settings")
        elif tag=="video":
            b = self.media_bytes_dict.get(self.video_path) if self.video_path in self.media_bytes_dict else None
            if b is None and self.video_path and Path(self.video_path).exists():
                try: b = Path(self.video_path).read_bytes()
                except: b=None
            dlg = AVSettingsDialog(self.video_params, self.video_path, b, "Видео", is_video=True, parent=self)
            if dlg.exec()==QDialog.Accepted:
                self.video_params = dlg.result_video()
                if self.on_change: self.on_change(self.video_path, "video_settings")
        else:
            b = self.media_bytes_dict.get(self.audio_path) if self.audio_path in self.media_bytes_dict else None
            if b is None and self.audio_path and Path(self.audio_path).exists():
                try: b = Path(self.audio_path).read_bytes()
                except: b=None
            dlg = AVSettingsDialog(self.audio_params, self.audio_path, b, "Аудио", is_video=False, parent=self)
            if dlg.exec()==QDialog.Accepted:
                self.audio_params = dlg.result_audio()
                if self.on_change: self.on_change(self.audio_path, "audio_settings")

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            local = url.toLocalFile()
            if not local or not os.path.exists(local): continue
            ext = Path(local).suffix.lower()
            has_photo = bool(self.photo_path); has_video = bool(self.video_path); has_audio = bool(self.audio_path)
            if ext in (".png",".jpg",".jpeg",".bmp",".gif",".webp"):
                if has_photo or has_video: continue
                self.photo_path = local; info,_,_,_=self._rows["photo"]; info.setText(local)
                if self.on_change: self.on_change(local, "photo_attach")
            elif ext in (".mp4",".avi",".mov",".mkv",".webm"):
                if has_video or has_photo or has_audio: continue
                self.video_path = local; info,_,_,_=self._rows["video"]; info.setText(local)
                if self.on_change: self.on_change(local, "video_attach")
            elif ext in (".mp3",".wav",".ogg",".flac",".m4a"):
                if has_audio or has_video: continue
                self.audio_path = local; info,_,_,_=self._rows["audio"]; info.setText(local)
                if self.on_change: self.on_change(local, "audio_attach")
        self.current_path = self.photo_path or self.video_path or self.audio_path
        self._sync_buttons()
        self._refresh_previews()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            has_photo = bool(self.photo_path); has_video = bool(self.video_path); has_audio = bool(self.audio_path)
            for url in e.mimeData().urls():
                local = url.toLocalFile()
                if not local: continue
                ext = Path(local).suffix.lower()
                if ext in (".png",".jpg",".jpeg",".bmp",".gif",".webp") and (has_photo or has_video): return
                if ext in (".mp4",".avi",".mov",".mkv",".webm") and (has_video or has_photo or has_audio): return
                if ext in (".mp3",".wav",".ogg",".flac",".m4a") and (has_audio or has_video): return
            e.acceptProposedAction()
        else:
            e.ignore()

    def set_path(self, path: str):
        ext = Path(path).suffix.lower() if path else ""
        if ext in (".png",".jpg",".jpeg",".bmp",".gif",".webp"): self.photo_path=path
        elif ext in (".mp4",".avi",".mov",".mkv",".webm"): self.video_path=path
        elif ext in (".mp3",".wav",".ogg",".flac",".m4a"): self.audio_path=path
        else: self.photo_path=path
        self.current_path = path or ""
        for tag in ("photo","video","audio"):
            p = {"photo":self.photo_path,"video":self.video_path,"audio":self.audio_path}[tag]
            info,_,_,_=self._rows[tag]
            info.setText(p if p else tr("(none)", "(нет)"))
        self._sync_buttons()
        self._refresh_previews()
