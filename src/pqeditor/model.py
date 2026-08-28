"""Data model — 1:1 mapping to manifest.json for round-trip fidelity.

Field names match the on-disk JSON exactly (PascalCase). Enums are integers.
"""
import copy
from enum import IntEnum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums (integer values as stored on disk)
# ---------------------------------------------------------------------------

class Difficulty(IntEnum):
    VeryEasy = 0
    Easy = 1
    Medium = 2
    Hard = 3
    VeryHard = 4


class Category(IntEnum):
    Family = 0
    GeneralKnowledge = 1
    Memes = 2
    Games = 3
    Mixed = 4
    Other = 5


class Language(IntEnum):
    English = 0
    Russian = 1
    Ukrainian = 2


class AgeRating(IntEnum):
    ZeroPlus = 0  # 0+
    TwelvePlus = 1  # 12+
    SixteenPlus = 2  # 16+
    EighteenPlus = 3  # 18+


class RoundType(IntEnum):
    Normal = 0
    Final = 1


class QuestionType(IntEnum):
    Normal = 0
    CatInBag = 1  # Кот в мешке
    Auction = 2
    Quiz = 3
    LeadingHints = 4  # Подсказки
    GuessNumber = 5
    # Final is not a separate Type — it's Type 0 + IsFinal=true


# ---------------------------------------------------------------------------
# Media edit params
# ---------------------------------------------------------------------------

class ImageEditParams(BaseModel):
    CropL: float = 0.0
    CropT: float = 0.0
    CropR: float = 1.0
    CropB: float = 1.0
    Zoom: float = 1.0
    FlipX: bool = False
    FlipY: bool = False


