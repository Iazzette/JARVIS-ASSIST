"""Explicit scheduling in PT/EN; missing dates/times trigger a question."""
from datetime import datetime,timedelta
import re
import dateparser
from core import normal

NUMBERS={'um':1,'dois':2,'uma':1,'duas':2,'tres':3,'quatro':4,'cinco':5,'seis':6,'sete':7,'oito':8,'nove':9,'dez':10,'onze':11,'doze':12,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,'quinze':15,'fifteen':15,'vinte':20,'twenty':20,'trinta':30,'thirty':30}
DATE=r'(?:depois de amanh[aã]|amanh[aã]|hoje|tomorrow|today|(?:pr[oó]xima\s+)?(?:segunda|ter[cç]a|quarta|quinta|sexta)(?:-feira)?|s[aá]bado|domingo|(?:next\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|\d{1,2}/\d{1,2}(?:/\d{4})?|\d{4}-\d{2}-\d{2})'
CLOCK=r'(?:(?:[aà]s|at)\s+\d{1,2}(?:(?::|h)\d{0,2})?(?:\s*(?:a\.?m\.?|p\.?m\.?|da manh[aã]|da tarde|da noite))?)'
WHEN=re.compile(r'\b(?:daqui a|em|in)\s+\d+\s*(?:minutos?|minutes?|horas?|hours?|segundos?|seconds?)\b|'+DATE+r'(?:[, ]+'+CLOCK+r')?|'+CLOCK,re.I)

def normalize_time(text):
    t=normal(text)
    for word,n in NUMBERS.items():t=re.sub(r'\b'+word+r'\b',str(n),t)
    t=t.replace(' e meia',':30').replace('half past ', '')
    t=re.sub(r'\bas (\d{1,2}) horas?\b',r'as \1',t)
    t=t.replace('meio dia','as 12:00').replace('meia noite','as 00:00')
    return t

def parse_when(text,base=None):
    base=base or datetime.now();t=normalize_time(text)
    relative=re.fullmatch(r'(?:daqui a|em|in)\s+(\d+)\s*(minutos?|minutes?|horas?|hours?|segundos?|seconds?)',t.strip(' ,'))
    if relative:
        n=int(relative.group(1));unit=relative.group(2);seconds=n*(3600 if unit.startswith(('hora','hour')) else 60 if unit.startswith(('minuto','minute')) else 1)
        if not 1<=seconds<=366*86400:return None
        return base+timedelta(seconds=seconds)
    if not re.search(r'\b(?:as|at)\s*\d',t):return None
    if not re.search(DATE,t,re.I):return None
    t=re.sub(r'\bda tarde\b|\bda noite\b','pm',t);t=re.sub(r'\bda manha\b','am',t)
    t=re.sub(r'\b(as|at)\s+(\d{1,2})(?![\d:])\b',r'\1 \2:00',t)
    dt=dateparser.parse(t,languages=['pt','en'],settings={'RELATIVE_BASE':base,'PREFER_DATES_FROM':'future','DATE_ORDER':'DMY' if not re.search(r'\b(at|today|tomorrow)\b',t) else 'MDY','RETURN_AS_TIMEZONE_AWARE':False})
    return dt

def parse_request(text,existing=None,base=None):
    base=base or datetime.now();existing=existing or {};raw=text.strip()
    raw=re.sub(r'^(?:jarvis[, ]*)?(?:por favor[, ]*|please[, ]*)?(?:me lembr[ae]|lembre-me|lembrete|remind me|set a reminder)\s*','',raw,flags=re.I)
    # Search normalized time but retain the user's title through raw matches first.
    norm=normalize_time(raw);matches=list(WHEN.finditer(norm))
    when=' '.join(m.group() for m in matches).strip()
    # The same patterns with written numbers allow removing the time from the original title.
    rawpattern=WHEN.pattern.replace(r'\d{1,2}',r'(?:\d{1,2}|'+ '|'.join(NUMBERS)+r')').replace(r'\d+',r'(?:\d+|'+ '|'.join(NUMBERS)+r')')
    title=re.sub(rawpattern,' ',raw,flags=re.I)
    title=re.sub(r'\s+',' ',title).strip(' ,.;')
    title=re.sub(r'^(?:de |para |to |about )','',title,flags=re.I).strip(' ,.;')
    title=re.sub(r'\s+(?:de|para|to|at|as)$','',title,flags=re.I).strip()
    if existing:
        if when and not re.search(DATE,when,re.I) and existing.get('when'):when=existing['when']+' '+when
        elif not when:when=existing.get('when','')
        if existing.get('title'):title=existing['title']
    due=parse_when(when,base) if when else None
    # Never silently shift explicit past dates.
    if due and due<=base:raise ValueError('past')
    return {'title':title,'when':when,'due':due.isoformat(timespec='seconds') if due else None}
