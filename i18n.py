"""Idioma único para interface, respostas, reconhecimento e síntese."""
_current = 'pt-BR'
def set_language(value):
    global _current
    _current = value if value in ('pt-BR','en-US') else 'pt-BR'
def language(): return _current
def tr(pt,en,locale=None): return en if (locale or _current)=='en-US' else pt
def language_name(locale=None): return tr('português brasileiro','American English',locale)
def speech_code(locale=None): return 'en' if (locale or _current)=='en-US' else 'pt'
def neural_voice(locale=None): return 'en-US-JennyNeural' if (locale or _current)=='en-US' else 'pt-BR-FranciscaNeural'
def date_text(value):
    from datetime import datetime
    dt=datetime.fromisoformat(value) if isinstance(value,str) else value
    return dt.strftime('%m/%d/%Y %I:%M %p' if _current=='en-US' else '%d/%m/%Y %H:%M')

def apply_qt_locale(app):
    from PySide6.QtCore import QLocale,QTranslator,QLibraryInfo
    QLocale.setDefault(QLocale('en_US' if language()=='en-US' else 'pt_BR'))
    previous=getattr(app,'_jarvis_translator',None)
    if previous:app.removeTranslator(previous)
    app._jarvis_translator=None
    if language()=='pt-BR':
        translator=QTranslator(app);path=QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        if translator.load('qtbase_pt_BR',path) or translator.load('qtbase_pt',path):app.installTranslator(translator);app._jarvis_translator=translator
