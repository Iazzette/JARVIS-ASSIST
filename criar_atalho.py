from pathlib import Path
from desktop import create_shortcut
print('Atalho criado:',create_shortcut(Path(__file__).resolve().parent))
