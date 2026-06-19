import json, os
from pathlib import Path
APP_DIR = Path(os.environ.get('FLETCHAUDIO_HOME', Path.home()/'.fletchaudio'))
APP_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_DB_URL = f"sqlite:///{APP_DIR/'fletchaudio.sqlite3'}"
SETTINGS_FILE = APP_DIR/'settings.json'
def load_settings():
    try: return json.loads(SETTINGS_FILE.read_text())
    except Exception: return {'theme':'System','working_directory':None}
def save_settings(settings): SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
