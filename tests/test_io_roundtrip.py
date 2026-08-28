"""Round-trip tests for .pq I/O."""
import hashlib
import json
import zipfile
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
PQ1 = EXAMPLES_DIR / "ТестовыйПак.pq"
PQ2 = EXAMPLES_DIR / "sfafsafasfasf.pq"


def test_load_example_pq1():
    from pqeditor.io import load_pq
    lp = load_pq(PQ1)
    pack = lp.pack
    assert pack.Name == "ТестовыйПак"
    assert pack.Description == "ТестовоеОписание"
    assert pack.Icon == "images.jpg"
    assert len(pack.Rounds) == 2
    # Round 0
    r0 = pack.Rounds[0]
    assert r0.Name == "ПервыйРаунд"
    assert r0.Type == 0
    assert len(r0.Themes) == 2
    t0 = r0.Themes[0]
    assert t0.Name == "ПерваяТема"
    assert len(t0.Questions) == 5
    # Q1 — Normal, but TimeToAnswer normalized 0.0 -> 10.0
    q0 = t0.Questions[0]
    assert q0.Price == 10
    assert q0.Type == 0
    assert q0.Text == "1вопрос1"
    assert q0.Picture.endswith(".png")
    assert q0.Answer.Picture.endswith("images.jpg")
    assert q0.TimeToAnswer == 10.0  # normalized
    # Q2 CatInBag
    q1 = t0.Questions[1]
    assert q1.Type == 1
    assert q1.Video != ""
    assert q1.Answer.Video != ""
    # Q3 Auction
    q2 = t0.Questions[2]
    assert q2.Type == 2
    assert q2.Audio != ""
    # Q4 Quiz
    q3 = t0.Questions[3]
    assert q3.Type == 3
    assert q3.MultipleChoice == ["1вариант1","2вариант2","3вариант3","4вариант4"]
    assert q3.MultipleChoiceIndex == 3
    assert q3.TimeToAnswer == 0.0
    # Q5 Leading Hints
    q4 = t0.Questions[4]
    assert q4.Type == 4
    assert q4.Text == ""
    assert len(q4.RevealingClues) == 5
    assert [c.Price for c in q4.RevealingClues] == [50,40,30,20,10]
    assert [c.Text for c in q4.RevealingClues] == ["1подсказка1","2подсказка2","3подсказка3","4подсказка4","5подсказка5"]
    assert q4.Price == 50
    # Theme 2 GuessNumber
    q5 = r0.Themes[1].Questions[0]
    assert q5.Type == 5
    assert q5.Answer.Text == "1"
    # Final round
    rf = pack.Rounds[1]
    assert rf.Type == 1
    assert rf.Name == "ПервыйФинал"
    assert len(rf.Themes) == 1
    qf = rf.Themes[0].Questions[0]
    assert qf.IsFinal is True
    assert qf.Text == "финалвопрос"
    assert qf.Answer.Text == "финалответ"
    # media duplication check — same bytes for question/answer video
    assert lp.media["ПервыйРаунд/ПерваяТема/20/question/IMG_8221.MP4"] == lp.media["ПервыйРаунд/ПерваяТема/20/answer/IMG_8221.MP4"]
    assert lp.media["images.jpg"] == lp.media["ПервыйРаунд/ПерваяТема/10/answer/images.jpg"]
    # cover exists
    assert "images.jpg" in lp.media


def test_load_example_pq2_timer_not_normalized():
    from pqeditor.io import load_pq
    lp = load_pq(PQ2)
    # This file has correct 10.0 timer for Q1 already
    assert lp.pack.Rounds[0].Themes[0].Questions[0].TimeToAnswer == 10.0


