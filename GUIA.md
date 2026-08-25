# Guia de instalação e uso do Recon

Este guia é para quem nunca usou Python nem terminal. Não precisa de
conhecimento prévio e **não precisa de permissão de administrador** — tudo é
instalado dentro da sua própria pasta de usuário.

Tempo estimado: 15 minutos, uma vez só.

---

## ⚠️ A regra de ouro: tudo dentro da sua pasta de usuário

Esta é a parte que resolve 90% dos problemas em máquina corporativa, então
leia antes de baixar qualquer coisa.

Quando você baixa um instalador, ele cai em **Downloads**. Se você executar
dali, na maioria das máquinas corporativas o Windows **pede senha de
administrador** — e você trava.

**A solução é mover o instalador para dentro da sua pasta de usuário antes de
executar.** Ou seja:

1. Abra o **Explorador de Arquivos**
2. Vá em **Este Computador → Disco Local (C:) → Usuários → `seu.nome`**
3. Crie ali uma pasta chamada **`Instaladores`**
4. **Recorte** o arquivo que está em Downloads e **cole** nessa pasta
5. Execute o instalador **de dentro dela**

```
C:\
└── Usuários\
    └── seu.nome\          ← tudo que for seu vive aqui dentro
        ├── Instaladores\   ← execute os instaladores daqui
        └── Programas\      ← e instale os programas aqui
```

**Por que isso funciona:** o Windows só pede administrador quando um programa
tenta escrever fora da sua pasta de usuário — em `C:\Program Files` ou no
registro da máquina inteira. Ficando tudo dentro de `C:\Usuários\seu.nome`,
nada é compartilhado com outros usuários da máquina e nada precisa de
permissão elevada. Muitas empresas também bloqueiam por política a execução
direta da pasta Downloads, o que produz o mesmo pedido de senha — mover
resolve os dois casos de uma vez.

**Sempre que uma tela de instalação oferecer escolha, prefira:**

- ✅ "Install for me only" / "Somente para mim" / "Apenas para este usuário"
- ❌ "Install for all users" / "Para todos os usuários deste computador"

A segunda opção é *sempre* a que dispara o pedido de senha.

---

## O que você vai instalar

| O quê | Para quê | Precisa de admin? |
|---|---|---|
| Python | a linguagem em que o Recon é escrito | **Não** — validado |
| Git | para baixar o Recon e receber atualizações | **Não** — validado |
| Recon | a ferramenta | **Não** |
| VS Code *(opcional)* | editor, deixa o uso mais confortável | **Não**, com o instalador certo |

---

## Passo 1 — Instalar o Python

1. Acesse **https://www.python.org/downloads/windows/**
2. Baixe o **Windows installer (64-bit)** da versão **3.12 ou superior**.
3. **Mova o arquivo baixado** de Downloads para `C:\Usuários\seu.nome\Instaladores`
   (veja a regra de ouro acima). Execute a partir de lá.
4. Na primeira tela do instalador:
   - ✅ marque **"Add python.exe to PATH"** — sem isso o terminal não encontra
     o Python depois
   - clique em **"Customize installation"** (não em "Install Now")
5. Na tela seguinte deixe tudo como está e avance.
6. Na tela **"Advanced Options"**:
   - ❌ **desmarque** "Install Python for all users" — é exatamente essa opção
     que pediria a senha
   - ✅ confirme que o caminho de instalação começa com
     `C:\Users\seu.nome\AppData\...`
7. Clique em **Install**. Não deve aparecer nenhum pedido de senha.

> **Se mesmo assim pedir senha:** você deixou marcado "for all users", ou está
> executando de Downloads. Cancele, verifique os dois pontos e tente de novo.

> **Se a empresa bloquear o `.exe` por completo:** busque "Python 3.12" na
> **Microsoft Store**. A instalação por lá é sempre por usuário e não pede
> senha.

### macOS / Linux

Abra o terminal e digite:

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

Deve aparecer `Python 3.12.x` ou maior. Se disser que o comando não existe,
tente `python3 --version`. Se nenhum dos dois funcionar, o Python não foi
adicionado ao PATH — reinstale marcando aquela opção do item 4.

---

## Passo 2 — Instalar o Git

O Git é o que baixa o Recon e permite atualizá-lo depois com um comando só.

### Windows

1. Acesse **https://git-scm.com/download/win**
2. Baixe o instalador **64-bit Git for Windows Setup**.
3. **Mova de Downloads para `C:\Usuários\seu.nome\Instaladores`** e execute
   de lá.
4. Pode aceitar todas as opções padrão (Next em tudo). O instalador do Git
   por usuário não pede senha de administrador.

