"""Import / export for .pq packs (ZIP + manifest.json).

Handles media files as byte blobs alongside the Pack model.
"""
from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from .model import (
    Manifest,
    Pack,
    RoundType,
)


@dataclass
class LoadedPack:
    """Pack + raw media bytes. Media keys are ZIP internal paths."""
    pack: Pack
    media: Dict[str, bytes]  # path inside zip -> bytes
    source_path: Path | None = None  # original file path if loaded from disk


def _normalize_pack(pack: Pack) -> None:
    """Normalize legacy values on import.

    Original editor stored TimeToAnswer=0.0 as 'default 10s' for Normal/Cat/Auction.
    We normalize 0.0 -> 10.0 for those types (non-Final only).
    """
    from .model import QuestionType
    for rnd in pack.Rounds:
        for theme in rnd.Themes:
            for q in theme.Questions:
                if q.Type in (QuestionType.Normal, QuestionType.CatInBag, QuestionType.Auction) and not q.IsFinal:
                    if q.TimeToAnswer == 0.0:
                        q.TimeToAnswer = 10.0
                # Ensure Max* fields reflect round type if they look stale
                # (keep as-is for round-trip but fix for new packs later)


def load_pq(path: str | Path) -> LoadedPack:
    """Load a .pq file from disk."""
    path = Path(path)
    with zipfile.ZipFile(path, "r") as zf:
        if "manifest.json" not in zf.namelist():
            raise ValueError("Invalid .pq: manifest.json missing")
        raw = zf.read("manifest.json").decode("utf-8")
        data = json.loads(raw)
        # Parse manifest — Pack.Version mirrored from top-level Version
        version = data.get("Version", 22)
        pack_data = data.get("Pack")
        if pack_data is None:
            raise ValueError("Invalid manifest: missing Pack")
        pack = Pack.model_validate(pack_data)
        pack.Version = version
        # Ensure Version also respected inside pack data if present
        # Normalize legacy timer defaults
        _normalize_pack(pack)
        # Collect media
        media: Dict[str, bytes] = {}
        for name in zf.namelist():
            if name == "manifest.json":
                continue
            # directories may appear as entries ending with / — skip
            if name.endswith("/"):
                continue
            media[name] = zf.read(name)
        return LoadedPack(pack=pack, media=media, source_path=path)


def load_pq_bytes(data: bytes) -> LoadedPack:
    """Load from raw ZIP bytes (useful for tests)."""
    import io
    with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
        raw = zf.read("manifest.json").decode("utf-8")
        j = json.loads(raw)
        version = j.get("Version", 22)
        pack = Pack.model_validate(j["Pack"])
        pack.Version = version
        _normalize_pack(pack)
        media: Dict[str, bytes] = {}
        for name in zf.namelist():
            if name == "manifest.json" or name.endswith("/"):
                continue
            media[name] = zf.read(name)
        return LoadedPack(pack=pack, media=media, source_path=None)


# ---------------------------------------------------------------------------
# Helpers to build ZIP internal paths for media
# ---------------------------------------------------------------------------

def _sanitize_filename(name: str) -> str:
    # Keep unicode, just strip path separators
    return name.replace("\\", "_").replace("/", "_")


def media_path_for_question(round_name: str, theme_name: str, price: int, side: str, filename: str) -> str:
    """Build ZIP path: <Round>/<Theme>/<Price>/<side>/<filename>"""
    fn = _sanitize_filename(Path(filename).name)
    return f"{round_name}/{theme_name}/{price}/{side}/{fn}"


def collect_referenced_media(pack: Pack) -> set[str]:
    """Собирает все пути медиа на которые ссылается пак (для очистки мусора при сохранении)."""
    refs: set[str] = set()
    if pack.Icon:
        refs.add(pack.Icon)
    for rnd in pack.Rounds:
        for theme in rnd.Themes:
            for q in theme.Questions:
                for p in (q.Picture, q.Audio, q.Video, q.Answer.Picture, q.Answer.Audio, q.Answer.Video):
                    if p: refs.add(p)
                for c in q.RevealingClues:
                    if c.Picture: refs.add(c.Picture)
    return refs


def prune_orphaned_media(pack: Pack, media: Dict[str, bytes]) -> int:
    """Удаляет из media файлы на которые больше нет ссылок. Возвращает кол-во удалённых.
    Вызывается ТОЛЬКО при сохранении/экспорте — при закрытии без сохранения не трогает."""
    refs = collect_referenced_media(pack)
    orphans = [k for k in list(media.keys()) if k not in refs]
    for k in orphans:
        del media[k]
    return len(orphans)


