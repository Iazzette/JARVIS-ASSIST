"""Captura por silêncio tolerante; não usa o fim de frase curto do Vosk."""
from dataclasses import dataclass,field
import numpy as np

@dataclass
class Utterance:
    pause_seconds:float=2.0
    max_seconds:float=35.0
    min_speech:float=.25
    chunks:list=field(default_factory=list)
    speech_seconds:float=0.
    silence_seconds:float=0.
    elapsed:float=0.
    def feed(self,samples,threshold=.008):
        samples=np.asarray(samples,dtype=np.float32);duration=len(samples)/16000
        self.chunks.append(samples.copy());self.elapsed+=duration
        rms=float(np.sqrt(np.mean(samples*samples))) if len(samples) else 0.
        if rms>=threshold:self.speech_seconds+=duration;self.silence_seconds=0.
        else:self.silence_seconds+=duration
        return ((self.speech_seconds>=self.min_speech and self.silence_seconds>=self.pause_seconds) or self.elapsed>=self.max_seconds)
    def audio(self):return np.concatenate(self.chunks) if self.chunks else np.zeros(0,dtype=np.float32)

def clean_transcription(text):
    import re
    text=re.sub(r'^\s*(?:jarvis|jervis|arvis|j[aá]rvis|javis|garvis)\b[\s,:.!-]*','',text,flags=re.I)
    return text.strip()
