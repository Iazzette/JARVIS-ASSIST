"""Jarvis 3.0: download em blocos, com retomada e validacao SHA-256."""
from pathlib import Path
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request

DATA = Path(os.getenv('JARVIS_DATA_DIR', str(Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'JarvisZeti')))
WHISPER_DIR = DATA / 'whisper-small'
FILES = ('config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt')
BASE = 'https://huggingface.co/Systran/faster-whisper-small/resolve/536b0662742c02347bc0e980a01041f333bce120/'
BLOCK_BYTES = 8 * 1024 * 1024
MAX_FAILURES = 12
MODEL_SHA256 = '3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def validate(path, name, expected_sha=None):
    if not path.is_file() or not path.stat().st_size:
        return False
    if expected_sha:
        return digest(path) == expected_sha
    if name.endswith('.json'):
        try:
            json.loads(path.read_text('utf-8'))
        except (ValueError, OSError, UnicodeError):
            return False
    return True


def fetch(url, target, progress=lambda text: None, expected_sha=None):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + '.part')
    meta_path = target.with_name(target.name + '.part.json')
    try:
        meta = json.loads(meta_path.read_text('utf-8'))
    except (ValueError, OSError):
        meta = {}
    # An unidentified partial file must not be mixed with a different resource.
    if part.exists() and meta.get('url') != url:
        part.rename(part.with_name(part.name + '.old-' + str(time.time_ns())))
    failures = 0
    while True:
        offset = part.stat().st_size if part.exists() else 0
        total = meta.get('total') if meta.get('url') == url else None
        if offset and total == offset:
            progress('Conferindo integridade / Checking integrity: ' + target.name)
            if not validate(part, target.name, expected_sha):
                part.rename(part.with_name(part.name + '.invalid-' + str(time.time_ns())))
                meta_path.unlink(missing_ok=True)
                raise ValueError('Arquivo invalido. Execute novamente para baixar uma copia integra: ' + target.name)
            part.replace(target)
            meta_path.unlink(missing_ok=True)
            progress(target.name + ': OK')
            return
        headers = {'User-Agent': 'JarvisZeti/3.0.1', 'Accept-Encoding': 'identity',
                   'Range': f'bytes={offset}-{offset + BLOCK_BYTES - 1}'}
        if offset and meta.get('etag'):
            headers['If-Range'] = meta['etag']
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=180) as response:
                status = response.status
                tag = response.headers.get('ETag')
                if status == 206:
                    match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
                    if not match:
                        raise OSError('Resposta parcial sem tamanho valido.')
                    start, end, remote_total = map(int, match.groups())
                    if start != offset or end < start or end >= remote_total or end >= offset + BLOCK_BYTES:
                        raise OSError('O servidor retornou um bloco diferente do solicitado; bytes nao foram adicionados.')
                    if offset and ((total and total != remote_total) or (meta.get('etag') and tag and meta['etag'] != tag)):
                        raise ValueError('O arquivo no servidor mudou. A parte salva foi mantida para verificacao.')
                    expected = end - start + 1
                    total = remote_total
                elif status == 200 and offset == 0:
                    expected = int(response.headers.get('Content-Length', 0))
                    if not expected:
                        raise OSError('O servidor nao informou o tamanho do arquivo.')
                    total = expected
                else:
                    raise OSError('O servidor nao aceitou a retomada. A parte baixada continua guardada.')
                meta = {'url': url, 'total': total, 'etag': tag or meta.get('etag')}
                temporary = meta_path.with_suffix('.tmp')
                temporary.write_text(json.dumps(meta), encoding='utf-8')
                temporary.replace(meta_path)
                received = 0
                last = 0.0
                with part.open('ab') as destination:
                    while received < expected:
                        chunk = response.read(min(256 * 1024, expected - received))
                        if not chunk:
                            break
                        destination.write(chunk)
                        received += len(chunk)
                        if time.monotonic() - last >= 1 or offset + received == total:
                            done = offset + received
                            progress(f'{target.name}: {done / 1024**2:.1f} / {total / 1024**2:.1f} MB ({done / total:.0%})')
                            last = time.monotonic()
                if received != expected:
                    raise OSError('Conexao interrompida antes de terminar este bloco.')
                failures = 0
        except (OSError, urllib.error.URLError) as error:
            failures += 1
            saved = part.stat().st_size if part.exists() else 0
            if failures >= MAX_FAILURES:
                raise OSError(f'Download pausado. {saved / 1024**2:.1f} MB preservados. Execute o mesmo comando para continuar. Causa: {error}') from error
            progress(f'Conexao interrompida. {saved / 1024**2:.1f} MB preservados. Retomando ({failures}/{MAX_FAILURES})...')
            time.sleep(min(failures, 3))


def download_whisper(progress=lambda text: None):
    for name in FILES:
        path = WHISPER_DIR / name
        expected = MODEL_SHA256 if name == 'model.bin' else None
        if path.exists():
            progress('Verificando / Checking: ' + name)
        if validate(path, name, expected):
            progress(name + ': ja instalado / already installed')
            continue
        fetch(BASE + name, path, progress, expected)
    return 'Whisper PT/EN OK'


if __name__ == '__main__':
    try:
        print(download_whisper(lambda text: print(text, flush=True)))
    except KeyboardInterrupt:
        print('\nPausado. Os blocos recebidos foram preservados. Execute novamente para continuar.')
        raise SystemExit(1)
    except Exception as error:
        print('\n' + str(error))
        raise SystemExit(1)
