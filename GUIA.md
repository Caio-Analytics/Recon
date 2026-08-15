# Guia de instalação e uso do Recon

Este guia é para quem nunca usou Python nem terminal. Não precisa de
conhecimento prévio e **não precisa de permissão de administrador** — tudo é
instalado dentro da sua própria pasta de usuário.

Tempo estimado: 15 minutos, uma vez só.

---

## O que você vai instalar

| O quê | Para quê | Precisa de admin? |
|---|---|---|
| Python | a linguagem em que o Recon é escrito | **Não** |
| Git | para baixar o Recon e receber atualizações | **Não** |
| Recon | a ferramenta | **Não** |

---

## Passo 1 — Instalar o Python

### Windows

1. Acesse **https://www.python.org/downloads/windows/**
2. Baixe o **Windows installer (64-bit)** da versão **3.12 ou superior**.
3. Execute o instalador e, na primeira tela:
   - ✅ marque **"Add python.exe to PATH"** (importante — sem isso o terminal
     não vai encontrar o Python)
   - clique em **"Customize installation"**
4. Na tela seguinte, deixe as opções como estão e avance.
5. Na tela **"Advanced Options"**:
   - ❌ **desmarque** "Install Python for all users" — é essa opção que pediria
     senha de administrador
   - ✅ marque "Install Python for me only" (ou deixe o caminho que aparece
     dentro de `C:\Users\seu.nome\...`)
6. Clique em **Install**.

> Se sua empresa bloqueia o instalador `.exe`, use a versão **embeddable** ou
> peça pela Microsoft Store (busque "Python 3.12"), que instala só para o seu
> usuário sem pedir senha.

### macOS / Linux

Provavelmente já tem. Abra o terminal e digite:

```bash
python3 --version
```

Se aparecer `Python 3.12` ou maior, está pronto. Se não, baixe em
**https://www.python.org/downloads/**.

### Conferindo

Abra o terminal (veja o Passo 4 se não souber como) e digite:

```bash
python --version
```

Deve aparecer algo como `Python 3.12.x`. Se disser que o comando não existe,
tente `python3 --version`. Se ainda assim não funcionar, o Python não foi
adicionado ao PATH — reinstale marcando aquela opção do passo 3.

---

## Passo 2 — Instalar o Git

O Git é o que baixa o Recon e permite atualizá-lo depois com um comando só.

### Windows

1. Acesse **https://git-scm.com/download/win**
2. Baixe e execute o instalador.
3. Pode aceitar todas as opções padrão (Next em tudo).

O instalador do Git **não pede senha de administrador** na instalação por
usuário.

### macOS

```bash
git --version
```

Se não tiver, o macOS oferece instalar sozinho ao rodar esse comando.

### Linux

```bash
sudo apt install git      # Ubuntu/Debian — este pede senha
```

---

## Passo 3 — Baixar o Recon

Escolha uma pasta sua para guardar a ferramenta. Sugestão:
`Documentos\Programas` no Windows, ou `~/programas` no Mac/Linux.

Abra o terminal e digite, **uma linha por vez**:

```bash
cd Documentos
mkdir Programas
cd Programas
git clone https://github.com/Caio-Analytics/Recon.git
cd Recon
```

> `cd` significa "entrar na pasta". `mkdir` cria uma pasta. `git clone` baixa
> o projeto.

Agora instale, **só para o seu usuário**:

```bash
pip install --user -e .
```

Se aparecer um erro dizendo `externally-managed-environment`, use:

```bash
pip install --user --break-system-packages -e .
```

> Esse erro **não** é falta de permissão de administrador — é só uma trava do
> próprio `pip`. O comando acima contorna sem precisar de senha.

### Se o comando `recon` não for reconhecido

O Python instala os programas numa pasta que o Windows às vezes não conhece.
Duas saídas:

**A) Adicionar ao PATH (permanente).** No Windows, procure "variáveis de
ambiente" no menu Iniciar → "Variáveis de ambiente" → em *Variáveis de
usuário*, selecione `Path` → Editar → Novo → cole o caminho que apareceu no
aviso do `pip` (algo como
`C:\Users\seu.nome\AppData\Roaming\Python\Python312\Scripts`). Feche e reabra
o terminal.

**B) Chamar pelo Python (funciona sempre).** Em vez de `recon`, use:

```bash
python -m recon.cli
```

---

## Passo 4 — Usar

Há dois caminhos. Escolha o que combina com você.

