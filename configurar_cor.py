import os

# Define o conteúdo do arquivo de configuração
config_content = """
[theme]
primaryColor = "#2E86C1"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F8F9FA"
textColor = "#333333"
font = "sans serif"
"""

# 1. Cria a pasta .streamlit se não existir
folder_path = ".streamlit"
if not os.path.exists(folder_path):
    os.makedirs(folder_path)
    print(f"Pasta '{folder_path}' criada.")

# 2. Cria ou atualiza o arquivo config.toml
file_path = os.path.join(folder_path, "config.toml")
with open(file_path, "w") as f:
    f.write(config_content)

print(f"✅ Sucesso! Arquivo '{file_path}' configurado para AZUL.")
print("⚠️ AGORA VOCÊ PRECISA REINICIAR SEU APP (Pare o terminal com Ctrl+C e rode 'streamlit run...' novamente).")