class AudioEditParams(BaseModel):
    TrimStart: float = 0.0
    TrimEnd: float = 0.0
    Volume: float = 1.0
    Speed: float = 1.0

    @field_validator("Volume")
    @classmethod
    def validate_volume(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("Volume must be 0.0..1.0")
        return v

    @field_validator("Speed")
    @classmethod
    def validate_speed(cls, v: float) -> float:
        if not 0.1 <= v <= 2.0:
            pass
        return v


class VideoEditParams(BaseModel):
    TrimStart: float = 0.0
    TrimEnd: float = 0.0
    Volume: float = 1.0
    Speed: float = 1.0


def default_image_params() -> ImageEditParams:
    return ImageEditParams()


def default_audio_params() -> AudioEditParams:
    return AudioEditParams()


def default_video_params() -> VideoEditParams:
    return VideoEditParams()


# Aliases to avoid Pydantic field-name == type-name clash (Pydantic v2 bug with
# `FieldName: FieldName = Field(...)` when field name equals type name).
_ImageEditParamsAlias = ImageEditParams
_AudioEditParamsAlias = AudioEditParams
_VideoEditParamsAlias = VideoEditParams
_DifficultyAlias = Difficulty
_CategoryAlias = Category
_LanguageAlias = Language
_AgeRatingAlias = AgeRating


# ---------------------------------------------------------------------------
# Clue (Leading Hints)
# ---------------------------------------------------------------------------

class Clue(BaseModel):
    Text: str = ""
    Picture: str = ""  # ZIP internal path or ""
    Price: int = 10


_ClueAlias = Clue


# ---------------------------------------------------------------------------
# Answer
# ---------------------------------------------------------------------------

class Answer(BaseModel):
    Text: str = ""
    Picture: str = ""
    Audio: str = ""
    Video: str = ""
    AudioEditParams: _AudioEditParamsAlias = Field(default_factory=default_audio_params)  # type: ignore[valid-type]
    ImageEditParams: _ImageEditParamsAlias = Field(default_factory=default_image_params)  # type: ignore[valid-type]
    VideoEditParams: _VideoEditParamsAlias = Field(default_factory=default_video_params)  # type: ignore[valid-type]
    TextVisibleToPlayers: bool = True
    IsReviewed: bool = False


_AnswerAlias = Answer


# ---------------------------------------------------------------------------
# Question
# ---------------------------------------------------------------------------

class Question(BaseModel):
    Price: int = 10
    Type: QuestionType = QuestionType.Normal
    Text: str = ""
    Picture: str = ""
    Audio: str = ""
    Video: str = ""
    AudioEditParams: _AudioEditParamsAlias = Field(default_factory=default_audio_params)  # type: ignore[valid-type]
    ImageEditParams: _ImageEditParamsAlias = Field(default_factory=default_image_params)  # type: ignore[valid-type]
    VideoEditParams: _VideoEditParamsAlias = Field(default_factory=default_video_params)  # type: ignore[valid-type]
    MultipleChoice: list[str] = Field(default_factory=list)
    MultipleChoiceIndex: int = -1
    TimeToAnswer: float = 10.0
    IsFinal: bool = False
    Answer: _AnswerAlias = Field(default_factory=Answer)  # type: ignore[valid-type]
    RevealingClues: list[_ClueAlias] = Field(default_factory=list)  # type: ignore[valid-type]
    IsReviewed: bool = False

    @model_validator(mode="after")
    def validate_by_type(self):  # type: ignore[no-redef]
        if self.Type == QuestionType.Quiz:
            if self.MultipleChoiceIndex != -1 and not 0 <= self.MultipleChoiceIndex < len(self.MultipleChoice):
                pass
        return self

    # Helpers
    def is_timer_locked(self) -> bool:
        return self.Type in (QuestionType.Quiz, QuestionType.LeadingHints, QuestionType.GuessNumber) or self.IsFinal

    def is_price_locked(self) -> bool:
        return self.Type == QuestionType.LeadingHints or self.IsFinal

    def is_question_text_locked(self) -> bool:
        return self.Type == QuestionType.LeadingHints


_QuestionAlias = Question


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

class Theme(BaseModel):
    Name: str = "НоваяТема"
    Description: str = ""
    MaxQuestionsCount: int = 5
    Questions: list[_QuestionAlias] = Field(default_factory=list)  # type: ignore[valid-type]


_ThemeAlias = Theme


# ---------------------------------------------------------------------------
# Round
# ---------------------------------------------------------------------------

class Round(BaseModel):
    Name: str = "НовыйРаунд"
    Description: str = ""
    Type: RoundType = RoundType.Normal
    MaxThemesCount: int = 5
    Themes: list[_ThemeAlias] = Field(default_factory=list)  # type: ignore[valid-type]


_RoundAlias = Round


# ---------------------------------------------------------------------------
# Pack
# ---------------------------------------------------------------------------

class Pack(BaseModel):
    Owner: int = 0
    Id: int = 0
    Name: str = "НовыйПак"
    Description: str = ""
    Icon: str = ""  # path at ZIP root or ""
    Rounds: list[_RoundAlias] = Field(default_factory=list)  # type: ignore[valid-type]
    Difficulty: _DifficultyAlias = Difficulty.Medium  # type: ignore[valid-type]
    Category: _CategoryAlias = Category.Other  # type: ignore[valid-type]
    Language: _LanguageAlias = Language.Russian  # type: ignore[valid-type]
    AgeRating: _AgeRatingAlias = AgeRating.SixteenPlus  # type: ignore[valid-type]
    TimeUpdated: int = 0
    Version: int = 22  # stored at manifest top-level, mirrored here for convenience

    def clone(self) -> "Pack":
        return copy.deepcopy(self)


# ---------------------------------------------------------------------------
# Top-level manifest wrapper (Version + Pack)
# ---------------------------------------------------------------------------

_PackAlias = Pack


class Manifest(BaseModel):
    Version: int = 22
    Pack: _PackAlias  # type: ignore[valid-type]


# ---------------------------------------------------------------------------
# Display helpers (labels for export dialog etc.)
# ---------------------------------------------------------------------------

DIFFICULTY_LABELS: dict[Difficulty, str] = {
    Difficulty.VeryEasy: "Very Easy",
    Difficulty.Easy: "Easy",
    Difficulty.Medium: "Medium",
    Difficulty.Hard: "Hard",
    Difficulty.VeryHard: "Very Hard",
}
DIFFICULTY_BY_LABEL = {v: k for k, v in DIFFICULTY_LABELS.items()}

CATEGORY_LABELS: dict[Category, str] = {
    Category.Family: "Family",
    Category.GeneralKnowledge: "General Knowledge",
    Category.Memes: "Memes",
    Category.Games: "Games",
    Category.Mixed: "Mixed",
    Category.Other: "Other",
}
CATEGORY_BY_LABEL = {v: k for k, v in CATEGORY_LABELS.items()}

LANGUAGE_LABELS: dict[Language, str] = {
    Language.English: "English",
    Language.Russian: "Russian",
    Language.Ukrainian: "Ukrainian",
}
LANGUAGE_BY_LABEL = {v: k for k, v in LANGUAGE_LABELS.items()}

AGERATING_LABELS: dict[AgeRating, str] = {
    AgeRating.ZeroPlus: "0+",
    AgeRating.TwelvePlus: "12+",
    AgeRating.SixteenPlus: "16+",
    AgeRating.EighteenPlus: "18+",
}
AGERATING_BY_LABEL = {v: k for k, v in AGERATING_LABELS.items()}

QUESTION_TYPE_LABELS: dict[QuestionType, str] = {
    QuestionType.Normal: "Normal",
    QuestionType.CatInBag: "Кот в мешке",
    QuestionType.Auction: "Auction",
    QuestionType.Quiz: "Quiz",
    QuestionType.LeadingHints: "Leading Hints",
    QuestionType.GuessNumber: "Guess the Number",
}
# Final is displayed as "Final Question" when IsFinal is true
