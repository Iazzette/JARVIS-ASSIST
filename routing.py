"""Deterministic bilingual commands. No generated shell code is executed."""
import re
from core import normal

APPS={'github':'github','youtube':'youtube','google':'google','chrome':'google','vs code':'vs code','vscode':'vs code','visual studio code':'vs code','visual code':'vs code','code':'vs code','spotify':'spotify','spotfy':'spotify','espotifai':'spotify','discord':'discord','calculadora':'calculadora','calculator':'calculadora','bloco de notas':'bloco de notas','notepad':'bloco de notas','documentos':'documentos','documents':'documentos','downloads':'downloads','browser':'navegador','navegador':'navegador','chatgpt':'chatgpt','chat gpt':'chatgpt'}
MEDIA={'pause music':'pausar musica','pause the music':'pausar musica','pausa a musica':'pausar musica','pausar musica':'pausar musica','pausa musica':'pausar musica','play music':'continuar musica','resume music':'continuar musica','continua a musica':'continuar musica','continuar musica':'continuar musica','next song':'proxima musica','next track':'proxima musica','proxima musica':'proxima musica','proxima faixa':'proxima musica','previous song':'musica anterior','musica anterior':'musica anterior','volume up':'aumentar volume','turn up the volume':'aumentar volume','aumenta o volume':'aumentar volume','aumentar volume':'aumentar volume','volume down':'diminuir volume','turn down the volume':'diminuir volume','abaixa o volume':'diminuir volume','diminui o volume':'diminuir volume','diminuir volume':'diminuir volume','mute':'silenciar','mute audio':'silenciar','silenciar':'silenciar'}

def clean(text):
    t=normal(text).strip(' .!?')
    t=re.sub(r'^(jarvis|arvis|jervis)[, :]*','',t)
    t=re.sub(r'^(?:por favor[, ]*|please[, ]*|voce pode |pode |consegue |can you |could you |would you )','',t)
    return re.sub(r'[, ]*(?:por favor|please)$','',t).strip(' .!?')

