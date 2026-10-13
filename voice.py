import asyncio,io,json,logging,queue,re,tempfile,threading,time
from pathlib import Path
from collections import deque
import numpy as np
from PySide6.QtCore import QThread,Signal
from core import DATA,normal
from downloads import WHISPER_DIR
from i18n import tr,speech_code,neural_voice
from listening import Utterance,clean_transcription

class Speaker(QThread):
    status=Signal(str);completed=Signal();error=Signal(str)
    def __init__(self,talking,get_cfg):
        super().__init__();self.talking=talking;self.get_cfg=get_cfg;self.items=queue.Queue();self.stopping=threading.Event();self.cancel=threading.Event()
    def say(self,text,cfg=None):self.cancel.clear();self.talking.set();self.items.put((text,dict(cfg or self.get_cfg())))
    def interrupt(self):
        self.cancel.set()
        while True:
            try:self.items.get_nowait()
            except queue.Empty:break
    def stop(self):self.interrupt();self.stopping.set()
    def play(self,samples,samplerate,volume):
        import sounddevice as sd
        samples=np.asarray(samples,dtype=np.float32)
        if samples.ndim==1:samples=samples[:,None]
        samples=np.clip(samples*volume,-1,1)
        with sd.OutputStream(samplerate=samplerate,channels=samples.shape[1],dtype='float32') as out:
            for i in range(0,len(samples),1024):
                if self.cancel.is_set() or self.stopping.is_set():break
                out.write(samples[i:i+1024])
    def windows(self,text,cfg,engine):
        import pyttsx3
        if engine is None:engine=pyttsx3.init()
        voices=engine.getProperty('voices');locale=cfg['locale'];desired=cfg.get('windows_voice_'+locale,'')
        female=next((v for v in voices if v.id==desired),None) if desired else None
        names=('zira','jenny','aria') if locale=='en-US' else ('maria','francisca')
        if female is None:female=next((v for v in voices if any(k in (v.id+' '+v.name).lower() for k in names)),None)
        if female is None:
            self.error.emit(tr('Voz feminina desse idioma indisponível no Windows. Instale o pacote de fala ou selecione Voz online nos Ajustes.','A female voice for this language is unavailable in Windows. Install its speech pack or select Online voice in Settings.',locale));return engine
        engine.setProperty('voice',female.id);engine.setProperty('rate',int(cfg['tts_rate']));engine.setProperty('volume',cfg['tts_volume']);self.status.emit('speaking');engine.say(text);engine.startLoop(False)
        try:
            while engine.isBusy() and not self.cancel.is_set() and not self.stopping.is_set():engine.iterate();time.sleep(.02)
        finally:engine.stop();engine.endLoop()
        return engine
    def run(self):
        import os
        if os.name=='nt':
            import pythoncom
            pythoncom.CoInitialize()
        engine=None
        try:
            while not self.stopping.is_set():
                try:text,cfg=self.items.get(timeout=.2)
                except queue.Empty:continue
                if self.cancel.is_set():self.talking.clear();self.completed.emit();continue
                self.status.emit('voice_loading');self.talking.set()
                try:
                    text=text.split(tr('Fontes (trechos do buscador):','Sources (search snippets):',cfg['locale']))[0]
                    text=re.sub(r'https?://\S+','',text);text=re.sub(r'[*#`]|\[\d+\]','',text)[:2600]
                    if cfg['tts']=='neural' and cfg.get('online_voice',False):
                        import edge_tts,av
                        async def synthesize():
                            data=bytearray();rate=f"{int((cfg['tts_rate']/175-1)*100):+d}%"
                            async def stream():
                                async for part in edge_tts.Communicate(text,neural_voice(cfg['locale']),rate=rate).stream():
                                    if self.cancel.is_set() or self.stopping.is_set():break
                                    if part['type']=='audio':data.extend(part['data'])
                            await asyncio.wait_for(stream(),timeout=40)
                            return bytes(data)
                        try:
                            data=asyncio.run(synthesize())
                            if data and not self.cancel.is_set():
                                chunks=[]
                                with av.open(io.BytesIO(data)) as container:
                                    resampler=av.AudioResampler(format='fltp',layout='mono',rate=24000)
                                    for frame in container.decode(audio=0):
                                        if self.cancel.is_set():break
                                        for f in resampler.resample(frame):chunks.append(f.to_ndarray().reshape(-1))
                                    for f in resampler.resample(None):chunks.append(f.to_ndarray().reshape(-1))
                                if chunks and not self.cancel.is_set():self.status.emit('speaking');self.play(np.concatenate(chunks),24000,cfg['tts_volume'])
                        except Exception:
                            self.error.emit(tr('Voz online indisponível; tentando a voz feminina do Windows.','Online voice unavailable; trying the Windows female voice.',cfg['locale']));engine=self.windows(text,cfg,engine)
                    else:engine=self.windows(text,cfg,engine)
                except Exception as e:logging.exception('Voice');self.error.emit(tr('Falha na voz: ','Voice error: ',cfg['locale'])+str(e));engine=None
                finally:time.sleep(.25);self.talking.clear();self.completed.emit()
        finally:
            if engine:
                try:engine.stop()
                except Exception:pass
            if os.name=='nt':pythoncom.CoUninitialize()