def test_roundtrip_bytes_preserves_manifest_and_media():
    """Load real .pq, save to bytes, reload and compare."""
    from pqeditor.io import load_pq, save_pq_bytes, load_pq_bytes
    lp = load_pq(PQ1)
    # Save with normalization (Q1 timer 10.0 now) — reload should be stable
    data = save_pq_bytes(lp.pack, lp.media)
    lp2 = load_pq_bytes(data)
    # Pack fields equal (except normalized timer)
    assert lp2.pack.Name == lp.pack.Name
    assert lp2.pack.Description == lp.pack.Description
    assert lp2.pack.Difficulty == lp.pack.Difficulty
    assert len(lp2.pack.Rounds) == len(lp.pack.Rounds)
    # Second round-trip should be byte-identical manifest (stable)
    data2 = save_pq_bytes(lp2.pack, lp2.media)
    # Compare manifests JSON semantic equality
    def manifest_from_bytes(b):
        import io
        z = zipfile.ZipFile(io.BytesIO(b))
        return json.loads(z.read("manifest.json").decode("utf-8"))
    m1 = manifest_from_bytes(data)
    m2 = manifest_from_bytes(data2)
    assert m1 == m2
    # Media bytes preserved
    for k, v in lp.media.items():
        assert k in lp2.media
        assert hashlib.sha256(v).hexdigest() == hashlib.sha256(lp2.media[k]).hexdigest()


def test_build_reference_pack_roundtrip():
    """Build the Step-2 reference pack in code and check it round-trips."""
    from pqeditor.io import build_reference_pack, save_pq_bytes, load_pq_bytes
    lp = build_reference_pack()
    # Replace dummy media with consistent bytes for test stability
    # Already dummy, just ensure Icon etc. consistent
    data = save_pq_bytes(lp.pack, lp.media)
    lp2 = load_pq_bytes(data)
    assert lp2.pack.Name == "ТестовыйПак"
    assert len(lp2.pack.Rounds) == 2
    assert len(lp2.pack.Rounds[0].Themes[0].Questions) == 5
    assert lp2.pack.Rounds[1].Themes[0].Questions[0].IsFinal is True
    # Price for Leading Hints equals max clue price
    q_hints = lp2.pack.Rounds[0].Themes[0].Questions[4]
    assert q_hints.Price == 50
    assert q_hints.RevealingClues[0].Price == 50


def test_validation_catches_errors():
    from pqeditor.io import build_reference_pack, validate_loaded_pack
    from copy import deepcopy
    lp = build_reference_pack()
    # Valid should have no errors (except missing real media bytes are present as dummy, but our dummy keys use correct names)
    errs = validate_loaded_pack(lp)
    # GuessNumber answer numeric is "1" so no error; but we have dummy media keys matching pack.Icon etc. — should be valid
    # Our build_reference_pack media keys include all Picture/Audio/Video paths, so expect 0 errors
    assert errs == [], f"unexpected validation errors: {errs}"
    # Break it: remove a quiz option
    lp2 = deepcopy(lp)
    lp2.pack.Rounds[0].Themes[0].Questions[3].MultipleChoice = ["only one"]
    errs2 = validate_loaded_pack(lp2)
    assert any("Quiz" in e for e in errs2)
    # Break GuessNumber numeric
    lp3 = deepcopy(lp)
    lp3.pack.Rounds[0].Themes[1].Questions[0].Answer.Text = "not a number"
    errs3 = validate_loaded_pack(lp3)
    assert any("numeric" in e for e in errs3)
    # Break Final theme count
    lp4 = deepcopy(lp)
    from pqeditor.model import Question
    lp4.pack.Rounds[1].Themes[0].Questions.append(Question(Price=10, Text="extra", IsFinal=True))
    errs4 = validate_loaded_pack(lp4)
    assert any("Final" in e for e in errs4)


def test_version_preserved():
    from pqeditor.io import load_pq
    lp = load_pq(PQ1)
    assert lp.pack.Version == 22
    # save and reload keeps version
    from pqeditor.io import save_pq_bytes, load_pq_bytes
    data = save_pq_bytes(lp.pack, lp.media)
    lp2 = load_pq_bytes(data)
    assert lp2.pack.Version == 22
    import io, json, zipfile
    m = json.loads(zipfile.ZipFile(io.BytesIO(data)).read("manifest.json").decode("utf-8"))
    assert m["Version"] == 22


def test_media_settings_defaults_present():
    from pqeditor.io import load_pq
    lp = load_pq(PQ1)
    q = lp.pack.Rounds[0].Themes[0].Questions[0]
    # All edit params should be present with defaults
    assert q.ImageEditParams.CropL == 0.0
    assert q.ImageEditParams.CropR == 1.0
    assert q.AudioEditParams.Volume == 1.0
    assert q.VideoEditParams.Speed == 1.0
