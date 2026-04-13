#!/usr/bin/env python3
"""
Script de limpeza - Reseta dados de execução do workflow CEF Monitor
Remove histórico de consultas e redefine arquivos de estado
"""

import json
import os
from datetime import datetime

def limpar_dados():
    """Limpa todos os dados de execução do workflow"""
    
    print("🧹 Iniciando limpeza de dados...")
    print(f"⏰ {datetime.now().strftime('%d/%m/%Y %H:%M:%S BRT')}")
    
    # 1. Limpar imoveis.json
    docs_path = "docs/imoveis.json"
    if os.path.exists(docs_path):
        with open(docs_path, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=2)
        print(f"✅ {docs_path} - LIMPADO")
    else:
        print(f"⚠️  {docs_path} - NÃO ENCONTRADO")
    
    # 2. Limpar ultima_execucao.txt
    exec_path = "docs/ultima_execucao.txt"
    if os.path.exists(exec_path):
        with open(exec_path, 'w', encoding='utf-8') as f:
            f.write("")
        print(f"✅ {exec_path} - LIMPADO")
    else:
        print(f"⚠️  {exec_path} - NÃO ENCONTRADO")
    
    print("\n✨ Limpeza concluída!")
    print("📝 O workflow será executado como se fosse a primeira vez")

if __name__ == "__main__":
    limpar_dados()