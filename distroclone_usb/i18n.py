"""Shared EN/IT/ES/FR/DE catalogs for desktop and privileged helper."""
import json
import locale
import os
from pathlib import Path

LANGUAGES = {'en': 'English', 'it': 'Italiano', 'es': 'Español', 'fr': 'Français', 'de': 'Deutsch'}
ROWS = json.loads(Path(__file__).with_name('translations.json').read_text())
CATALOGS = {'en': {key: key for key in ROWS}}
for index, code in enumerate(('it', 'es', 'fr', 'de')):
    CATALOGS[code] = {key: values[index] for key, values in ROWS.items()}
ENV_LANGUAGE = next((os.environ[key] for key in ('LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG')
                     if os.environ.get(key)), locale.getlocale()[0] or 'en')
_language = ENV_LANGUAGE[:2] if ENV_LANGUAGE[:2] in LANGUAGES else 'en'


def get_language():
    return _language


def set_language(code):
    global _language
    if code not in LANGUAGES:
        raise ValueError('Unsupported language')
    _language = code


def tr(text):
    return CATALOGS[_language].get(text, text)
