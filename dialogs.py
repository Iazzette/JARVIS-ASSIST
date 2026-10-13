from pathlib import Path
from datetime import datetime,timedelta
from PySide6.QtCore import Qt,Signal,QDateTime,QLocale
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,QTextEdit,QComboBox,QCheckBox,QSpinBox,QDoubleSpinBox,QDateTimeEdit,QPushButton,QDialogButtonBox,QListWidget,QListWidgetItem,QMessageBox,QWidget,QTabWidget,QApplication)
from i18n import tr,language
from core import normal
from organizer import parse_plan

def buttons(dialog,layout):
    box=QDialogButtonBox();ok=box.addButton(tr('Salvar','Save'),QDialogButtonBox.ButtonRole.AcceptRole);box.addButton(tr('Cancelar','Cancel'),QDialogButtonBox.ButtonRole.RejectRole)
    box.accepted.connect(dialog.accept);box.rejected.connect(dialog.reject);layout.addWidget(box);return box

class TaskDialog(QDialog):
    def __init__(self,parent=None,row=None):
        super().__init__(parent);self.setWindowTitle(tr('Editar tarefa','Edit task') if row else tr('Nova tarefa','New task'));self.resize(510,340)
        layout=QVBoxLayout(self);f=QFormLayout();layout.addLayout(f)
        self.title=QLineEdit(row[1] if row else '');f.addRow(tr('O que fazer','What to do'),self.title)
        self.project=QLineEdit(row[2] if row else tr('Pessoal','Personal'));f.addRow(tr('Projeto','Project'),self.project)
        self.priority=QComboBox();self.priority.addItems([tr('Alta','High'),tr('Normal','Normal'),tr('Baixa','Low')]);self.priority.setCurrentIndex((row[3] if row else 2)-1);f.addRow(tr('Prioridade','Priority'),self.priority)
        self.scheduled=QCheckBox(tr('Me lembrar em uma data e horário','Remind me at a date and time'));self.scheduled.setChecked(bool(row and row[4]));f.addRow(self.scheduled)
        when=datetime.fromisoformat(row[4]) if row and row[4] else datetime.now()+timedelta(hours=1)
        self.date=QDateTimeEdit(QDateTime(when));self.date.setCalendarPopup(True);self.date.setDisplayFormat('MM/dd/yyyy hh:mm AP' if language()=='en-US' else 'dd/MM/yyyy HH:mm');self.date.setEnabled(self.scheduled.isChecked());self.scheduled.toggled.connect(self.date.setEnabled);f.addRow(tr('Quando','When'),self.date)
        hint=QLabel(tr('Os alertas aparecem com o Jarvis aberto, inclusive perto do relógio.','Alerts appear while Jarvis is running, including in the system tray.'));hint.setWordWrap(True);layout.addWidget(hint);buttons(self,layout)
    def accept(self):
        if not self.title.text().strip():self.title.setFocus();return
        due=self.value()[3]
        if due and datetime.fromisoformat(due)<=datetime.now():QMessageBox.information(self,'Jarvis',tr('Escolha um horário futuro.','Choose a future time.'));return
        super().accept()
    def value(self):return (self.title.text().strip(),self.project.text().strip(),self.priority.currentIndex()+1,self.date.dateTime().toPython().isoformat(timespec='seconds') if self.scheduled.isChecked() else None)

class TextDialog(QDialog):
    def __init__(self,title,text='',parent=None):
        super().__init__(parent);self.setWindowTitle(title);self.resize(540,360);layout=QVBoxLayout(self);self.text=QTextEdit();self.text.setPlainText(text);layout.addWidget(self.text);buttons(self,layout)
    def accept(self):
        if self.text.toPlainText().strip():super().accept()