def action_for(text,custom=None):
    t=clean(text);custom=custom or {}
    if t in ('cancelar','pare','parar','cancela','silencio','stop','cancel','be quiet'):return 'cancel',None
    if t in ('encerrar conversa','encerre a conversa','fim da conversa','end conversation','stop listening for now'):return 'end_session',None
    if t in ('abre o painel','abrir painel','show panel','open panel'):return 'panel',None
    if t in ('modo compacto','janela flutuante','compact mode','floating window'):return 'compact',None
    if t in ('resumo do dia','o que tenho para hoje','o que tenho que fazer hoje','minhas tarefas','minhas pendencias','agenda','my tasks','my agenda','what do i need to do today','what do i have to do today','daily summary'):return 'brief',None
    if t in ('minhas notas','minhas anotacoes','listar notas','mostra minhas notas','my notes','show my notes','list notes'):return 'notes',None
    if t in ('minhas memorias','o que voce lembra de mim','my memories','what do you remember about me'):return 'memories',None
    if t in ('preparar contexto','preparar contexto para o chatgpt','export context','context for chatgpt'):return 'export',None
    if t in ('organizar conversa','salvar pontos desta conversa','resumir conversa','save points from this conversation','summarize conversation'):return 'organize',None
    # Capture original spelling for saved text.
    request=re.sub(r'^(?:jarvis[, ]+)?(?:voc[eê] pode |pode |consegue |can you |could you |would you )','',text,flags=re.I)
    m=re.match(r'^(?:jarvis[, ]+)?(?:por favor[, ]*|please[, ]*)?(anota(?:r|e)?|guarda uma ideia|ideia|note|take a note|write down|idea|lembre que|guarde que|remember that|nova tarefa|new task)\s*[:,-]?\s+(.+)',request,re.I)
    if m:
        prefix=normal(m.group(1));a='memory' if prefix in ('lembre que','guarde que','remember that') else 'task' if prefix in ('nova tarefa','new task') else 'note'
        return a,m.group(2).strip()
    if re.match(r'^(?:me lembr[ae]|lembrete|lembre-me|remind me|set a reminder)\b',t):return 'reminder',text
    m=re.match(r'^(?:pesquisa(?:r)?|pesquise|procura na internet|search(?: the web)?(?: for)?|look up)\s+(.+)',t)
    if m:return 'search',m.group(1)
    for prefix,a in [(r'(?:concluir|conclua|finalizar|complete|finish)','complete'),(r'(?:excluir|apagar|delete|remove)','delete_task'),(r'(?:adiar|adie|postpone|snooze)','postpone'),(r'(?:editar|edite|edit)','edit_task')]:
        m=re.fullmatch(prefix+r'\s+(?:a |the )?(?:tarefa|lembrete|task|reminder)\s+(.+)',t)
        if m:return a,m.group(1)
    if t.startswith(('buscar anotacao ','buscar nota ','find note ','search notes ')):return 'find_note',re.sub(r'^(buscar anotacao|buscar nota|find note|search notes)\s+','',t)
    m=re.fullmatch(r'(?:localiza(?:r)? arquivo|buscar arquivo|find file) (.+)',t)
    if m:return 'find_file',m.group(1)
    m=re.fullmatch(r'(?:cria(?:r)? pasta|create folder) (.+)',t)
    if m:return 'create_folder',m.group(1)
    if t in MEDIA:return 'media',MEDIA[t]
    windows={'minimizar janela':'minimizar janela','minimize window':'minimizar janela','maximizar janela':'maximizar janela','maximize window':'maximizar janela','alternar janela':'alternar janela','switch window':'alternar janela'}
    if t in windows:return 'window',windows[t]
    if t in ('processos','quais processos','quem consome mais memoria','o que consome mais memoria','top processes','memory usage by app'):return 'processes',None
    if any(w in t for w in ('meu computador','my computer','minha bateria','my battery','uso da cpu','cpu usage','uso de memoria','memory usage')) or t in ('bateria','battery','cpu','memoria','ram','disco','disk','status do computador','computer status'):return 'system',None
    # Chains contain only explicit app/media commands, not arbitrary prose.
    pieces=re.split(r'\s+(?:e depois|e|and then|and)\s+',text)
    if 1<len(pieces)<=4:
        actions=[action_for(p,custom) for p in pieces]
        if all(a in ('open','media') for a,_ in actions):return 'chain',actions
    targets={**APPS,**{normal(k):k for k in custom}}
    m=re.fullmatch(r'(?:abre|abrir|abra|inicia|iniciar|execute|open|launch|start)\s+(?:o |a |the )?(.+)',t)
    if m:return ('open',targets[m.group(1)]) if m.group(1) in targets else ('unknown_app',m.group(1))
    if re.fullmatch(r'(?:coloca|coloque|toca|toque|play) (?:uma |some )?(?:musica|music)(?: no| on)? spotify',t):return 'spotify_play',None
    # A short, uncertain phrase naming a known app is clarified, never executed.
    # This also handles imperfectly transcribed verbs without inventing an action.
    if len(t.split())<=6 and not re.match(r'^(?:nao|nunca|no|never|do not|dont|qual|quem|como|por que|porque|what|why|how|who|gosto|adoro|amo|i like|i love)\b',t):
        named={v for k,v in targets.items() if re.search(r'\b'+re.escape(k)+r'\b',t)}
        if len(named)==1:return 'confirm_open',named.pop()
    if re.search(r'\b(?:noticias|news|cotacao|exchange rate|previsao do tempo|weather|resultado de hoje|latest|atualizado|atualmente|hoje|today)\b',t):return 'current',text
    if re.search(r'\b(?:versiculo|versiculos|bible verse|scripture|salmo|psalm)\b',t):return 'search',text
    return 'chat',None
