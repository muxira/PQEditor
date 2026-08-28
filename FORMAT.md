# Party Quiz Pack Format — Reverse-Engineered from Exported Example

> Single source of truth for serialization/deserialization. Derived solely from the exported `ТестовыйПак.pq` in `./examples/` cross-checked against the human-readable reference test pack description.

## 1. Container

* **File extension:** `.pq`
* **Container format:** ZIP archive (deflate). Verified magic `50 4B 03 04` and `zipfile.ZipFile` can open it.
* **Top-level entries:**

| Path | Meaning |
|------|---------|
| `manifest.json` | Single JSON manifest containing all structural data + media references + pack metadata. Always present, always at archive root. |
| `<Round>/<Theme>/<Price>/question/<filename>` | Question-side media file (photo / video / audio). `<Price>` is the question's `Price` value as decimal string (e.g. `10`). Folder names use the raw Round/Theme display names — Cyrillic preserved, not escaped. |
| `<Round>/<Theme>/<Price>/answer/<filename>` | Answer-side media file. Same naming rules. |
| `<filename>` at root (e.g. `images.jpg`) | Pack cover image (`Pack.Icon`). Stored at archive root, duplicated if the same file is also used as question/answer media (no deduplication — see §6). |

No other manifest or sidecar files were observed.

## 2. Manifest JSON (`manifest.json`)

The JSON is UTF-8, pretty-printed in the example but whitespace is insignificant. Top-level shape:

```json
{
  "Version": 22,
  "Pack": { ... }
}
```

* `Version: integer` — observed `22`. Treat as opaque; editor writes `22` on export.
* `Pack: object` — see §3.

All strings are JSON strings (UTF-8). Numeric fields are JSON numbers (integers for enums/ids, floats for timers/volumes).

## 3. `Pack` object

| Field | Type | Notes |
|-------|------|-------|
| `Owner` | `u64` | Steam ID of creator (observed `76561198871026078`). |
| `Id` | `integer` | Pack ID, `0` for local packs. |
| `Name` | `string` | Pack title. Example: `"ТестовыйПак"`. Maps to export dialog "Title". |
| `Description` | `string` | Pack description. `"ТестовоеОписание"`. |
| `Icon` | `string` | Relative path inside ZIP to cover image. `"images.jpg"` or `""` if none. |
| `Rounds` | `Round[]` | At least 1. Order = display order. |
| `Difficulty` | `integer` | Enum: `0=Very Easy, 1=Easy, 2=Medium, 3=Hard, 4=Very Hard`. Example `2` = Medium. |
| `Category` | `integer` | Enum: `0=Family, 1=General Knowledge, 2=Memes, 3=Games, 4=Mixed, 5=Other`. Example `5`. |
| `Language` | `integer` | Enum: `0=English, 1=Russian, 2=Ukrainian`. Example `1`. |
| `AgeRating` | `integer` | Enum: `0=0+, 1=12+, 2=16+, 3=18+`. Example `2` = 16+. |
| `TimeUpdated` | `integer` | Unix timestamp or `0` if unset. Example `0`. |

## 4. `Round` object

| Field | Type | Notes |
|-------|------|-------|
| `Name` | `string` | Display name. Example `"ПервыйРаунд"`. |
| `Description` | `string` | `"ТестовыйПервыйРаунд"`. |
| `Type` | `integer` | `0=Normal`, `1=Final`. |
| `MaxThemesCount` | `integer` | Declared capacity, always `5` in example. Ignored on import, written as `5`. |
| `Themes` | `Theme[]` | 1..=5 (Final also 1..=5, but each theme then has exactly 1 question). |

## 5. `Theme` object

| Field | Type | Notes |
|-------|------|-------|
| `Name` | `string` | |
| `Description` | `string` | |
| `MaxQuestionsCount` | `integer` | `5` for Normal rounds, `1` for Final rounds. Mirrors round type. Written accordingly. |
| `Questions` | `Question[]` | 1..=5 (exactly 1 when parent Round is Final). Order = price-ascending display before manual sort. |

## 6. `Question` object