class CollectionDialog(QDialog):
    def __init__(self,store,kind,parent=None):
        super().__init__(parent);self.store=store;self.kind=kind;self.setWindowTitle(tr('Memórias autorizadas','Approved memories'));self.resize(640,430)
        layout=QVBoxLayout(self);hint=QLabel(tr('Informações pessoais que você escolheu guardar. Podem ser usadas como contexto nas respostas.','Personal information you chose to save. It can be used as context in responses.'));hint.setWordWrap(True);layout.addWidget(hint);self.list=QListWidget();layout.addWidget(self.list);row=QHBoxLayout();layout.addLayout(row)
        for title,fn in [(tr('Adicionar','Add'),self.add),(tr('Editar','Edit'),self.edit),(tr('Excluir','Delete'),self.delete)]:b=QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
        self.refresh()
    def refresh(self):
        self.list.clear()
        for row in self.store.memories():
            item=QListWidgetItem(row[1]);item.setData(Qt.ItemDataRole.UserRole,row);self.list.addItem(item)
    def add(self):
        d=TextDialog(tr('Nova memória','New memory'),parent=self)
        if d.exec()==QDialog.DialogCode.Accepted:self.store.unique_memory(d.text.toPlainText().strip());self.refresh()
    def edit(self):
        item=self.list.currentItem()
        if not item:return
        row=item.data(Qt.ItemDataRole.UserRole);d=TextDialog(tr('Editar memória','Edit memory'),row[1],self)
        if d.exec()==QDialog.DialogCode.Accepted:self.store.edit_memory(row[0],d.text.toPlainText().strip());self.refresh()
    def delete(self):
        item=self.list.currentItem()
        if item and QMessageBox.question(self,'Jarvis',tr('Excluir esta memória?','Delete this memory?'))==QMessageBox.StandardButton.Yes:self.store.delete_memory(item.data(Qt.ItemDataRole.UserRole)[0]);self.refresh()

class ReviewDialog(QDialog):
    def __init__(self,items,parent=None):
        super().__init__(parent);self.setWindowTitle(tr('Revise antes de salvar','Review before saving'));self.resize(680,450);layout=QVBoxLayout(self)
        hint=QLabel(tr('Marque apenas o que deseja guardar. Tarefas sugeridas ficam sem prazo até você escolher uma data.','Select only what you want to save. Suggested tasks have no deadline until you choose a date.'));hint.setWordWrap(True);layout.addWidget(hint);self.list=QListWidget();self.list.setWordWrap(True);layout.addWidget(self.list)
        kinds={'nota':tr('Anotação','Note'),'tarefa':tr('Tarefa','Task'),'memoria':tr('Memória','Memory')}
        for entry in items:
            item=QListWidgetItem(kinds[entry['kind']]+' · '+entry['text']);item.setData(Qt.ItemDataRole.UserRole,entry);item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Unchecked);self.list.addItem(item)
        buttons(self,layout)
    def selected(self):return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count()) if self.list.item(i).checkState()==Qt.CheckState.Checked]

class ExportDialog(QDialog):
    def __init__(self,store,parent=None):
        super().__init__(parent);self.store=store;self.setWindowTitle(tr('Levar contexto para o ChatGPT','Take context to ChatGPT'));self.resize(690,530);layout=QVBoxLayout(self);row=QHBoxLayout();layout.addLayout(row);self.options={}
        for key,label in [('history',tr('Conversa','Conversation')),('notes',tr('Anotações','Notes')),('tasks',tr('Agenda','Agenda')),('memories',tr('Memórias','Memories'))]:
            c=QCheckBox(label);c.setChecked(key!='memories');c.toggled.connect(self.preview);row.addWidget(c);self.options[key]=c
        self.text=QTextEdit();layout.addWidget(self.text);label=QLabel(tr('Revise e copie. Você cola o texto aqui no ChatGPT; nada é enviado automaticamente.','Review and copy. Paste the text into ChatGPT yourself; nothing is sent automatically.'));label.setWordWrap(True);layout.addWidget(label);b=QPushButton(tr('Copiar contexto','Copy context'));b.clicked.connect(self.copy);layout.addWidget(b);self.preview()
    def preview(self):
        if hasattr(self,'text'):self.text.setPlainText(self.store.export(**{k:c.isChecked() for k,c in self.options.items()}))
    def copy(self):QApplication.clipboard().setText(self.text.toPlainText());self.accept()

class ImportDialog(QDialog):
    def __init__(self,store,parent=None):
        super().__init__(parent);self.store=store;self.setWindowTitle(tr('Importar tarefas','Import tasks'));self.resize(630,440);layout=QVBoxLayout(self);layout.addWidget(QLabel(tr('Cole uma lista com uma tarefa por linha, começando com - ou 1.','Paste one task per line, starting with - or 1.')));self.text=QTextEdit();layout.addWidget(self.text);b=QPushButton(tr('Revisar tarefas','Review tasks'));b.clicked.connect(self.review);layout.addWidget(b)
    def review(self):
        entries=[{'kind':'tarefa','text':t} for t in parse_plan(self.text.toPlainText())]
        if not entries:QMessageBox.information(self,'Jarvis',tr('Não encontrei itens na lista.','No list items found.'));return
        d=ReviewDialog(entries,self)
        if d.exec()==QDialog.DialogCode.Accepted:
            for i in d.selected():self.store.unique_task(i['text'])
            self.accept()

