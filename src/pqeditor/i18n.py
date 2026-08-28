"""UI i18n — English (default) / Russian."""
import json
from pathlib import Path
from platformdirs import user_config_dir

APP_NAME = "PQEditor"
APP_AUTHOR = "PQEditor"

def _config_path() -> Path:
    return Path(user_config_dir(APP_NAME, APP_AUTHOR)) / "config.json"

_current = "en"  # default English

def load_language() -> str:
    global _current
    try:
        p = _config_path()
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            lang = data.get("ui_language", "en")
            if lang in ("en", "ru"):
                _current = lang
    except Exception:
        pass
    return _current

def get_language() -> str:
    return _current

def set_language(lang: str) -> None:
    global _current
    if lang not in ("en", "ru"):
        return
    _current = lang
    # persist to config (merge with recent)
    try:
        p = _config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except: data = {}
        data["ui_language"] = lang
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

def tr(en: str, ru: str) -> str:
    """Return ru if current is ru, else en. English is default."""
    return ru if _current == "ru" else en

# load at import
load_language()