### Caminho A — Com VS Code (recomendado se você já usa)

1. Baixe em **https://code.visualstudio.com/** e instale (a instalação
   *User Installer* não pede senha de administrador).
2. Abra o VS Code → menu **Arquivo → Abrir Pasta** → escolha a pasta onde
   estão as suas planilhas.
3. Abra o terminal integrado: menu **Terminal → Novo Terminal**
   (ou `Ctrl` + `'`).
4. Digite:

```bash
recon
```

5. Responda as perguntas. No fim, os relatórios aparecem na barra lateral
   esquerda — clique com o botão direito no arquivo `.html` →
   **Revelar no Explorador de Arquivos** → clique duas vezes para abrir no
   navegador.

### Caminho B — Direto no terminal (sem instalar mais nada)

**Windows:** aperte a tecla `Windows`, digite `powershell`, dê Enter.

**macOS:** aperte `Cmd` + `Espaço`, digite `terminal`, dê Enter.

**Linux:** `Ctrl` + `Alt` + `T`.

Depois, navegue até a pasta das suas planilhas e rode:

```bash
cd Documentos\MinhasPlanilhas
recon
```

> Dica no Windows: você pode arrastar a pasta para dentro da janela do
> terminal depois de digitar `cd ` — o caminho é preenchido sozinho.

---

## Passo 5 — O menu

Digitando `recon` sozinho, aparece isto:

```
╭───────────────────────────────────────────────────────────────────╮
│ Recon 3.0.0                                                       │
│ Descubra o que tem nos seus arquivos antes de começar a analisar. │
╰───────────────────────────────────────────────────────────────────╯

Onde estão os arquivos? (Enter = pasta atual):
```

Aperte **Enter** para usar a pasta em que você está, ou cole o caminho de
outra pasta.

```
Encontrei 3 arquivo(s):
  #  Arquivo           Tamanho
  1  empregados.csv       2.4 MB
  2  treinamentos.csv     8.1 MB
  3  cursos.csv           0.1 MB

O que você quer fazer?
  1  Comparar os arquivos  — um relatório só, do pior para o melhor (recomendado)
  2  Descobrir como se ligam  — chaves entre as tabelas, fato × dimensão, análises prontas
  3  Analisar um por um  — relatório completo e separado de cada arquivo
Escolha [1]:
```

Aperte **Enter** para aceitar o padrão, ou digite o número da opção.

No fim ele diz onde salvou. **Clique duas vezes no arquivo `.html`** — abre no
seu navegador, formatado, sem precisar de mais nada.

**Se você apertar Enter em todas as perguntas, funciona.** Os padrões foram
escolhidos para o caso comum.

---

## Qual opção escolher?

| Sua situação | Opção |
|---|---|
| Recebi uma planilha e não sei o que tem nela | Aparece direto, sem perguntar |
| Recebi 10 arquivos e quero saber quais prestam | **1 — Comparar** |
| Tenho tabelas que se relacionam (empregados, treinamentos, cursos…) | **2 — Descobrir como se ligam** |
| Quero o máximo de detalhe de cada arquivo | **3 — Um por um** |

---

## Atualizar o Recon

Sempre que quiser a versão mais nova:

```bash
cd Documentos\Programas\Recon
git pull
pip install --user -e .
```

---

## Problemas comuns

**"python não é reconhecido como um comando"**
O Python não foi adicionado ao PATH. Reinstale marcando
*"Add python.exe to PATH"* na primeira tela do instalador.

**"recon não é reconhecido como um comando"**
Veja a seção "Se o comando `recon` não for reconhecido" no Passo 3. A
alternativa `python -m recon.cli` sempre funciona.

**"Acesso negado" ou pedido de senha de administrador**
Você esqueceu o `--user` no comando de instalação. Ele é o que faz tudo ser
instalado só na sua pasta.

**O relatório abriu no bloco de notas em vez do navegador**
Você abriu o arquivo `.json` ou `.md`. O que abre no navegador é o `.html`.

**A análise está demorando muito**
Arquivo grande. Para uma primeira olhada rápida:

```bash
recon perfilar arquivo_gigante.csv --limite-amostra 200000
```

**Meu Excel tem título e linha de total no meio**
Não precisa fazer nada. O Recon detecta e avisa no relatório o que ajustou.

---

## Para ir além

Depois de se acostumar com o menu, os comandos diretos são mais rápidos.
Veja **`COMANDOS.md`** — tem todos eles com exemplos e receitas prontas.