> Se aparecer uma tela perguntando entre "Git for Windows Setup" e "Portable",
> qualquer uma serve. A portátil nem instala — descompacta e roda.

### macOS

```bash
git --version
```

O macOS oferece instalar sozinho ao rodar esse comando.

### Linux

```bash
sudo apt install git      # este pede senha, mas é a sua máquina pessoal
```

---

## Passo 3 — Baixar o Recon

Pela regra de ouro, o Recon também vai para dentro da sua pasta de usuário —
naquela pasta `Programas` que você criou em `C:\Usuários\seu.nome`.

Abra o terminal e digite, **uma linha por vez**:

```bash
cd %USERPROFILE%
mkdir Programas
cd Programas
git clone https://github.com/Caio-Analytics/Recon.git
cd Recon
```

> `%USERPROFILE%` é um atalho do Windows para `C:\Usuários\seu.nome` — ele te
> leva direto ao lugar certo, sem digitar o caminho inteiro.
> `cd` entra numa pasta, `mkdir` cria uma, `git clone` baixa o projeto.

No **macOS ou Linux**, troque a primeira linha por `cd ~`.

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

**B) Chamar pelo Python (funciona sempre, em qualquer instalação).** Em vez de `recon`, use:

```bash
python -m recon
```

Guarde essa alternativa — ela reaparece nos próximos passos toda vez que o guia pede pra digitar `recon`.

---

## Passo 4 — Usar

Há três caminhos. Escolha o que combina com você — o **A** é o mais simples e
não exige digitar comando nenhum depois de instalado.

### Caminho A — A janela (não precisa de terminal) ⭐

**No Windows**, abra a pasta onde você baixou o Recon
(`C:\Usuários\seu.nome\Programas\Recon`) e dê **dois cliques** no arquivo:

```
Recon.pyw
```

Uma janela abre. Não aparece nenhuma tela preta de terminal — é um programa
como qualquer outro.

<img src="docs/imagens/janela.png" alt="A janela do Recon" width="620">

**No Linux**, dois cliques não funcionam: o gerenciador de arquivos do Ubuntu
não executa esse tipo de arquivo, ele abre no editor de texto. Rode **uma
única vez**, dentro da pasta do Recon:

```bash
./instalar-atalho.sh
```

Daí em diante o Recon está no menu de aplicativos: aperte a tecla **Super**
(a do losango do Windows) e digite "Recon". Botão direito no ícone →
*Adicionar aos favoritos* fixa ele na barra lateral. Para tirar,
`./instalar-atalho.sh --remover`.

**No macOS**, rode o mesmo `./instalar-atalho.sh`. Ele cria um arquivo
`Recon.command` na pasta do projeto, que abre com dois cliques no Finder.