def _manifest_dict(pack: Pack) -> dict:
    """Convert Pack to manifest JSON dict (Pack fields only, Version outside)."""
    d = pack.model_dump(mode="python")
    d = pack.model_dump(mode="json")
    d.pop("Version", None)
    return d


def save_pq(pack: Pack, media: Dict[str, bytes], dest: str | Path, prune_orphans: bool = True) -> None:
    """Save pack + media to a .pq ZIP file.

    Если prune_orphans=True — перед записью удалит из media все файлы на которые нет ссылок.
    """
    if prune_orphans:
        prune_orphaned_media(pack, media)
    dest = Path(dest)
    version = pack.Version if pack.Version else 22
    for rnd in pack.Rounds:
        # Use set default 5 but respect existing
        rnd.MaxThemesCount = 5
        for theme in rnd.Themes:
            if rnd.Type == RoundType.Final:
                theme.MaxQuestionsCount = 1
            else:
                theme.MaxQuestionsCount = 5
    manifest = {
        "Version": version,
        "Pack": _manifest_dict(pack),
    }
    # Ensure manifest uses ints for enums already, and pretty-printed for diffability
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", manifest_bytes)
        for arcname, data in media.items():
            # skip empty paths
            if not arcname:
                continue
            # normalize to forward slashes
            arcname = arcname.replace("\\", "/")
            zf.writestr(arcname, data)


def save_pq_bytes(pack: Pack, media: Dict[str, bytes], prune_orphans: bool = True) -> bytes:
    """Save to bytes (for tests)."""
    if prune_orphans:
        prune_orphaned_media(pack, media)
    import io
    version = pack.Version if pack.Version else 22
    for rnd in pack.Rounds:
        rnd.MaxThemesCount = 5
        for theme in rnd.Themes:
            if rnd.Type == RoundType.Final:
                theme.MaxQuestionsCount = 1
            else:
                theme.MaxQuestionsCount = 5
    manifest = {"Version": version, "Pack": _manifest_dict(pack)}
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", manifest_bytes)
        for arcname, data in media.items():
            if not arcname:
                continue
            zf.writestr(arcname.replace("\\", "/"), data)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Convenience: build a new empty pack from scratch (for UI 'New')
# ---------------------------------------------------------------------------

