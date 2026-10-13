# JARVIS

Meu assistente pessoal para Windows, desenvolvido em Python.

A ideia surgiu da vontade de criar um Jarvis para usar no meu próprio computador: conversar por voz, abrir programas, guardar ideias e lembrar das tarefas do dia. A inspiração vem do Homem de Ferro, com uma interface em roxo e preto, do meu jeito.

## O que ele faz

- Conversa por texto e voz.
- Responde usando Gemini ou um modelo local pelo Ollama.
- Reconhece comandos em português e inglês.
- Abre aplicativos, sites e pastas.
- Controla volume, reprodução de música e janelas.
- Organiza tarefas, lembretes, anotações e memórias.
- Pesquisa informações na internet e apresenta as fontes.
- Monitora CPU, memória e bateria.
- Continua funcionando na bandeja do Windows.

## Voz e interação

O reconhecimento de fala acontece localmente com Whisper. A ativação pode ser feita pela palavra “Jarvis” ou pelo botão de fala.

As respostas podem ser lidas por uma voz feminina do Windows ou por uma voz online. O idioma selecionado também acompanha a interface e as novas respostas.

## Tecnologias

**Aplicação:** Python e PySide6  
**Inteligência artificial:** Gemini API e Ollama  
**Reconhecimento de fala:** faster-whisper e PocketSphinx  
**Áudio:** sounddevice, pyttsx3 e edge-tts  
**Dados:** SQLite  
**Integrações:** requests, psutil, dateparser, DDGS e pywin32  

## Organização do projeto

O código está dividido entre interface, interpretação de pedidos, voz, automação e armazenamento.

Os comandos conhecidos são tratados pelo aplicativo. A IA participa da conversa e dos resumos, enquanto tarefas, notas e preferências ficam salvas localmente.

## Desenvolvimento

Uso o Jarvis no dia a dia para identificar o que precisa melhorar. Meu foco é tornar a conversa mais natural, melhorar o reconhecimento de voz e deixar os comandos cada vez mais úteis.

O projeto reúne áreas que gosto de explorar: programação, inteligência artificial, automação e interfaces.

---

**Felipe Iazzette · Zeti**

[GitHub](https://github.com/Iazzette) · [LinkedIn](https://www.linkedin.com/in/felipe-goncalez-0644502b5/)