> **Dica:** clique com o botão direito no `Recon.pyw` → **Enviar para** →
> **Área de trabalho (criar atalho)**. Daí em diante é só clicar no atalho.
>
> Se os dois cliques abrirem o Bloco de Notas com o texto do arquivo em vez de
> abrir a janela, o Windows associou `.pyw` ao programa errado: botão direito →
> **Abrir com** → **Escolher outro aplicativo** → procure `pythonw.exe` (fica em
> `C:\Users\seu.nome\AppData\Local\Programs\Python\Python312\`) e marque
> "Sempre usar este aplicativo".

Na janela:

1. **Escolha o modo na lista da esquerda** — *Um arquivo*, *Comparar vários*
   ou *Como se ligam*. Cada um traz uma linha dizendo para que serve. O item
   **Ajuda**, no fim da lista, responde as dúvidas mais comuns sem precisar
   deste guia.
2. **Clique em "Procurar…"** e escolha o arquivo pelo Explorer normal, do jeito
   que você abre qualquer planilha. Dá para escolher a pasta inteira também.
3. Se quiser, escolha **onde salvar** os relatórios. Deixando em branco, eles
   são salvos na **mesma pasta do arquivo** que você selecionou.
4. Se quiser, escolha o **formato**. O HTML já vem marcado e é o que a maioria
   das pessoas quer: abre no navegador com dois cliques. JSON e Markdown são
   extras — pode marcar os três, cada um vira um arquivo.
5. **Clique em "Analisar agora"** e espere.

> **A janela vai parecer travada. Isso é normal.** Enquanto analisa, o botão
> fica cinza e a barra fica correndo; em arquivo grande isso leva alguns
> minutos, e o Windows às vezes escreve "Não Responde" na barra de título mesmo
> com tudo funcionando. Espere, não feche e não clique várias vezes no botão.

No fim, clique em **"Abrir a pasta dos relatórios"** e dê dois cliques no
arquivo `.html`.

Se você já tem o `recon` funcionando no terminal, a mesma janela abre com:

```bash
recon janela
```

### Caminho B — Com VS Code (recomendado se você já usa)

1. Baixe em **https://code.visualstudio.com/**. Na página de download do
   Windows, escolha a opção **"User Installer"** — não a "System Installer".

   | Versão | Instala em | Pede admin? |
   |---|---|---|
   | **User Installer** ✅ | `C:\Users\seu.nome\AppData\Local\Programs` | **Não** |
   | System Installer ❌ | `C:\Program Files` | **Sim** |
   | **.zip (Portable)** ✅ | onde você descompactar | **Não**, nem instala |

   Se o instalador estiver bloqueado pela empresa, baixe o **.zip**,
   descompacte dentro de `C:\Usuários\seu.nome\Programas` e execute o
   `Code.exe` de lá. Funciona igual e não passa por instalação nenhuma.

   Mova o arquivo baixado para a sua pasta antes de executar, como nos
   passos anteriores.
2. Abra o VS Code → menu **Arquivo → Abrir Pasta** → escolha a pasta onde
   estão as suas planilhas.
3. Abra o terminal integrado: menu **Terminal → Novo Terminal**
   (ou `Ctrl` + `'`).
4. Digite:

```bash
recon
```

   Se aparecer "comando não encontrado" ou "not recognized", use
   `python -m recon` no lugar — funciona sempre, mesmo sem o PATH configurado
   (veja o Passo 3).

5. Responda as perguntas. No fim, os relatórios aparecem na barra lateral
   esquerda — clique com o botão direito no arquivo `.html` →
   **Revelar no Explorador de Arquivos** → clique duas vezes para abrir no
   navegador.

### Caminho C — Direto no terminal (sem instalar mais nada)

**Windows:** aperte a tecla `Windows`, digite `powershell`, dê Enter.

**macOS:** aperte `Cmd` + `Espaço`, digite `terminal`, dê Enter.

**Linux:** `Ctrl` + `Alt` + `T`.

Depois, navegue até a pasta das suas planilhas e rode:

```bash
cd Documentos\MinhasPlanilhas
recon
```

> Se `recon` não for reconhecido, troque por `python -m recon` — funciona
> sempre, independente de PATH.

> Dica no Windows: você pode arrastar a pasta para dentro da janela do
> terminal depois de digitar `cd ` — o caminho é preenchido sozinho.

---

## Passo 5 — O menu do terminal

> Se você escolheu o **Caminho A** (a janela), pode pular este passo: as
> perguntas são as mesmas, só que em botões. Ele interessa a quem usa os
> caminhos B e C.

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
alternativa `python -m recon` sempre funciona, em qualquer instalação.

**A janela "Não Responde" enquanto analisa**
É o comportamento normal do Windows enquanto um programa trabalha. A barra
correndo mostra que está tudo certo. Espere: arquivo grande leva minutos. Só
desconfie se passar de dez minutos com um arquivo pequeno.

**Dois cliques no `Recon.pyw` abrem o Bloco de Notas**
O Windows associou a extensão ao programa errado. Botão direito no arquivo →
**Abrir com** → **Escolher outro aplicativo** → procure o `pythonw.exe` e
marque "Sempre usar este aplicativo". Enquanto isso, `recon janela` no
terminal abre a mesma janela.

**A janela abriu e sumiu na hora / apareceu erro dizendo que não está instalado**
Faltou o `pip install --user -e .` do Passo 3, ou ele foi feito com outro
Python. Refaça o Passo 3 e tente de novo.

**Pediu senha de administrador**
Três causas possíveis, em ordem de frequência:

1. Você executou o instalador direto da pasta **Downloads**. Mova para
   `C:\Usuários\seu.nome\Instaladores` e execute de lá.
2. Deixou marcado **"Install for all users"** em alguma tela. Cancele e
   refaça desmarcando.
3. Esqueceu o `--user` no `pip install`. É ele que faz tudo ser instalado só
   na sua pasta.

Se mesmo assim persistir, é um programa que realmente exige administrador —
aí não tem jeito por fora, precisa de chamado. Mas **Python, Git e VS Code
não são o caso**: os três instalam por usuário.

**A empresa bloqueou o instalador `.exe`**
- Python: instale pela **Microsoft Store** (busque "Python 3.12")
- Git: baixe a versão **Portable**, que só descompacta
- VS Code: baixe o **.zip**, descompacte na sua pasta e rode o `Code.exe`

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
