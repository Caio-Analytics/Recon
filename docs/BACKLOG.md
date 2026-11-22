# Backlog do Recon

Revisado em 2026-11-22 contra o código da `main`. Cada item tem **tamanho**
(P, M, G) e **nível** para quem quer contribuir: 🟢 bom para começar,
🟡 exige conhecer um módulo, 🔴 exige decisão de design (abra uma issue antes).

Para propor algo novo, abra uma [issue](https://github.com/Caio-Analytics/Recon/issues/new/choose)
ou uma [discussão](https://github.com/Caio-Analytics/Recon/discussions).

## Segurança e confiabilidade

### Auditoria automática de dependências 🟢 P

**Problema.** Todas as versões são fixadas exatamente, o que dá reprodutibilidade,
mas também significa que nada avisa quando uma versão fixada recebe um CVE. Na
revisão de 2026-11-22, `pip-audit` encontrou 46 vulnerabilidades em três
pacotes (`pillow`, `brotli` e `weasyprint`) que só foram corrigidas à mão.

**Proposta.** Rodar `pip-audit` na CI e habilitar o Dependabot para
`pyproject.toml` e GitHub Actions.

**Critério de aceite.** A CI falha quando o `requirements-dev.lock` contém
versão com vulnerabilidade conhecida e corrigível.

### Restringir o carregamento de recursos no PDF 🟡 P

**Problema.** `reporting/_pdf.py` chama `HTML(filename=...).write_pdf(...)` com o
`url_fetcher` padrão do WeasyPrint, que busca qualquer URL ou arquivo
referenciado. Hoje os valores dos dados são escapados no HTML, então não há
injeção conhecida, mas os avisos de segurança do WeasyPrint (CVE-2026-55073
e CVE-2026-106443) mostram que essa camada é frágil.

**Proposta.** Passar um `url_fetcher` que só aceita `data:` e o próprio arquivo
do relatório, com teste que garante que `file://` e `http://` são recusados.

### Escapar caminhos e nomes de aba no código gerado 🟡 P

**Problema.** `reporting/_modelo.py` (e `codegen.py`) interpolam o caminho do
arquivo e o nome da aba direto em literais Python e SQL, como em
`pd.read_excel(r"{arquivo}", sheet_name="{aba}")`. Um nome de aba com aspas gera
um script quebrado ou, em tese, código inesperado.

**Proposta.** Usar `repr()` ou os helpers `_literal_python` e `_identificador_sql`
que já existem em `datamodel.py`, e cobrir com testes nomes de aba com aspas,
barras invertidas e quebras de linha.

### Cobertura de testes nos módulos fracos 🟢 M

**Situação.** O total é 79% (mínimo da CI: 75%), mas há módulos abaixo disso:
`reporting/_conferencia.py` (54%), `codegen.py` (58%), `cli.py` (63%) e
`__main__.py` (0%). O `codegen.py` gera scripts de limpeza e pseudonimização,
então é onde um erro silencioso custa mais.

**Critério de aceite.** Cada módulo acima chega a 80% ou mais, com testes de
comportamento (não só execução) e o piso da CI sobe para 80%.

## Produto

### Relações entre tabelas sem chave explícita 🔴 G

**Situação.** `datamodel.detectar_relacionamentos` só considera como destino
colunas já classificadas como chave primária, e compara conjuntos de valores
(contenção) com apoio da similaridade de nomes. Quando nenhuma das tabelas tem
chave identificável, nada é sugerido.

**Proposta.** Etapa opcional de hipóteses de relacionamento que combine nomes
semanticamente parecidos, sobreposição de valores, formatos e cardinalidade. O
resultado deve ser uma sugestão para revisão da pessoa analista, não uma
relação assumida pelo sistema.

**Guardas necessárias.** Não criar `join` automático nem afirmar que duas
colunas se relacionam sem evidência explicável. Definir limiares, mostrar a
confiança e oferecer validações que reduzam falsos positivos.

**Critério de aceite.** Cada hipótese informa as evidências usadas, a
confiança, exemplos não sensíveis e uma forma de rejeitá-la. Bases sem
evidência suficiente não recebem sugestão.

**Prioridade.** Média. A capacidade deve continuar opcional até ser avaliada
contra conjuntos de dados com relações conhecidas.

### Gazetteer de municípios completo 🟢 P

**Problema.** O vocabulário de municípios cobre só as 27 capitais
(veja [limitações](TECNICO.md#10-limitações-conhecidas)). Colunas com cidades
do interior ficam sem classificação semântica geográfica.

**Proposta.** Incluir os municípios do IBGE em `semantics/vocabulary.py`, com
normalização de acentos e a UF como contexto para desambiguar nomes repetidos.

### Suporte a mais formatos de entrada 🟢 M

**Situação.** O Recon lê CSV, TSV, Excel (`xlsx`, `xls`, `xlsb`), JSON, JSONL e
Parquet. Não lê ODS (LibreOffice) nem Feather.

**Proposta.** Adicionar o formato em `ingestion.py` com teste, documentação e
extensão registrada na lista de formatos aceitos.

### Paralelização em Windows e macOS 🔴 M

**Problema.** A descrição por coluna só usa processos onde existe `fork` ou
`forkserver` (`pipeline.py`). Em Windows e macOS a análise é sempre sequencial.

**Proposta.** Avaliar `spawn` com um executor que não recopie o `DataFrame`
inteiro para cada processo, e medir o ganho antes de adotar.

### Reaproveitar resultados entre fases 🔴 G

**Problema.** Chamar as fases isoladas e depois o pipeline recomputa tudo, o
que impede uso incremental da API.

**Proposta.** Cachear estatísticas por coluna dentro de `DataProfiler`.

### Calibrar os pesos de confiança da inferência semântica 🔴 G

**Problema.** Os números da cascata semântica vêm de julgamento, não de ajuste
sobre corpus rotulado, e o limiar fuzzy de 0,85 é frouxo.

**Proposta.** Montar um conjunto rotulado **sintético** de colunas e medir
precisão e revocação por categoria antes de mexer nos limiares.

## Plataforma e manutenção

### Aposentar a interface Tk legada 🟡 M

**Situação.** `gui.py` (1.149 linhas) é a interface antiga, mantida só por
compatibilidade, e `Recon.pyw` ainda a usa para exibir erros. A interface atual
é a Qt (`gui_qt.py`). A manutenção em dobro aumenta a superfície de testes
(`tests/test_gui.py` exige `tkinter`, que não vem em todas as distribuições).

**Proposta.** Remover `gui.py` e `test_gui.py`, trocar o `tkinter` do
`Recon.pyw` por uma mensagem de erro em PySide6 e registrar no CHANGELOG.

### Atalho de instalação para Windows 🟡 P

**Situação.** `instalar-atalho.sh` cobre Linux e macOS. Quem usa Windows precisa
chamar `Recon.pyw` manualmente.

**Proposta.** Um script `instalar-atalho.ps1` que cria o atalho no menu Iniciar.

### Publicar no PyPI 🔴 M

**Proposta.** Fluxo de release com GitHub Actions e *trusted publishing*, para
`pip install recon` funcionar sem clonar o repositório. Antes, verificar se o
nome está livre e decidir a política de versões.

## Fora de escopo

Decisões registradas em [TECNICO.md](TECNICO.md#11-fora-de-escopo-decisão-explícita):
monitoramento contínuo de drift, geração de asserções para dbt ou Great
Expectations e integrações externas de modelagem.
