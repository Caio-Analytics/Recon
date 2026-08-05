import glob
from profiling_orchestrator import orquestrar

def rodar_em_lote():
    # Pega todos os arquivos CSV e Excel da pasta
    arquivos = glob.glob("*.csv") + glob.glob("*.xlsx") + glob.glob("*.xls")
    
    print(f"\n🚀 Iniciando processamento em lote para {len(arquivos)} arquivos...\n")
    
    for arquivo in arquivos:
        print(f"\n{'='*55}\n⏳ INICIANDO ARQUIVO: {arquivo}")
        try:
            orquestrar(arquivo) # Chama o nosso motor
        except Exception as e:
            print(f"❌ Erro ao processar {arquivo}: {e}")

if __name__ == "__main__":
    rodar_em_lote()