# Painel-Proxy
Este é um painel de proxy funcional que é usado facilmente para qualquer uso!!

# 1. install dep
pip install requests

# 2. make wrapper executable
chmod +x proxy_panel.sh

# 3. install pp alias
source proxy_panel.sh --install
source ~/.bashrc   # ou ~/.profile no termux

# 4. abrir o painel
python3 panel.py

# -- ou via alias depois do install:
pp               # abre TUI
pp --country BR  # switch direto
pp --on          # ativa
pp --off         # desativa
pp --status      # checa estado

# windows (PowerShell / Git Bash):
python panel.py
python panel.py --country DE