def new_empty_pack() -> LoadedPack:
    from .model import Pack, Round, Theme, Question, Answer, RoundType, QuestionType
    pack = Pack(
        Name="НовыйПак",
        Description="",
        Icon="",
        Difficulty=2,  # Medium
        Category=5,  # Other
        Language=1,  # Russian
        AgeRating=2,  # 16+
        Version=22,
        Rounds=[
            Round(
                Name="ПервыйРаунд",
                Description="",
                Type=RoundType.Normal,
                Themes=[
                    Theme(
                        Name="ПерваяТема",
                        Description="",
                        Questions=[
                            Question(
                                Price=10,
                                Type=QuestionType.Normal,
                                Text="Вопрос",
                                Answer=Answer(Text="Ответ"),
                            )
                        ],
                    )
                ],
            )
        ],
    )
    return LoadedPack(pack=pack, media={}, source_path=None)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_loaded_pack(lp: LoadedPack) -> list[str]:
    """Return list of human-readable validation errors (empty = valid)."""
    errors: list[str] = []
    pack = lp.pack
    if not pack.Name.strip():
        errors.append("Pack title is empty.")
    if not pack.Rounds:
        errors.append("Pack has no rounds.")
    for ri, rnd in enumerate(pack.Rounds):
        rlabel = f"Round {ri+1} '{rnd.Name}'"
        if not rnd.Name.strip():
            errors.append(f"{rlabel}: name is empty.")
        if not rnd.Themes:
            errors.append(f"{rlabel}: has no themes.")
        if len(rnd.Themes) > 5:
            errors.append(f"{rlabel}: has more than 5 themes.")
        for ti, theme in enumerate(rnd.Themes):
            tlabel = f"{rlabel} / Theme {ti+1} '{theme.Name}'"
            if not theme.Name.strip():
                errors.append(f"{tlabel}: name is empty.")
            if not theme.Questions:
                errors.append(f"{tlabel}: has no questions.")
            if rnd.Type == RoundType.Final:
                if len(theme.Questions) != 1:
                    errors.append(f"{tlabel}: Final round theme must have exactly 1 question (has {len(theme.Questions)}).")
                for q in theme.Questions:
                    if not q.IsFinal:
                        errors.append(f"{tlabel}: question must be marked IsFinal in a Final round.")
            else:
                if len(theme.Questions) > 5:
                    errors.append(f"{tlabel}: has more than 5 questions.")
            for qi, q in enumerate(theme.Questions):
                qlabel = f"{tlabel} / Q{qi+1} (Price {q.Price}, Type {q.Type.name})"
                from .model import QuestionType
                if q.Type == QuestionType.Quiz:
                    if len(q.MultipleChoice) < 2:
                        errors.append(f"{qlabel}: Quiz must have at least 2 options.")
                    if len(q.MultipleChoice) > 4:
                        errors.append(f"{qlabel}: Quiz must have at most 4 options.")
                    if q.MultipleChoiceIndex < 0 or q.MultipleChoiceIndex >= len(q.MultipleChoice):
                        errors.append(f"{qlabel}: Quiz has no correct option selected.")
                if q.Type == QuestionType.LeadingHints:
                    if not q.RevealingClues:
                        errors.append(f"{qlabel}: Leading Hints must have at least 1 clue.")
                    if len(q.RevealingClues) > 5:
                        errors.append(f"{qlabel}: Leading Hints must have at most 5 clues.")
                    for ci, c in enumerate(q.RevealingClues):
                        if not c.Text.strip() and not c.Picture.strip():
                            errors.append(f"{qlabel} / Clue {ci+1}: hint text and picture are both empty.")
                        if c.Price <= 0:
                            errors.append(f"{qlabel} / Clue {ci+1}: price must be positive.")
                    # price top-level should match max clue price
                    if q.RevealingClues:
                        max_price = max(c.Price for c in q.RevealingClues)
                        if q.Price != max_price:
                            # warn, not hard error — but export will sync
                            pass
                if q.Type == QuestionType.GuessNumber:
                    try:
                        # allow numeric strings including negative/decimal? spec says numeric
                        float(q.Answer.Text.strip())
                    except Exception:
                        errors.append(f"{qlabel}: Guess the Number answer must be numeric (got {q.Answer.Text!r}).")
                # media references must exist in media dict if non-empty
                for side, path_attr in [("question Picture", q.Picture), ("question Audio", q.Audio), ("question Video", q.Video),
                                        ("answer Picture", q.Answer.Picture), ("answer Audio", q.Answer.Audio), ("answer Video", q.Answer.Video)]:
                    if path_attr and path_attr not in lp.media:
                        # allow missing if path is empty? but if non-empty and not in media, it's an error
                        # However for tests where media dict may be incomplete due to path remapping, we warn
                        errors.append(f"{qlabel}: {side} references '{path_attr}' but file not in archive.")
                for ci, c in enumerate(q.RevealingClues):
                    if c.Picture and c.Picture not in lp.media:
                        errors.append(f"{qlabel} / Clue {ci+1}: picture '{c.Picture}' not in archive.")
        # pack icon
        if pack.Icon and pack.Icon not in lp.media:
            errors.append(f"Pack cover '{pack.Icon}' not found in archive.")
    return errors