| Field | Type | Notes |
|-------|------|-------|
| `Price` | `integer` | Points value. `10..50` typical. For Leading Hints (Type 4) this equals the *maximum* hint price (first hint). Example Q5 Price 50. |
| `Type` | `integer` | Enum: `0=Normal, 1=Cat in Bag (Кот в мешке), 2=Auction, 3=Quiz (multiple choice), 4=Leading Hints (Подсказки), 5=Guess the Number`. Final-round questions use `Type=0` + `IsFinal=true` (see below). |
| `Text` | `string` | Question text. Empty `""` for Leading Hints (type 4) where question text is not applicable. |
| `Picture` | `string` | Relative ZIP path to image for the **question side**, or `""` if none. |
| `Audio` | `string` | Relative ZIP path to audio file for question side, or `""`. |
| `Video` | `string` | Relative ZIP path to video file for question side, or `""`. |
| `AudioEditParams` | `EditParamsAudio` | Always present, even when no media. Defaults = full/1.0. |
| `ImageEditParams` | `EditParamsImage` | Always present. |
| `VideoEditParams` | `EditParamsVideo` | Always present. |
| `MultipleChoice` | `string[]` | Only for Type 3 (Quiz). Up to 4 entries. Empty otherwise. |
| `MultipleChoiceIndex` | `integer` | For Type 3: `0..3` index of correct option (example `3`). `-1` otherwise (including empty Quiz before selection). |
| `TimeToAnswer` | `float` | Seconds. Для таймер-независимых типов (Quiz, Leading Hints, Guess the Number, Final) всегда `0.0`. Для Normal/Кот/Аукцион дефолт по ТЗ — `10.0` (вопрос 1 первого раунда: `10с`). В примере для этого вопроса в файле лежало `0.0` — это легаси-значение «дефолт»; при загрузке редактор нормализует `0.0 → 10.0` и далее всегда сохраняет явные `10.0 / 20.0 / 30.0`. |
| `IsFinal` | `bool` | `true` only for the single question inside each Final-round theme. `false` otherwise. This is the sole discriminator for "Final Question" — there is no separate `Type` value for it. |
| `Answer` | `Answer` object | See §6.1. |
| `RevealingClues` | `Clue[]` | Only for Type 4 (Leading Hints). Up to 5 entries. Empty otherwise. |
| `IsReviewed` | `bool` | Always `false` in example. Unknown moderation flag; preserved round-trip. |

### 6.1 `Answer` object

| Field | Type | Notes |
|-------|------|-------|
| `Text` | `string` | Answer text. For Guess the Number (Type 5) this must be numeric string (example `"1"`). |
| `Picture` | `string` | Path or `""`. |
| `Audio` | `string` | Path or `""`. |
| `Video` | `string` | Path or `""`. |
| `AudioEditParams` | `EditParamsAudio` | Always present, independent from Question-side params (separate instance even when referencing the same file). |
| `ImageEditParams` | `EditParamsImage` | Always present. |
| `VideoEditParams` | `EditParamsVideo` | Always present. |
| `TextVisibleToPlayers` | `bool` | `true` in all examples. Whether answer text is shown to players after reveal. |
| `IsReviewed` | `bool` | `false` in example. |

### 6.2 `RevealingClues` / Clue (Leading Hints)

```json
{
  "Text": "1подсказка1",
  "Picture": "",
  "Price": 50
}
```

| Field | Type | Notes |
|-------|------|-------|
| `Text` | `string` | Hint text. |
| `Picture` | `string` | Optional photo path for this hint, or `""`. Audio/Video not supported for clues. |
| `Price` | `integer` | Points for this hint. Decreasing sequence in example: 50,40,30,20,10. Storage order = reveal order (drag-to-reorder). |

* Leading Hints questions have `Text=""` at the top level, `Price=50` (max hint price), `TimeToAnswer=0.0`, `RevealingClues` populated, `MultipleChoice` empty.
* If a clue has a picture, the file is stored alongside the question's media? In the current example all clue pictures are `""`, so path convention for clue media is not observed — editor will store it as `<Round>/<Theme>/<Price>/question/clue<N>_<filename>` or reuse the question/answer convention; importer accepts any non-empty string as path.

### 6.3 Media Edit Params

**`EditParamsImage` (Photo):**

```json
{"CropL":0.0,"CropT":0.0,"CropR":1.0,"CropB":1.0,"Zoom":1.0,"FlipX":false,"FlipY":false}
```

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `CropL` | `float` | `0.0` | Left crop, normalized 0..1 |
| `CropT` | `float` | `0.0` | Top crop |
| `CropR` | `float` | `1.0` | Right crop |
| `CropB` | `float` | `1.0` | Bottom crop |
| `Zoom` | `float` | `1.0` | Zoom factor |
| `FlipX` | `bool` | `false` | Horizontal flip |
| `FlipY` | `bool` | `false` | Vertical flip |

