@echo off
setlocal
cd /d "%~dp0"
echo Jarvis 3.0 - PT-BR / EN-US
echo Feche o Jarvis antigo pelo icone perto do relogio antes de continuar.
if exist ".venv\Scripts\python.exe" goto dependencies
py -3.12 -m venv .venv 2>nul
if not errorlevel 1 goto dependencies
py -3.11 -m venv .venv 2>nul
if not errorlevel 1 goto dependencies
echo Instale Python 3.12 de 64 bits e execute novamente.
pause
exit /b 1
:dependencies
.venv\Scripts\python.exe -c "import struct,sys; assert sys.version_info[:2] in ((3,11),(3,12)) and struct.calcsize('P')*8==64, 'Use Python 3.11 ou 3.12 de 64 bits'"
if errorlevel 1 goto failure
.venv\Scripts\python.exe -m pip install --timeout 180 --retries 10 -r requirements.txt
if errorlevel 1 goto failure
.venv\Scripts\python.exe downloads.py
if errorlevel 1 goto failure
.venv\Scripts\python.exe criar_atalho.py
if errorlevel 1 goto shortcut_error
echo Instalacao concluida. Abra ABRIR.bat ou o atalho Jarvis Zeti.
echo Para testar no VS Code: .\.venv\Scripts\python.exe main.py
pause
exit /b 0
:shortcut_error
echo Instalacao feita. Nao consegui criar o atalho. Use ABRIR.bat.
pause
exit /b 0
:failure
echo A instalacao nao terminou. Copie o erro para verificarmos.
echo Seus dados salvos nao foram apagados.
pause
exit /b 1