class Listener(QThread):
    command=Signal(str);status=Signal(str);level=Signal(float);partial=Signal(str);wake=Signal();cancelled=Signal();error=Signal(str);online=Signal(bool)
    def __init__(self,talking,get_cfg):
        super().__init__();self.talking=talking;self.get_cfg=get_cfg;self.enabled=threading.Event();self.enabled.set();self.stopping=threading.Event();self.busy=threading.Event();self.reset=threading.Event();self.session_until=0.;self.force=threading.Event();self.confirm=threading.Event()
    def stop(self):self.stopping.set()
    def resume(self,conversation=False):
        cfg=self.get_cfg();self.session_until=time.monotonic()+cfg['session_seconds'] if conversation and cfg['continuous'] else 0.;self.busy.clear();self.reset.set()
    def end_session(self):self.session_until=0.;self.reset.set()
    def listen_now(self):self.force.set()
    def submit_audio(self):self.confirm.set()
    def run(self):
        try:
            import sounddevice as sd
            from pocketsphinx import Decoder
            import onnxruntime
            onnxruntime.disable_telemetry_events()
            from faster_whisper import WhisperModel
            cfg=dict(self.get_cfg())
            if not (WHISPER_DIR/'model.bin').is_file():raise RuntimeError(tr('Baixe o Whisper nos Ajustes ou execute INSTALAR.bat.','Download Whisper in Settings or run INSTALAR.bat.'))
            self.status.emit('listening_loading')
            model=None
            decoder=Decoder(samprate=16000,loglevel='ERROR',lm=None)
            lex={'jarvis':'JH AA R V IH S','arvis':'AA R V IH S','jervis':'JH EH R V IH S','jarvisbr':'ZH AA R V IH S','jarvish':'ZH AA HH V IH S','arvish':'AA HH V IH S'}
            for word,phonemes in lex.items():
                if not decoder.lookup_word(word):decoder.add_word(word,phonemes,True)
            aliases=[a.strip().lower() for a in cfg['voice_aliases'].split(',') if a.strip().lower() in ('jarvis','arvis','jervis')] or ['jarvis']
            if 'jarvis' in aliases:aliases+=['jarvisbr','jarvish']
            if 'arvis' in aliases:aliases+=['arvish']
            threshold={'baixa':'1e-35','normal':'1e-45','alta':'1e-50'}[cfg['sensitivity']]
            audio=queue.Queue(maxsize=40);pre=deque(maxlen=10);noise=.002
            rate=16000
            try:sd.check_input_settings(device=cfg['mic'],samplerate=rate,channels=1,dtype='int16')
            except Exception:rate=int(sd.query_devices(cfg['mic'],'input')['default_samplerate'])
            def callback(data,frames,timing,status):
                if rate!=16000:
                    raw=np.frombuffer(data,dtype=np.int16);data=np.interp(np.arange(1600)*rate/16000,np.arange(len(raw)),raw).astype(np.int16).tobytes()
                try:audio.put_nowait(bytes(data))
                except queue.Full:pass
            with tempfile.TemporaryDirectory(dir=DATA) as td:
                keywords=Path(td)/'wake.list';keywords.write_text('\n'.join(f'{a} /{threshold}/' for a in aliases),'utf-8');decoder.add_kws('wake',str(keywords));decoder.activate_search('wake');decoder.start_utt()
                active=False;capture=None;deadline=0.;occupied_before=False
                def reset_decoder():decoder.end_utt();decoder.start_utt();pre.clear()
                with sd.RawInputStream(device=cfg['mic'],samplerate=rate,blocksize=int(rate*.1),dtype='int16',channels=1,callback=callback):
                    self.online.emit(True);self.status.emit('waiting')
                    while not self.stopping.is_set():
                        try:data=audio.get(timeout=.2)
                        except queue.Empty:continue
                        samples=np.frombuffer(data,dtype=np.int16).astype(np.float32)/32768
                        rms=float(np.sqrt(np.mean(samples*samples)));self.level.emit(min(1,rms*14))
                        if not self.enabled.is_set():active=False;capture=None;self.reset.set();continue
                        # Suprime a saída de voz para não transcrever a própria resposta.
                        occupied=self.talking.is_set() or self.busy.is_set()
                        if occupied:
                            if not occupied_before:reset_decoder()
                            occupied_before=True;active=False;capture=None;pre.clear()
                            if cfg.get('barge_in'):
                                decoder.process_raw(data,False,False)
                                if decoder.hyp():self.cancelled.emit();reset_decoder()
                            if model is not None and cfg['economy']:
                                model=None
                                import gc
                                gc.collect()
                            continue
                        if occupied_before:occupied_before=False;self.reset.set()
                        if self.reset.is_set():
                            reset_decoder();self.reset.clear();active=False;capture=None
                            if self.session_until>time.monotonic():active=True;deadline=self.session_until;capture=Utterance(cfg['pause_seconds'],cfg['max_utterance']);self.status.emit('session')
                            else:self.status.emit('waiting')
                        if self.force.is_set():self.force.clear();self.confirm.clear();active=True;capture=Utterance(cfg['pause_seconds'],cfg['max_utterance']);deadline=time.monotonic()+15;self.status.emit('listening')
                        if not active:
                            noise=noise*.995+min(rms,.015)*.005;pre.append(samples.copy());decoder.process_raw(data,False,False)
                            if decoder.hyp():
                                active=True;deadline=time.monotonic()+15;capture=Utterance(cfg['pause_seconds'],cfg['max_utterance']);self.wake.emit();self.status.emit('listening')
                                for old in pre:capture.feed(old,max(.004,min(.012,noise*2.5)))
                                pre.clear()
                            continue
                        done=capture.feed(samples,max(.004,min(.012,noise*2.5)))
                        self.partial.emit(tr('Captando sua frase…','Capturing your sentence…',cfg['locale']) if rms>=max(.004,min(.012,noise*2.5)) else tr('Pausa · continuo ouvindo…','Pause · still listening…',cfg['locale']))
                        if self.confirm.is_set():self.confirm.clear();done=True
                        if time.monotonic()>deadline and capture.speech_seconds<.25:active=False;capture=None;self.session_until=0.;self.reset.set();continue
                        if not done:continue
                        if capture.speech_seconds<.25:active=False;capture=None;self.reset.set();continue
                        self.status.emit('transcribing')
                        if model is None:model=WhisperModel(str(WHISPER_DIR),device='cpu',compute_type='int8',cpu_threads=2,num_workers=1)
                        segments,_=model.transcribe(capture.audio(),language=speech_code(cfg['locale']),beam_size=5,condition_on_previous_text=False,vad_filter=True,initial_prompt='Jarvis, Spotify, Visual Studio Code, Lika Manager.')
                        text=clean_transcription(' '.join(s.text.strip() for s in segments))
                        # Descarte áudio acumulado durante a transcrição, sem reutilizar conversa antiga.
                        while True:
                            try:audio.get_nowait()
                            except queue.Empty:break
                        self.partial.emit(text)
                        if self.stopping.is_set():break
                        if self.reset.is_set():active=False;capture=None;self.partial.emit('');continue
                        if normal(text) in ('pare','parar','cancelar','silencio','stop','cancel','be quiet'):self.cancelled.emit();self.reset.set();active=False;continue
                        if text:
                            if cfg['economy']:
                                model=None
                                import gc
                                gc.collect()
                            self.busy.set();self.command.emit(text);active=False;capture=None;self.reset.set()
                        else:
                            active=True;capture=Utterance(cfg['pause_seconds'],cfg['max_utterance']);deadline=time.monotonic()+10;self.status.emit('repeat')
                decoder.end_utt()
        except Exception as e:logging.exception('Escuta');self.error.emit(str(e))
        finally:self.online.emit(False);self.level.emit(0.)