Full-image default = `(0,0)-(1,1)`. The spec's "Crop rectangle" maps to these six fields.

**`EditParamsAudio` / `EditParamsVideo`:**

```json
{"TrimStart":0.0,"TrimEnd":0.0,"Volume":1.0,"Speed":1.0}
```

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `TrimStart` | `float` | `0.0` | Start frame/time (0.0 = start of file). `0,0` means full duration. |
| `TrimEnd` | `float` | `0.0` | End frame/time (0.0 = end of file). |
| `Volume` | `float` | `1.0` | 0.0..1.0 (export dialog shows 100%). |
| `Speed` | `float` | `1.0` | 0.1..2.0 (max 2x per spec). |

These structs are stored **separately for question and answer** — even when both sides point to the same file (see §7), each side carries its own `AudioEditParams`/`ImageEditParams`/`VideoEditParams`.

### 6.4 Question-Type Matrix (observed)

| Type | Timer (`TimeToAnswer`) | Price | Question `Text` | `MultipleChoice` | `RevealingClues` | Answer `Text` |
|------|------------------------|-------|------------------|-----------------|------------------|---------------|
| 0 Normal | configurable (дефолт 10) | configurable | yes | — | — | yes |
| 1 Cat in Bag | configurable (дефолт 10) | configurable | yes | — | — | yes |
| 2 Auction | configurable (дефолт 10) | configurable | yes | — | — | yes |
| 3 Quiz | `0.0` (locked) | configurable (10 in example) | yes | up to 4, index 0..3 | — | yes |
| 4 Leading Hints | `0.0` (locked) | = max clue price | `""` (not settable) | — | 1..5, each with price | yes |
| 5 Guess Number | `0.0` (locked) | configurable | yes | — | — | numeric string |
| Final (`IsFinal=true`) | `0.0` (locked) | `20` in example but spec says not configurable — treat as locked | yes | — | — | yes |

## 7. Media Handling

* **Storage:** Files are stored verbatim (no transcoding) inside the ZIP. Paths are case-sensitive, UTF-8, with forward slashes.
* **Reference:** `Picture` / `Audio` / `Video` / `Answer.Picture` etc. and `Clue.Picture` hold the ZIP internal path. Empty string means no media.
* **Duplication:** When the same source file is attached to both question and answer (Q2 video, Q3 audio, cover vs answer photo), the file is **duplicated** in the archive under both `question/` and `answer/` paths (verified byte-identical via Python). The cover image is also duplicated at the root. Editor must not assume deduplication — write a separate entry per reference.
* **Cover:** `Pack.Icon` points to a file at the archive root (e.g. `images.jpg`). That file's bytes are identical to `ПервыйРаунд/ПерваяТема/10/answer/images.jpg` in the example, confirming the editor copies the file rather than referencing it.
* **Media settings are metadata-only:** `ImageEditParams` / `AudioEditParams` / `VideoEditParams` travel alongside each media reference but do not alter the stored bytes.

## 8. Round-Trip Guarantees

* Reading a `.pq` produced by the original editor and re-exporting with this spec must produce a ZIP whose `manifest.json` is semantically identical (field order may differ, but values and media bytes must match). Tests compare `Version`, `Pack` fields, and media SHA-256.
* `IsReviewed`, `TextVisibleToPlayers`, `MaxThemesCount`, `MaxQuestionsCount`, `TimeUpdated`, `Owner`, `Id` are preserved verbatim even though the editor does not expose them in the UI — they are written back as read, with sensible defaults for newly created packs (`Owner=0`, `Id=0`, `TimeUpdated=0`, `IsReviewed=false`, `TextVisibleToPlayers=true`).

## 9. Open Questions / Assumptions

* `TimeToAnswer = 0.0` для Normal Q1 в примере — легаси-экспорт оригинального редактора (дефолт 10с хранился как 0). ТЗ явно задаёт «Timer: 10s» для этого вопроса. Редактор нормализует `0.0 → 10.0` при импорте для `Normal/Кот/Аукцион` (если `!IsFinal`) и сохраняет `10.0` явно. Для безтаймерных типов `0.0` сохраняется как есть.
* Final question Price 20 vs spec "not configurable": example stores 20, so editor will persist whatever is set but UI will disable editing for `IsFinal` questions.
* Clue picture storage path convention is unobserved — editor will place clue images under `<Round>/<Theme>/<Price>/question/` with a `clue_<index>_` prefix and document it here if the game accepts it; importer is path-agnostic.
