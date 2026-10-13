"""Ações permitidas; respostas do modelo nunca são executadas."""
import os, re, subprocess, webbrowser, sys
from pathlib import Path
from core import normal,open_target
from i18n import tr

APPS={'spotify':'spotify:','discord':str(Path(os.getenv('LOCALAPPDATA',''))/'Discord/Update.exe')}

def open_app(name,custom):
    if name in custom:
        path=Path(custom[name]).expanduser()
        if not path.exists():return tr('O caminho cadastrado não existe.','The configured path does not exist.')
        os.startfile(str(path));return tr('Abrindo ','Opening ')+name+'.'
    if name=='spotify':os.startfile('spotify:');return tr('Abrindo Spotify.','Opening Spotify.')
    if name=='discord':
        path=Path(APPS['discord'])
        if not path.is_file():return tr('Cadastre o caminho do Discord nas configurações.','Set the Discord path in Settings.')
        subprocess.Popen([str(path),'--processStart','Discord.exe']);return tr('Abrindo Discord.','Opening Discord.')
    if name in ('navegador','chatgpt'):
        opened=webbrowser.open('https://chatgpt.com' if name=='chatgpt' else 'https://www.google.com')
        if not opened:return tr('Não consegui abrir o navegador.','Could not open the browser.')
        return tr('Abrindo ','Opening ')+name+'.'
    return open_target(name)

def media(action):
    import win32api, win32con
    key={'pausar musica':0xB3,'continuar musica':0xB3,'proxima musica':0xB0,'musica anterior':0xB1,'aumentar volume':0xAF,'diminuir volume':0xAE,'silenciar':0xAD}[action]
    repeats=3 if 'volume' in action else 1
    for _ in range(repeats):win32api.keybd_event(key,0,0,0);win32api.keybd_event(key,0,win32con.KEYEVENTF_KEYUP,0)
    return tr('Comando de mídia enviado ao Windows.','Media command sent to Windows.')

def window_action(action):
    import win32gui,win32con,win32api
    if action=='alternar janela':
        win32api.keybd_event(win32con.VK_MENU,0,0,0);win32api.keybd_event(win32con.VK_TAB,0,0,0);win32api.keybd_event(win32con.VK_TAB,0,win32con.KEYEVENTF_KEYUP,0);win32api.keybd_event(win32con.VK_MENU,0,win32con.KEYEVENTF_KEYUP,0)
    else:win32gui.ShowWindow(win32gui.GetForegroundWindow(),win32con.SW_MINIMIZE if action=='minimizar janela' else win32con.SW_MAXIMIZE)
    return tr('Comando enviado à janela ativa.','Command sent to the active window.')

def search_files(term):
    if len(term)<3:return tr('Use pelo menos três caracteres para procurar um arquivo.','Use at least three characters to find a file.')
    found=[];count=0
    # Não percorre o disco inteiro. Também evita links de diretório.
    for base in (Path.home()/'Documents',Path.home()/'Downloads'):
        if not base.exists():continue
        for root,dirs,files in os.walk(base,followlinks=False):
            dirs[:]=[d for d in dirs if d not in ('.venv','node_modules','.git') and not (Path(root)/d).is_symlink()]
            for name in files:
                count+=1
                if normal(term) in normal(name):found.append(str(Path(root)/name))
                if len(found)>=15 or count>=10000:break
            if len(found)>=15 or count>=10000:break
    return '\n'.join(found) if found else tr('Nenhum arquivo encontrado em Documentos/Downloads (limite: 10 mil arquivos).','No files found in Documents/Downloads (limit: 10,000 files).')

def create_folder(name):
    if not name or name in ('.','..') or re.search(r'[\\/:*?"<>|]',name):return tr('Use um nome simples de pasta, sem caminho.','Use a simple folder name, not a path.')
    base=Path.home()/'Documents'
    if not base.is_dir():return tr('A pasta Documentos padrão não está disponível.','The default Documents folder is unavailable.')
    path=base/name
    if path.exists():return tr('Essa pasta já existe.','That folder already exists.')
    path.mkdir();return tr('Pasta criada: ','Folder created: ')+str(path)

def set_startup(enabled,project):
    if os.name!='nt':raise ValueError(tr('Inicialização disponível somente no Windows.','Startup is only available on Windows.'))
    import win32com.client
    path=Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs/Startup/Jarvis Zeti.lnk'
    if enabled:
        shell=win32com.client.Dispatch('WScript.Shell');shortcut=shell.CreateShortCut(str(path))
        shortcut.TargetPath=sys.executable if getattr(sys,'frozen',False) else str(Path(project)/'.venv/Scripts/pythonw.exe');shortcut.Arguments='--background' if getattr(sys,'frozen',False) else '"'+str(Path(project)/'main.py')+'" --background'
        shortcut.WorkingDirectory=str(project);shortcut.Description='Jarvis 3.0';shortcut.save()
    elif path.exists():path.unlink()

def create_shortcut(project):
    import win32com.client
    shell=win32com.client.Dispatch('WScript.Shell');path=Path(shell.SpecialFolders('Desktop'))/'Jarvis Zeti.lnk'
    shortcut=shell.CreateShortCut(str(path));shortcut.TargetPath=sys.executable if getattr(sys,'frozen',False) else str(Path(project)/'.venv/Scripts/pythonw.exe');shortcut.Arguments='' if getattr(sys,'frozen',False) else '"'+str(Path(project)/'main.py')+'"';shortcut.WorkingDirectory=str(project);shortcut.Description='Jarvis 3.0';shortcut.save();return str(path)