class Preferences(QDialog):
    request_download=Signal(str);preview_voice=Signal(dict)
    def __init__(self,cfg,parent=None):
        super().__init__(parent);self.cfg=cfg;self.busy=False;self.setWindowTitle(tr('Ajustes de voz e funcionamento','Voice and behavior settings'));self.resize(680,720)
        layout=QVBoxLayout(self);self.tabs=QTabWidget();layout.addWidget(self.tabs)
        def tab(label):w=QWidget();f=QFormLayout(w);f.setVerticalSpacing(12);self.tabs.addTab(w,label);return f
        f=tab(tr('Idioma e voz','Language and voice'))
        self.locale=QComboBox();self.locale.addItem('Português (Brasil)','pt-BR');self.locale.addItem('English (US)','en-US');self.locale.setCurrentIndex(1 if cfg['locale']=='en-US' else 0);f.addRow(tr('Idioma de todo o Jarvis','Language for all of Jarvis'),self.locale)
        self.speech=QCheckBox(tr('Ler as respostas em voz alta','Read responses aloud'));self.speech.setChecked(cfg['speech']);f.addRow(self.speech)
        self.tts=QComboBox();self.tts.addItem(tr('Feminina do Windows · offline','Windows female voice · offline'),'windows');self.tts.addItem(tr('Feminina natural · online','Natural female voice · online'),'neural');self.tts.setCurrentIndex(max(0,self.tts.findData(cfg['tts'])));f.addRow(tr('Voz','Voice'),self.tts)
        self.consent=QCheckBox(tr('Permitir enviar o texto da fala ao serviço de voz online','Allow spoken text to be sent to the online voice service'));self.consent.setChecked(cfg['online_voice']);f.addRow(self.consent)
        note=QLabel(tr('Online: Francisca em PT-BR e Jenny em EN-US. Precisa de internet. Offline: usa uma voz feminina disponível no Windows.','Online: Francisca for PT-BR and Jenny for EN-US. Requires internet. Offline: uses an available Windows female voice.'));note.setWordWrap(True);f.addRow(note)
        self.speed=QSpinBox();self.speed.setRange(100,260);self.speed.setValue(int(cfg['tts_rate']));f.addRow(tr('Velocidade','Rate'),self.speed)
        self.volume=QDoubleSpinBox();self.volume.setRange(.05,1);self.volume.setSingleStep(.05);self.volume.setValue(cfg['tts_volume']);f.addRow(tr('Volume','Volume'),self.volume)
        b=QPushButton(tr('Ouvir uma amostra','Hear a sample'));b.clicked.connect(self.sample);f.addRow(b)
        f=tab(tr('Microfone','Microphone'));self.listening=QCheckBox(tr('Escutar a palavra Jarvis','Listen for Jarvis'));self.listening.setChecked(cfg['listening']);f.addRow(self.listening)
        self.mic=QComboBox();self.mic.addItem(tr('Padrão do Windows','Windows default'),None)
        try:
            import sounddevice as sd
            for i,d in enumerate(sd.query_devices()):
                if d['max_input_channels']>0:self.mic.addItem(f"{i} · {d['name']}",i)
        except Exception:pass
        self.mic.setCurrentIndex(max(0,self.mic.findData(cfg['mic'])));f.addRow(tr('Dispositivo','Device'),self.mic)
        self.pause=QDoubleSpinBox();self.pause.setRange(1,6);self.pause.setSingleStep(.2);self.pause.setValue(cfg['pause_seconds']);self.pause.setSuffix(' s');f.addRow(tr('Pausa antes de enviar','Pause before sending'),self.pause)
        self.continuous=QCheckBox(tr('Continuar ouvindo depois da resposta','Keep listening after a response'));self.continuous.setChecked(cfg['continuous']);f.addRow(self.continuous)
        self.session=QSpinBox();self.session.setRange(5,90);self.session.setValue(int(cfg['session_seconds']));self.session.setSuffix(' s');f.addRow(tr('Tempo para continuar a conversa','Conversation window'),self.session)
        self.sensitivity=QComboBox()
        for label,key in [(tr('Baixa','Low'),'baixa'),(tr('Normal','Normal'),'normal'),(tr('Alta','High'),'alta')]:self.sensitivity.addItem(label,key)
        self.sensitivity.setCurrentIndex(max(0,self.sensitivity.findData(cfg['sensitivity'])));f.addRow(tr('Sensibilidade da ativação','Wake word sensitivity'),self.sensitivity)
        self.barge=QCheckBox(tr('Interromper a fala dizendo Jarvis (use fones)','Interrupt speech by saying Jarvis (use headphones)'));self.barge.setChecked(cfg['barge_in']);f.addRow(self.barge)
        label=QLabel(tr('Sem fones, a própria voz do Jarvis pode ativar essa interrupção. O botão Parar funciona sempre.','Without headphones, Jarvis may trigger its own interruption. The Stop button always works.'));label.setWordWrap(True);f.addRow(label)
        f=tab(tr('Rotina','Routine'));self.flags={}
        for key,label in [('startup',tr('Iniciar com o Windows','Start with Windows')),('background',tr('Abrir perto do relógio','Start in the system tray')),('brief',tr('Mostrar a agenda na primeira abertura do dia','Show agenda on the first launch of the day')),('brief_voice',tr('Ler o resumo diário em voz alta','Read the daily briefing aloud')),('alerts',tr('Alertas de bateria, CPU e memória','Battery, CPU and memory alerts')),('auto_search',tr('Pesquisar perguntas sobre informações atuais','Search questions about current information')),('economy',tr('Economizar memória entre os pedidos','Release model memory between requests'))]:c=QCheckBox(label);c.setChecked(cfg[key]);self.flags[key]=c;f.addRow(c)
        f=tab(tr('Avançado','Advanced'));self.model=QComboBox();self.model.setEditable(True);self.model.addItem(cfg['model']);f.addRow(tr('Modelo Ollama','Ollama model'),self.model)
        for label,kind in [(tr('Baixar modelo da IA','Download AI model'),'ollama'),(tr('Baixar reconhecimento PT/EN','Download PT/EN speech recognition'),'stt')]:b=QPushButton(label);b.clicked.connect(lambda checked=False,k=kind:self.request_download.emit(k));f.addRow(b)
        self.custom=QTextEdit();self.custom.setMaximumHeight(130);self.custom.setPlainText('\n'.join(f'{k}={v}' for k,v in cfg['custom_apps'].items()));f.addRow(tr('Aplicativos: nome=caminho','Apps: name=path'),self.custom)
        hint=QLabel(tr('Exemplo: projeto=C:\\Projetos\\LikaManager\nUse nomes simples e caminhos completos.','Example: project=C:\\Projects\\LikaManager\nUse simple names and full paths.'));hint.setWordWrap(True);f.addRow(hint)
        self.progress=QLabel('');self.progress.setWordWrap(True);layout.addWidget(self.progress);self.box=buttons(self,layout)
    def value(self):
        custom={}
        for line in self.custom.toPlainText().splitlines():
            if not line.strip():continue
            if '=' not in line:raise ValueError(tr('Use nome=caminho nos aplicativos.','Use name=path for apps.'))
            key,value=line.split('=',1);key=normal(key);value=value.strip().strip('"')
            if not key or not Path(value).is_absolute():raise ValueError(tr('Use um nome e um caminho completo.','Use a name and a full path.'))
            custom[key]=value
        return {**self.cfg,'locale':self.locale.currentData(),'tts':self.tts.currentData(),'online_voice':self.consent.isChecked(),'speech':self.speech.isChecked(),'tts_rate':self.speed.value(),'tts_volume':self.volume.value(),'listening':self.listening.isChecked(),'mic':self.mic.currentData(),'pause_seconds':self.pause.value(),'continuous':self.continuous.isChecked(),'session_seconds':self.session.value(),'sensitivity':self.sensitivity.currentData(),'barge_in':self.barge.isChecked(),'model':self.model.currentText().strip(),'custom_apps':custom,**{k:c.isChecked() for k,c in self.flags.items()}}
    def validate(self):
        cfg=self.value()
        if cfg['tts']=='neural' and not cfg['online_voice']:raise ValueError(tr('Para usar a voz online, marque a permissão de envio do texto ou escolha a voz do Windows.','To use online voice, allow sending the text or select the Windows voice.'))
        if not cfg['model']:raise ValueError(tr('Informe o modelo.','Enter a model name.'))
        return cfg
    def accept(self):
        try:self.validate()
        except ValueError as e:QMessageBox.information(self,'Jarvis',str(e));return
        if not self.busy:super().accept()
    def sample(self):
        try:self.preview_voice.emit(self.validate())
        except ValueError as e:QMessageBox.information(self,'Jarvis',str(e))
    def set_busy(self,value):self.busy=value;self.box.setEnabled(not value);self.tabs.setEnabled(not value)
    def reject(self):
        if not self.busy:super().reject()
    def closeEvent(self,event):
        if self.busy:event.ignore()
        else:event.accept()
