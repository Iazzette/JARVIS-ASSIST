from __future__ import annotations
import html,json,logging,os,re,sys,threading,time,sqlite3,zipfile,tempfile
from pathlib import Path
from datetime import datetime
import requests
from PySide6.QtCore import Qt,QThread,Signal,QTimer,QLockFile,QLocale
from PySide6.QtGui import QIcon,QPixmap,QPainter,QColor,QShortcut,QKeySequence
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTextBrowser,QLineEdit,QFrame,QSystemTrayIcon,QMenu,QDialog,QListWidget,QListWidgetItem,QTabWidget,QMessageBox,QComboBox,QFileDialog)
from core import DATA,settings,save_settings,snapshot,computer_reply,backup_data,models,start_ollama,BASE_URL
from i18n import tr,set_language,language,date_text,apply_qt_locale
from organizer import Organizer
from engine import Assistant
from desktop import set_startup,create_shortcut
from downloads import download_whisper
from voice import Listener,Speaker
from hud import CoreViz
from dialogs import Preferences,TaskDialog,TextDialog,CollectionDialog,ReviewDialog,ExportDialog,ImportDialog

PROJECT=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
logging.basicConfig(filename=DATA/'jarvis.log',level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
STYLE='''
QWidget {background:#0b0912;color:#eee8fa;font-family:"Segoe UI";font-size:14px;}
QLabel {background:transparent;} QLabel#muted {color:#a79bb9;font-size:12px;} QLabel#title {font-size:27px;font-weight:700;color:#c1a0ff;letter-spacing:3px;}
QLabel#heading {font-size:22px;font-weight:600;} QFrame#card {background:#15101f;border:1px solid #352645;border-radius:12px;}
QPushButton {background:#251b35;border:1px solid #4d3765;border-radius:8px;padding:9px 14px;}
QPushButton:hover {background:#39264d;border-color:#ac7ee8;} QPushButton#primary {background:#7844ca;border-color:#b88bed;font-weight:600;}
QPushButton:disabled {color:#766b85;background:#191320;} QLineEdit,QTextEdit,QListWidget,QComboBox,QDateTimeEdit,QSpinBox,QDoubleSpinBox {background:#120d1c;border:1px solid #49325f;border-radius:7px;padding:8px;selection-background-color:#7443b5;}
QTextBrowser {background:#100c19;border:1px solid #30223f;border-radius:12px;padding:14px;} QListWidget::item {padding:10px;border-bottom:1px solid #2b203b;} QListWidget::item:selected {background:#37244f;}
QTabWidget::pane {border:0;} QTabBar::tab {background:#0b0912;color:#a79bb9;padding:13px 22px;border-bottom:2px solid #231a32;} QTabBar::tab:selected {color:#e6d7ff;border-bottom:2px solid #b98aff;}
QMenu {background:#191123;} QMenu::item {padding:9px 20px;} QMenu::item:selected {background:#43305a;}
QToolTip {background:#241632;color:#eee8fa;border:1px solid #8d5bbd;}
QCheckBox {spacing:9px;padding:3px;} QScrollBar:vertical {background:#110c19;width:10px;} QScrollBar::handle:vertical {background:#4e3766;min-height:25px;border-radius:5px;}
'''
STATUS={'waiting':('Em espera · diga Jarvis','Standby · say Jarvis'),'session':('Pode continuar falando','You can keep talking'),'listening':('Ouvindo · fale no seu ritmo','Listening · take your time'),'transcribing':('Entendendo sua frase','Transcribing your sentence'),'processing':('Preparando a resposta','Preparing a response'),'speaking':('Falando','Speaking'),'voice_loading':('Preparando a voz','Preparing the voice'),'listening_loading':('Preparando o microfone','Preparing the microphone'),'paused':('Microfone pausado','Microphone paused'),'repeat':('Não entendi · pode repetir','I did not catch that · please repeat'),'error':('Atenção ao microfone','Microphone needs attention'),'stopping':('Interrompendo','Stopping')}

def app_icon():
    p=QPixmap(64,64);p.fill(Qt.GlobalColor.transparent);painter=QPainter(p);painter.setRenderHint(QPainter.RenderHint.Antialiasing);painter.setBrush(QColor('#151020'));painter.setPen(QColor('#b68cff'));painter.drawEllipse(4,4,56,56);painter.drawEllipse(15,15,34,34);painter.drawText(p.rect(),Qt.AlignmentFlag.AlignCenter,'J');painter.end();return QIcon(p)

class Job(QThread):
    ready=Signal(object);failed=Signal(str);delta=Signal(str);progress=Signal(str)
    def __init__(self,fn):super().__init__();self.fn=fn
    def run(self):
        try:self.ready.emit(self.fn(self))
        except Exception as e:logging.exception('Job');self.failed.emit(str(e))

class Monitor(QThread):
    sample=Signal(dict)
    def __init__(self):super().__init__();self.stopping=threading.Event()
    def run(self):
        while not self.stopping.is_set():
            try:self.sample.emit(snapshot())
            except Exception:logging.exception('Monitor')
            self.stopping.wait(3)

class Compact(QDialog):
    def __init__(self,parent):
        super().__init__(parent,Qt.WindowType.Window|Qt.WindowType.WindowStaysOnTopHint);self.setWindowTitle(tr('Jarvis · janela flutuante','Jarvis · floating window'));self.resize(350,280)
        layout=QVBoxLayout(self);self.viz=CoreViz();layout.addWidget(self.viz);self.status=QLabel('');self.status.setWordWrap(True);layout.addWidget(self.status);row=QHBoxLayout();layout.addLayout(row)
        for label,fn in [(tr('Painel','Panel'),parent.show_panel),(tr('Falar','Talk'),parent.listen_now),(tr('Parar','Stop'),parent.interrupt)]:b=QPushButton(label);b.clicked.connect(fn);row.addWidget(b)

class Window(QMainWindow):
    def __init__(self,no_audio=False,store=None,offline=False):
        super().__init__();backup_data();self.cfg=settings();set_language(self.cfg['locale']);self.store=store or Organizer();self.engine=Assistant(self.store,lambda:self.cfg)
        self.no_audio=no_audio;self.offline=offline;self.talking=threading.Event();self.cancel=threading.Event();self.jobs=[];self.worker=None;self.listener=None;self.speaker=None;self.pref=None;self.compact=None;self.closing=False;self.voice_online=False;self.restart_pending=False;self.retry_count=0;self.stream='';self.metrics=None;self.alerts={};self.high_cpu=0;self.state_key='waiting';self.session_after=True;self.alert_queue=[];self.display=[(m['role'],m['content']) for m in self.store.history(30)];self.staged_request=None;self.listen_requested=False
        self.setWindowTitle('Jarvis 3.0 · Zeti');self.setWindowIcon(app_icon());self.resize(1100,840);self.setMinimumSize(890,700)
        self.tray=QSystemTrayIcon(app_icon(),self);self.tray.activated.connect(lambda r:self.show_panel() if r==QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.build();self.tray.show()
        self.stop_shortcut=QShortcut(QKeySequence('Escape'),self);self.stop_shortcut.activated.connect(self.interrupt)
        if not no_audio:
            self.speaker=Speaker(self.talking,lambda:self.cfg);self.speaker.status.connect(self.set_state);self.speaker.completed.connect(self.speech_finished);self.speaker.error.connect(self.voice_warning);self.speaker.start();self.start_listener()
        self.monitor=Monitor();self.monitor.sample.connect(self.update_metrics);self.monitor.start()
        self.poll=QTimer(self);self.poll.timeout.connect(self.scheduler);self.poll.start(1000)
        self.stream_timer=QTimer(self);self.stream_timer.timeout.connect(self.render_if_streaming);self.stream_timer.start(120)
        if not offline:self.job(lambda j:start_ollama(),lambda _:None,lambda _:None)
        self.start_time=time.monotonic()
    def button(self,text,fn,primary=False):
        b=QPushButton(text);b.clicked.connect(fn)
        if primary:b.setObjectName('primary')
        return b
    def build(self):
        apply_qt_locale(QApplication.instance())
        old=self.takeCentralWidget()
        if old:old.deleteLater()
        root=QWidget();self.setCentralWidget(root);outer=QVBoxLayout(root);outer.setContentsMargins(24,18,24,16);outer.setSpacing(12)
        header=QHBoxLayout();title=QLabel('JARVIS  /  3.0');title.setObjectName('title');header.addWidget(title);header.addStretch();badge=QLabel(tr('ASSISTENTE PESSOAL · ZETI','PERSONAL ASSISTANT · ZETI'));badge.setObjectName('muted');header.addWidget(badge)
        self.language_box=QComboBox();self.language_box.addItem('PT-BR','pt-BR');self.language_box.addItem('EN-US','en-US');self.language_box.setCurrentIndex(1 if self.cfg['locale']=='en-US' else 0);self.language_box.setToolTip(tr('Muda interface, fala e respostas','Changes interface, speech and responses'));self.language_box.currentIndexChanged.connect(self.change_language);header.addWidget(self.language_box);outer.addLayout(header)
        self.metric_button=self.button(tr('CPU —  ·  MEMÓRIA —  ·  BATERIA —','CPU —  ·  MEMORY —  ·  BATTERY —'),self.computer_details);self.metric_button.setObjectName('metrics');outer.addWidget(self.metric_button)
        self.alert_label=QLabel('');self.alert_label.setWordWrap(True);self.alert_label.setStyleSheet('color:#e2c5ff;padding:4px');self.alert_label.hide();outer.addWidget(self.alert_label)
        self.tabs=QTabWidget();outer.addWidget(self.tabs,1)
        page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(0,6,0,0);self.tabs.addTab(page,tr('Conversa','Conversation'))
        self.viz=CoreViz();layout.addWidget(self.viz)
        row=QHBoxLayout();self.state=QLabel('');self.state.setStyleSheet('color:#c6a6ff;font-size:15px;font-weight:600');row.addWidget(self.state);row.addStretch();self.mic=self.button('',self.toggle_mic);row.addWidget(self.mic);layout.addLayout(row)
        self.partial=QLabel(tr('Diga “Jarvis” ou clique em Falar agora.','Say “Jarvis” or click Talk now.'));self.partial.setObjectName('muted');self.partial.setWordWrap(True);layout.addWidget(self.partial)
        self.messages=QTextBrowser();self.messages.setOpenExternalLinks(True);layout.addWidget(self.messages,1)
        row=QHBoxLayout();self.talk=self.button(tr('Falar agora','Talk now'),self.listen_now);row.addWidget(self.talk);self.input=QLineEdit();self.input.setPlaceholderText(tr('Converse ou peça algo…','Chat or ask for something…'));self.input.returnPressed.connect(self.send);row.addWidget(self.input,1);self.send_btn=self.button(tr('Enviar','Send'),self.send,True);row.addWidget(self.send_btn);layout.addLayout(row)
        row=QHBoxLayout();self.stop_button=self.button(tr('Parar','Stop'),self.interrupt);row.addWidget(self.stop_button);self.done_speaking=self.button(tr('Terminei de falar','Done speaking'),self.submit_audio);row.addWidget(self.done_speaking);row.addStretch();more=self.button(tr('Mais opções','More options'),lambda:None);menu=QMenu(more)
        for title,fn in [(tr('Salvar pontos desta conversa','Save points from this conversation'),lambda:self.submit(tr('salvar pontos desta conversa','save points from this conversation'))),(tr('Janela flutuante','Floating window'),self.show_compact),(tr('Limpar conversa','Clear conversation'),self.clear)]:menu.addAction(title).triggered.connect(fn)
        more.setMenu(menu);row.addWidget(more);layout.addLayout(row)
        page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(8,20,8,4);self.tabs.addTab(page,tr('Agenda','Agenda'));heading=QLabel(tr('Seu próximo passo','Your next step'));heading.setObjectName('heading');layout.addWidget(heading);self.agenda_hint=QLabel(tr('Tarefas com horário avisam por notificação e voz. O Jarvis precisa estar aberto.','Scheduled tasks notify you with a message and voice. Jarvis must be running.'));self.agenda_hint.setWordWrap(True);self.agenda_hint.setObjectName('muted');layout.addWidget(self.agenda_hint);self.task_list=QListWidget();self.task_list.setWordWrap(True);self.task_list.itemDoubleClicked.connect(self.edit_task);layout.addWidget(self.task_list,1);row=QHBoxLayout();layout.addLayout(row)
        for title,fn in [(tr('+ Nova tarefa','+ New task'),self.new_task),(tr('Editar','Edit'),self.edit_task),(tr('Concluir','Complete'),self.complete_task),(tr('Adiar 1 hora','Snooze 1 hour'),self.postpone_task),(tr('Excluir','Delete'),self.delete_task)]:row.addWidget(self.button(title,fn))
        row=QHBoxLayout();layout.addLayout(row);row.addWidget(self.button(tr('Ouvir resumo','Hear briefing'),lambda:self.submit(tr('resumo do dia','daily summary'))));row.addWidget(self.button(tr('Importar tarefas','Import tasks'),self.import_plan));row.addStretch()
        page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(8,20,8,4);self.tabs.addTab(page,tr('Anotações','Notes'));heading=QLabel(tr('Suas ideias, no mesmo lugar','Your ideas, in one place'));heading.setObjectName('heading');layout.addWidget(heading);self.note_filter=QLineEdit();self.note_filter.setPlaceholderText(tr('Buscar nas anotações…','Search notes…'));self.note_filter.textChanged.connect(self.refresh_notes);layout.addWidget(self.note_filter);self.notes_list=QListWidget();self.notes_list.setWordWrap(True);self.notes_list.itemDoubleClicked.connect(self.edit_note);layout.addWidget(self.notes_list,1);row=QHBoxLayout();layout.addLayout(row)
        for title,fn in [(tr('+ Anotação','+ Note'),self.new_note),(tr('Editar','Edit'),self.edit_note),(tr('Excluir','Delete'),self.delete_note),(tr('Copiar contexto para ChatGPT','Copy context for ChatGPT'),self.export_context)]:row.addWidget(self.button(title,fn))
        page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(16,24,16,8);layout.setSpacing(14);self.tabs.addTab(page,tr('Ajustes','Settings'));heading=QLabel(tr('Deixe do seu jeito','Make it yours'));heading.setObjectName('heading');layout.addWidget(heading)
        self.settings_description=QLabel(tr('Português e inglês, voz feminina, microfone e rotina de inicialização.','Portuguese and English, female voice, microphone and startup routine.'));self.settings_description.setWordWrap(True);layout.addWidget(self.settings_description)
        for title,fn in [(tr('Idioma, voz e funcionamento','Language, voice and behavior'),self.preferences),(tr('Memórias que o Jarvis pode usar','Memories Jarvis may use'),lambda:CollectionDialog(self.store,'memories',self).exec()),(tr('Criar cópia de segurança dos meus dados','Back up my data'),self.backup),(tr('Criar atalho na área de trabalho','Create desktop shortcut'),self.shortcut),(tr('Abrir pasta de dados e diagnóstico','Open data and diagnostics folder'),self.open_data)]:layout.addWidget(self.button(title,fn))
        layout.addStretch();privacy=QLabel(tr('A conversa usa Gemini quando configurado ou Ollama local. Gemini recebe o texto e o contexto usado nas respostas. Pesquisas enviam a consulta ao buscador. A voz online só envia texto quando habilitada.','Conversation uses Gemini when configured or local Ollama. Gemini receives text and response context. Searches send the query to a search engine. Online voice sends text only when enabled.'));privacy.setWordWrap(True);privacy.setObjectName('muted');layout.addWidget(privacy)
        foot=QLabel(tr('ESC interrompe  ·  Fechar a janela mantém o Jarvis perto do relógio','ESC stops  ·  Closing the window keeps Jarvis in the system tray'));foot.setObjectName('muted');outer.addWidget(foot)
        menu=QMenu(self)
        for title,fn in [(tr('Abrir Jarvis','Open Jarvis'),self.show_panel),(tr('Janela flutuante','Floating window'),self.show_compact),(tr('Pausar / ativar microfone','Pause / enable microphone'),self.toggle_mic),(tr('Sair','Quit'),self.quit)]:menu.addAction(title).triggered.connect(fn)
        self.tray.setContextMenu(menu);self.render();self.refresh_tasks();self.refresh_notes();self.apply_mic();self.set_state(self.state_key)
        if self.metrics:self.update_metrics(self.metrics)
    def busy(self):return bool(self.worker and self.worker.isRunning())
    def job(self,fn,ready,failed=None):
        j=Job(fn);self.jobs.append(j);j.ready.connect(ready);j.failed.connect(failed or self.background_error);j.finished.connect(lambda:self.release_job(j));j.start();return j
    def release_job(self,j):
        if j in self.jobs:self.jobs.remove(j)
        if self.worker is j:self.worker=None
        j.deleteLater()
    def background_error(self,text):self.tray.showMessage('Jarvis',text[:220])
    def set_state(self,key):
        if self.closing:return
        self.done_speaking.setEnabled(key in ('listening','session'))
        self.state_key=key;text=tr(*STATUS[key]) if key in STATUS else key;self.state.setText(text);self.viz.state=key;self.tray.setToolTip('Jarvis 3.0 · '+text)
        if self.compact:self.compact.status.setText(text);self.compact.viz.state=key
    def render(self):
        entries=self.display[-30:]+([('assistant',self.stream+' ▌')] if self.stream else [])
        if not entries:entries=[('assistant',tr('Oi, Zeti. Pode falar comigo, pedir para abrir um programa ou guardar uma ideia.\nPara começar: “Jarvis, abre o Spotify”.','Hi, Zeti. Talk to me, ask me to open an app, or save an idea.\nTry: “Jarvis, open Spotify”.'))]
        parts=[]
        for role,text in entries:
            content=html.escape(text).replace('\n','<br>');content=re.sub(r'(https?://[^\s<>]+)',r'<a style="color:#c9a4ff" href="\1">\1</a>',content)
            parts.append(f'<p style="color:#bfa4e8;font-size:11px"><b>{"JARVIS" if role=="assistant" else tr("VOCÊ","YOU")}</b></p><p style="font-size:15px;color:#eee8fa;line-height:150%">{content}</p><br>')
        self.messages.setHtml(''.join(parts));self.messages.verticalScrollBar().setValue(self.messages.verticalScrollBar().maximum())
    def render_if_streaming(self):
        if self.stream:self.render()
    def append(self,role,text,save=True):
        if not text:return
        self.display.append((role,text));self.display=self.display[-30:]
        if save:self.store.save(role,text)
        self.render()
    def send(self):
        text=self.input.text().strip()
        if text and not self.busy():self.input.clear();self.submit(text)
    def submit(self,text):
        if self.closing:return
        from routing import action_for
        if action_for(text)[0]=='cancel':self.interrupt();return
        if self.busy():self.alert_label.setText(tr('Aguarde a resposta ou clique em Parar.','Wait for the response or click Stop.'));self.alert_label.show();return
        if self.speaker and self.talking.is_set():
            self.staged_request=text;self.speaker.interrupt();return
        self.cancel=threading.Event();self.stream='';self.append('user',text);self.send_btn.setEnabled(False);self.language_box.setEnabled(False);self.session_after=True
        if self.listener:self.listener.busy.set()
        self.set_state('processing');self.tabs.setCurrentIndex(0)
        self.worker=self.job(lambda j:self.engine.handle(text,self.cancel,j.delta.emit),self.finish,self.failed);self.worker.delta.connect(self.on_delta)
    def on_delta(self,token):
        if not self.cancel.is_set():self.stream+=token
    def finish(self,result):
        if self.closing:return
        event=result.get('event','');text=result.get('text','')
        if self.cancel.is_set():text=tr('Pedido interrompido.','Request stopped.');event='cancel'
        if event=='review':
            dialog=ReviewDialog(result['data'],self)
            if dialog.exec()==QDialog.DialogCode.Accepted:
                for item in dialog.selected():
                    if item['kind']=='nota':self.store.unique_note(item['text'])
                    elif item['kind']=='memoria':self.store.unique_memory(item['text'])
                    else:self.store.unique_task(item['text'])
                text=tr(f'{len(dialog.selected())} pontos salvos.',f'{len(dialog.selected())} points saved.')
            else:text=tr('Nenhum ponto foi salvo.','No points were saved.')
        elif event=='panel':self.show_panel()
        elif event=='compact':self.show_compact()
        elif event=='agenda':self.tabs.setCurrentIndex(1)
        elif event=='export':self.export_context()
        elif event=='edit_task':self.edit_task(row=result['data'])
        self.session_after=event not in ('end_session','cancel','error','export');self.stream='';self.append('assistant',text);self.send_btn.setEnabled(True);self.language_box.setEnabled(True);self.refresh_tasks();self.refresh_notes();self.set_state('waiting' if self.cfg['listening'] else 'paused')
        if self.cfg['speech'] and self.speaker and text and not self.cancel.is_set():self.speaker.say(text)
        elif self.listener:self.listener.resume(self.session_after)
    def failed(self,text):
        if 'HTTPConnectionPool' in text or 'Connection refused' in text:text=tr('O Ollama não respondeu. Abra o Ollama e confira o modelo nos Ajustes. Os comandos locais continuam disponíveis.','Ollama did not respond. Open Ollama and check the model in Settings. Local commands remain available.')
        self.finish({'text':tr('Não consegui concluir: ','Could not complete: ')+text,'event':'error'})
    def interrupt(self):
        self.cancel.set();self.engine.pending=None;self.staged_request=None;self.session_after=False
        if self.speaker:self.speaker.interrupt()
        if self.listener:self.listener.end_session();self.listener.resume(False)
        self.set_state('stopping' if self.busy() else 'waiting')
    def voice_interrupt(self):
        self.interrupt();self.listen_requested=True
    def speech_finished(self):
        if self.closing:return
        if self.listen_requested and self.listener:
            self.listen_requested=False;self.listener.resume(False);self.listener.listen_now();return
        if self.staged_request:
            text=self.staged_request;self.staged_request=None;QTimer.singleShot(20,lambda:self.submit(text));return
        if self.listener and not self.busy():self.listener.resume(self.session_after)
        if not self.busy():self.set_state('waiting' if self.cfg['listening'] else 'paused')
    def voice_warning(self,text):self.alert_label.setText(text);self.alert_label.show();self.tray.showMessage('Jarvis',text[:220])
    def mic_error(self,text):
        self.set_state('error');self.partial.setText(text);self.retry_count+=1
        if self.retry_count<=2 and self.cfg['listening'] and not self.closing:QTimer.singleShot(3000,self.recover_listener)
    def mic_online(self,value):self.voice_online=value;self.apply_mic()
    def start_listener(self):
        if self.no_audio or self.closing or not self.cfg['listening'] or self.listener and self.listener.isRunning():return
        self.listener=Listener(self.talking,lambda:self.cfg);self.listener.command.connect(self.submit);self.listener.cancelled.connect(self.voice_interrupt);self.listener.status.connect(self.set_state);self.listener.error.connect(self.mic_error);self.listener.online.connect(self.mic_online);self.listener.level.connect(self.audio_level);self.listener.partial.connect(lambda text:self.partial.setText(text));self.listener.finished.connect(self.listener_finished);self.listener.start()
    def listener_finished(self):
        if self.restart_pending and not self.closing:self.restart_pending=False;QTimer.singleShot(100,self.start_listener)
    def recover_listener(self):
        if not self.closing and self.cfg['listening'] and (not self.listener or not self.listener.isRunning()):self.start_listener()
    def restart_listener(self):
        self.retry_count=0
        if self.listener and self.listener.isRunning():self.restart_pending=True;self.listener.stop()
        else:self.start_listener()
    def audio_level(self,value):
        self.viz.level=value
        if self.compact:self.compact.viz.level=value
    def apply_mic(self):
        self.mic.setText(tr('Microfone pausado','Microphone paused') if not self.cfg['listening'] else tr('Microfone ativo','Microphone on') if self.voice_online else tr('Reiniciar microfone','Restart microphone'))
    def toggle_mic(self):
        if self.cfg['listening'] and not self.voice_online:self.restart_listener();return
        self.cfg['listening']=not self.cfg['listening'];save_settings(self.cfg)
        if self.cfg['listening']:self.restart_listener()
        elif self.listener:self.listener.enabled.clear();self.listener.end_session();self.set_state('paused');self.audio_level(0.)
        self.apply_mic()
    def listen_now(self):
        if self.speaker and self.talking.is_set():self.speaker.interrupt();self.listen_requested=True;return
        if self.busy():self.interrupt();return
        if not self.cfg['listening']:self.cfg['listening']=True;save_settings(self.cfg);self.restart_listener()
        if self.listener and self.listener.isRunning() and self.voice_online:self.listener.listen_now()
        else:self.restart_listener();self.partial.setText(tr('Aguarde o microfone ficar ativo e clique novamente.','Wait for the microphone to become active, then click again.'))
    def submit_audio(self):
        if self.listener:self.listener.submit_audio()
    def change_language(self):
        value=self.language_box.currentData()
        if value==self.cfg['locale']:return
        if self.busy():return
        if self.speaker:self.speaker.interrupt()
        self.cfg['locale']=value;set_language(value);QLocale.setDefault(QLocale('en_US' if value=='en-US' else 'pt_BR'));save_settings(self.cfg);self.engine.pending=None
        if self.compact:self.compact.close();self.compact.deleteLater();self.compact=None
        self.build();self.restart_listener()
    def update_metrics(self,s):
        if self.closing:return
        self.metrics=s;b='—' if s['battery'] is None else f"{s['battery']:.0f}%"
        self.metric_button.setText(tr(f"CPU {s['cpu']:.0f}%   ·   MEMÓRIA {s['ram']:.0f}%   ·   BATERIA {b}",f"CPU {s['cpu']:.0f}%   ·   MEMORY {s['ram']:.0f}%   ·   BATTERY {b}"))
        if not self.cfg['alerts']:return
        now=time.monotonic();self.high_cpu=self.high_cpu+1 if s['cpu']>=self.cfg['cpu_limit'] else 0;alerts=[]
        if s['battery'] is not None and not s['plugged'] and s['battery']<=self.cfg['battery_limit']:alerts.append(('battery',tr('Bateria baixa: ','Low battery: ')+b))
        if s['ram']>=self.cfg['ram_limit']:alerts.append(('ram',tr('Memória quase cheia. Fechar aplicativos pode melhorar a resposta.','Memory is nearly full. Closing apps may improve response time.')))
        if self.high_cpu>=10:alerts.append(('cpu',tr('CPU elevada por cerca de 30 segundos.','High CPU usage for about 30 seconds.')))
        for key,text in alerts:
            if now-self.alerts.get(key,-100000)>self.cfg['alert_minutes']*60:self.tray.showMessage('Jarvis',text);self.alerts[key]=now
    def computer_details(self):
        if self.metrics:QMessageBox.information(self,tr('Seu computador','Your computer'),computer_reply(self.metrics))
    def refresh_tasks(self):
        selected=self.task_list.currentItem();id=selected.data(Qt.ItemDataRole.UserRole)[0] if selected else None;self.task_list.clear()
        for row in self.store.tasks():
            date=date_text(row[4]) if row[4] else tr('Sem data','No date');past=bool(row[4] and datetime.fromisoformat(row[4])<datetime.now());prefix=tr('ATRASADA · ','OVERDUE · ') if past else ''
            item=QListWidgetItem(f'#{row[0]} · {row[1]}\n{prefix}{date}  ·  {row[2]}');item.setData(Qt.ItemDataRole.UserRole,row);self.task_list.addItem(item)
            if row[0]==id:self.task_list.setCurrentItem(item)
    def new_task(self):
        d=TaskDialog(self)
        if d.exec()==QDialog.DialogCode.Accepted:
            title,project,priority,due=d.value();self.store.add_task(title,due,project,priority);self.refresh_tasks()
    def edit_task(self,*args,row=None):
        if row is None:
            item=self.task_list.currentItem()
            if not item:return
            row=item.data(Qt.ItemDataRole.UserRole)
        d=TaskDialog(self,row)
        if d.exec()==QDialog.DialogCode.Accepted:self.store.edit_task(row[0],*d.value());self.refresh_tasks()
    def complete_task(self):
        item=self.task_list.currentItem()
        if item:self.store.complete(item.data(Qt.ItemDataRole.UserRole)[0]);self.refresh_tasks()
    def postpone_task(self):
        item=self.task_list.currentItem()
        if item:self.store.postpone(item.data(Qt.ItemDataRole.UserRole)[0],60);self.refresh_tasks()
    def delete_task(self):
        item=self.task_list.currentItem()
        if item and QMessageBox.question(self,'Jarvis',tr('Excluir esta tarefa?','Delete this task?'))==QMessageBox.StandardButton.Yes:self.store.delete_task(item.data(Qt.ItemDataRole.UserRole)[0]);self.refresh_tasks()
    def refresh_notes(self):
        from core import normal
        query=normal(self.note_filter.text());self.notes_list.clear()
        for row in self.store.notes_full():
            if query and query not in normal(row[1]):continue
            item=QListWidgetItem(row[1]+'\n'+date_text(row[2]));item.setData(Qt.ItemDataRole.UserRole,row);self.notes_list.addItem(item)
    def new_note(self):
        d=TextDialog(tr('Nova anotação','New note'),parent=self)
        if d.exec()==QDialog.DialogCode.Accepted:self.store.unique_note(d.text.toPlainText().strip());self.refresh_notes()
    def edit_note(self,*args):
        item=self.notes_list.currentItem()
        if not item:return
        row=item.data(Qt.ItemDataRole.UserRole);d=TextDialog(tr('Editar anotação','Edit note'),row[1],self)
        if d.exec()==QDialog.DialogCode.Accepted:self.store.update_note(row[0],d.text.toPlainText().strip());self.refresh_notes()
    def delete_note(self):
        item=self.notes_list.currentItem()
        if item and QMessageBox.question(self,'Jarvis',tr('Excluir esta anotação?','Delete this note?'))==QMessageBox.StandardButton.Yes:self.store.delete_note(item.data(Qt.ItemDataRole.UserRole)[0]);self.refresh_notes()
    def scheduler(self):
        if self.closing:return
        for id,title in self.store.due_tasks():
            text=tr(f'Lembrete #{id}: {title}',f'Reminder #{id}: {title}');self.tray.showMessage('Jarvis',text[:220]);self.alert_label.setText(text);self.alert_label.show();self.append('assistant',text);self.alert_queue.append(text);self.store.mark_notified(id);self.refresh_tasks()
        now=datetime.now();today=now.date().isoformat()
        if self.cfg['brief'] and time.monotonic()-self.start_time>8 and self.store.kv('brief_day')!=today:
            text=self.store.brief();self.store.set_kv('brief_day',today);self.tray.showMessage(tr('Jarvis · agenda','Jarvis · agenda'),text[:220]);self.append('assistant',text,False)
            if self.cfg['brief_voice']:self.alert_queue.append(text)
        if self.alert_queue and not self.busy() and not self.talking.is_set():
            text=self.alert_queue.pop(0)
            if self.speaker and self.cfg['speech']:
                self.session_after=False
                if self.listener:self.listener.busy.set()
                self.speaker.say(text)
    def preferences(self):
        if self.busy():return
        self.pref=Preferences(self.cfg,self);self.pref.request_download.connect(self.download);self.pref.preview_voice.connect(self.preview_voice)
        if not self.offline:self.job(lambda j:models(),self.add_models,lambda _:None)
        if self.pref.exec()==QDialog.DialogCode.Accepted:
            previous=self.cfg;self.cfg=self.pref.value()
            if self.cfg['startup']!=previous['startup']:
                try:set_startup(self.cfg['startup'],PROJECT)
                except Exception as e:self.cfg['startup']=previous['startup'];QMessageBox.warning(self,'Jarvis',str(e))
            set_language(self.cfg['locale']);QLocale.setDefault(QLocale('en_US' if self.cfg['locale']=='en-US' else 'pt_BR'));save_settings(self.cfg)
            if self.speaker:self.speaker.interrupt()
            if self.cfg['listening']:self.restart_listener()
            elif self.listener:self.listener.enabled.clear()
            self.build();self.tabs.setCurrentIndex(3)
        self.pref.deleteLater();self.pref=None
    def preview_voice(self,cfg):
        if not self.speaker:return
        if self.talking.is_set():self.speaker.interrupt();QTimer.singleShot(600,lambda:self.preview_voice(cfg));return
        text=tr('Oi, Zeti. Esta é a minha voz em português. Vamos organizar seu dia?','Hi, Zeti. This is my English voice. Ready to organize your day?',cfg['locale']);self.speaker.say(text,cfg)
    def add_models(self,names):
        if self.pref:
            for name in names:
                if self.pref.model.findText(name)<0:self.pref.model.addItem(name)
    def download(self,kind):
        if not self.pref or self.pref.busy:return
        self.pref.set_busy(True);model=self.pref.model.currentText().strip()
        def work(j):
            if kind=='stt':return download_whisper(j.progress.emit)
            start_ollama()
            with requests.post(BASE_URL+'/api/pull',json={'model':model,'stream':True},stream=True,timeout=(5,180)) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:continue
                    item=json.loads(line)
                    if item.get('error'):raise ValueError(item['error'])
                    pct=f" {item['completed']/item['total']:.0%}" if item.get('total') and item.get('completed') else ''
                    j.progress.emit(item.get('status','Download')+pct)
            return tr('Modelo instalado.','Model installed.')
        j=self.job(work,self.download_done,self.download_done);j.progress.connect(self.download_progress)
    def download_progress(self,text):
        if self.pref:self.pref.progress.setText(text)
    def download_done(self,text):
        if self.pref:self.pref.progress.setText(str(text));self.pref.set_busy(False)
    def export_context(self):ExportDialog(self.store,self).exec()
    def import_plan(self):ImportDialog(self.store,self).exec();self.refresh_tasks()
    def backup(self):
        path,_=QFileDialog.getSaveFileName(self,tr('Salvar cópia de segurança','Save backup'),'Jarvis-backup-'+datetime.now().strftime('%Y%m%d')+'.zip','ZIP (*.zip)')
        if not path:return
        try:
            with tempfile.TemporaryDirectory() as td:
                dbpath=Path(td)/'jarvis.sqlite3'
                with self.store.connect() as src,sqlite3.connect(dbpath) as dst:src.backup(dst)
                with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
                    z.write(dbpath,'jarvis.sqlite3')
                    if (DATA/'settings.json').is_file():z.write(DATA/'settings.json','settings.json')
            QMessageBox.information(self,'Jarvis',tr('Cópia de segurança criada.','Backup created.'))
        except Exception as e:QMessageBox.warning(self,'Jarvis',str(e))
    def shortcut(self):
        try:QMessageBox.information(self,'Jarvis',tr('Atalho criado: ','Shortcut created: ')+create_shortcut(PROJECT))
        except Exception as e:QMessageBox.warning(self,'Jarvis',str(e))
    def open_data(self):
        if os.name=='nt':os.startfile(DATA)
    def clear(self):
        if self.busy():return
        if QMessageBox.question(self,'Jarvis',tr('Apagar apenas a conversa? Agenda, anotações e memórias serão mantidas.','Clear only the conversation? Agenda, notes and memories will be kept.'))==QMessageBox.StandardButton.Yes:self.store.clear();self.display=[];self.stream='';self.render()
    def show_panel(self):self.show();self.raise_();self.activateWindow()
    def show_compact(self):
        if self.compact is None:self.compact=Compact(self)
        self.compact.show();self.compact.raise_();self.set_state(self.state_key)
    def closeEvent(self,event):
        if self.closing:event.accept()
        elif QSystemTrayIcon.isSystemTrayAvailable():event.ignore();self.hide()
        else:event.ignore();self.quit()
    def quit(self):
        if self.pref and self.pref.busy:self.show_panel();return
        self.closing=True;self.hide();self.cancel.set();self.poll.stop();self.stream_timer.stop();self.monitor.stopping.set()
        if self.compact:self.compact.hide()
        if self.listener:self.listener.stop()
        if self.speaker:self.speaker.stop()
        self.shutdown=QTimer(self);self.shutdown.timeout.connect(self.try_quit);self.shutdown.start(100)
    def try_quit(self):
        if not any(t and t.isRunning() for t in [self.monitor,self.listener,self.speaker]+self.jobs):self.tray.hide();QApplication.instance().quit()

def main():
    app=QApplication(sys.argv);app.setApplicationName('JarvisZeti');app.setStyleSheet(STYLE);app.setQuitOnLastWindowClosed(False);set_language(settings()['locale']);QLocale.setDefault(QLocale('en_US' if language()=='en-US' else 'pt_BR'))
    lock=QLockFile(str(DATA/'app.lock'));lock.setStaleLockTime(0)
    if not lock.tryLock(100):QMessageBox.information(None,'Jarvis',tr('O Jarvis já está aberto. Procure o ícone perto do relógio.','Jarvis is already running. Look for its system tray icon.'));return 0
    window=Window('--no-audio' in sys.argv,offline='--offline-test' in sys.argv)
    if not (window.cfg['background'] or '--background' in sys.argv) or not QSystemTrayIcon.isSystemTrayAvailable():window.show()
    return app.exec()
if __name__=='__main__':sys.exit(main())