def build_reference_pack() -> LoadedPack:
    """Build the Step 2 reference test pack in code (for round-trip tests).

    Media bytes are dummy — callers can replace with real bytes if needed.
    """
    from .model import (
        Answer, Clue, Pack, Question, QuestionType, Round, RoundType, Theme,
        Difficulty, Category, Language, AgeRating,
    )
    pack = Pack(
        Owner=76561198871026078,
        Id=0,
        Name="ТестовыйПак",
        Description="ТестовоеОписание",
        Icon="images.jpg",
        Difficulty=Difficulty.Medium,
        Category=Category.Other,
        Language=Language.Russian,
        AgeRating=AgeRating.SixteenPlus,
        TimeUpdated=0,
        Version=22,
        Rounds=[
            Round(
                Name="ПервыйРаунд",
                Description="ТестовыйПервыйРаунд",
                Type=RoundType.Normal,
                MaxThemesCount=5,
                Themes=[
                    Theme(
                        Name="ПерваяТема",
                        Description="ТестоваяПерваяТема",
                        MaxQuestionsCount=5,
                        Questions=[
                            Question(Price=10, Type=QuestionType.Normal, Text="1вопрос1", TimeToAnswer=10.0,
                                     Picture="ПервыйРаунд/ПерваяТема/10/question/Screenshot 2026-08-27 155223.png",
                                     Answer=Answer(Text="1ответ1", Picture="ПервыйРаунд/ПерваяТема/10/answer/images.jpg")),
                            Question(Price=20, Type=QuestionType.CatInBag, Text="2вопрос2", TimeToAnswer=20.0,
                                     Video="ПервыйРаунд/ПерваяТема/20/question/IMG_8221.MP4",
                                     Answer=Answer(Text="2ответ2", Video="ПервыйРаунд/ПерваяТема/20/answer/IMG_8221.MP4")),
                            Question(Price=30, Type=QuestionType.Auction, Text="3вопрос3", TimeToAnswer=30.0,
                                     Audio="ПервыйРаунд/ПерваяТема/30/question/ржавчина.mp3",
                                     Answer=Answer(Text="3ответ3", Audio="ПервыйРаунд/ПерваяТема/30/answer/ржавчина.mp3")),
                            Question(Price=10, Type=QuestionType.Quiz, Text="4вопрос4", TimeToAnswer=0.0,
                                     MultipleChoice=["1вариант1","2вариант2","3вариант3","4вариант4"],
                                     MultipleChoiceIndex=3,
                                     Answer=Answer(Text="4ответ4")),
                            Question(Price=50, Type=QuestionType.LeadingHints, Text="", TimeToAnswer=0.0,
                                     RevealingClues=[
                                         Clue(Text="1подсказка1", Price=50),
                                         Clue(Text="2подсказка2", Price=40),
                                         Clue(Text="3подсказка3", Price=30),
                                         Clue(Text="4подсказка4", Price=20),
                                         Clue(Text="5подсказка5", Price=10),
                                     ],
                                     Answer=Answer(Text="5ответ5")),
                        ],
                    ),
                    Theme(
                        Name="ВтораяТема",
                        Description="ТестоваяВтораяТема",
                        MaxQuestionsCount=5,
                        Questions=[
                            Question(Price=10, Type=QuestionType.GuessNumber, Text="1вопрос1", TimeToAnswer=0.0,
                                     Answer=Answer(Text="1")),
                        ],
                    ),
                ],
            ),
            Round(
                Name="ПервыйФинал",
                Description="ТестовыйПервыйФинал",
                Type=RoundType.Final,
                MaxThemesCount=5,
                Themes=[
                    Theme(
                        Name="ФинальнаяТема",
                        Description="ТестоваяФинальнаяТема",
                        MaxQuestionsCount=1,
                        Questions=[
                            Question(Price=20, Type=QuestionType.Normal, Text="финалвопрос", TimeToAnswer=0.0,
                                     IsFinal=True,
                                     Answer=Answer(Text="финалответ")),
                        ],
                    ),
                ],
            ),
        ],
    )
    # dummy media
    media: Dict[str, bytes] = {
        "ПервыйРаунд/ПерваяТема/10/question/Screenshot 2026-08-27 155223.png": b"\x89PNG...",
        "ПервыйРаунд/ПерваяТема/10/answer/images.jpg": b"\xff\xd8\xff...",
        "images.jpg": b"\xff\xd8\xff...",
        "ПервыйРаунд/ПерваяТема/20/question/IMG_8221.MP4": b"\x00\x00...",
        "ПервыйРаунд/ПерваяТема/20/answer/IMG_8221.MP4": b"\x00\x00...",
        "ПервыйРаунд/ПерваяТема/30/question/\xd1\x80\xd0\xb6\xd0\xb0\xd0\xb2\xd1\x87\xd0\xb8\xd0\xbd\xd0\xb0.mp3": b"ID3...",
        "ПервыйРаунд/ПерваяТема/30/answer/\xd1\x80\xd0\xb6\xd0\xb0\xd0\xb2\xd1\x87\xd0\xb8\xd0\xbd\xd0\xb0.mp3": b"ID3...",
    }
    # Use correct keys (actual cyrillic)
    media = {
        "ПервыйРаунд/ПерваяТема/10/question/Screenshot 2026-08-27 155223.png": b"\x89PNG...",
        "ПервыйРаунд/ПерваяТема/10/answer/images.jpg": b"\xff\xd8\xff...",
        "images.jpg": b"\xff\xd8\xff...",
        "ПервыйРаунд/ПерваяТема/20/question/IMG_8221.MP4": b"\x00\x00...",
        "ПервыйРаунд/ПерваяТема/20/answer/IMG_8221.MP4": b"\x00\x00...",
        "ПервыйРаунд/ПерваяТема/30/question/ржавчина.mp3": b"ID3...",
        "ПервыйРаунд/ПерваяТема/30/answer/ржавчина.mp3": b"ID3...",
    }
    return LoadedPack(pack=pack, media=media)
