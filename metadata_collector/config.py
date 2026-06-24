import json, os
from pathlib import Path
APP_DIR = Path(os.environ.get('FLETCHAUDIO_HOME', Path.home()/'.fletchaudio'))
APP_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_DB_URL = f"sqlite:///{APP_DIR/'fletchaudio.sqlite3'}"
SETTINGS_FILE = APP_DIR/'settings.json'
DEFAULT_SETTINGS = {'theme':'System','working_directory':None,'staging_dir':None,'conversion_output_dir':None,'archive_dir':None,'abs_library_dir':None,'abs_url':None,'abs_api_key':None}
def load_settings():
    try:
        loaded=json.loads(SETTINGS_FILE.read_text())
        return {**DEFAULT_SETTINGS, **loaded}
    except Exception: return dict(DEFAULT_SETTINGS)
def save_settings(settings): SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
