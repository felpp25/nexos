# NEXOS — Guia de instalação e uso

Este guia é para quem vai **usar** o NEXOS. Leva menos de 10 minutos, contando o
download do modelo de IA.

O NEXOS roda **100% no seu computador**: seus documentos e conversas nunca saem
da máquina e nenhuma conta é necessária.

---

## Passo 1 — Instale o Ollama

O Ollama é o motor que executa a inteligência artificial localmente. É gratuito e
de código aberto.

> ### ⬇️ Baixe pelo site oficial:
> # **https://ollama.com/download**

Use **somente esse endereço**. Baixe a versão para Windows, execute o instalador
e siga o padrão (Avançar → Instalar). Ao terminar, o Ollama inicia sozinho e fica
como um ícone de lhama na bandeja do Windows, ao lado do relógio.

> Para conferir se funcionou: abra o PowerShell e digite `ollama --version`.

---

## Passo 2 — Baixe o NEXOS

Baixe o arquivo **`NEXOS.exe`** na página de versões do projeto:

> ### **https://github.com/felpp25/nexos/releases/latest**

Não precisa instalar nada: é um único arquivo. Coloque-o onde preferir (Área de
Trabalho, Documentos…) e dê **dois cliques** para abrir.

### Se aparecer "O Windows protegeu o seu PC"

É o aviso padrão para programas sem certificado digital pago. Clique em
**Mais informações → Executar assim mesmo**. O NEXOS não instala nada no sistema
e não acessa a internet, exceto para baixar o modelo do Ollama no passo 3.

> A primeira abertura demora de 5 a 15 segundos (o programa se descompacta).
> Uma tela azul com o logo aparece enquanto isso.

---

## Passo 3 — Baixe o modelo de IA (uma única vez)

Na primeira execução o NEXOS mostra esta tela:

![Tela de primeira execução](img/00-primeira-execucao.png)

Clique em **Baixar modelo agora**. São cerca de **1,9 GB**, baixados direto dos
servidores oficiais do Ollama, com barra de progresso dentro do próprio app.

Prefere pelo terminal? Rode:

```powershell
ollama pull qwen2.5:3b
```

E depois clique em **Já instalei, verificar**. Quando os dois passos ficarem
verdes, clique em **Começar a usar**.

> Modelo usado: **qwen2.5:3b** — página oficial: https://ollama.com/library/qwen2.5

---

## Usando o NEXOS

### 1. Criar agente

![Criar agente](img/02-criar-agente.png)

Um agente é um assistente especializado em um assunto. Preencha:

| Campo | O que colocar |
|---|---|
| **Nome** | Como você vai chamá-lo. Ex.: *Secretaria Acadêmica* |
| **Propósito** | O que ele faz e para quem responde. Ex.: *responder dúvidas de alunos sobre normas e prazos* |
| **Observações** | Regras de tom e formato. Ex.: *tom formal, nunca inventar prazos* |

Depois arraste os documentos da base de conhecimento (ou clique para escolher):

- **PDF** — a citação indica a página
- **PowerPoint (.pptx)** — indica o slide, e lê as notas do apresentador
- **Word (.docx)**, **TXT**, **Markdown**, **CSV**
- **Imagens** (PNG, JPG…) — exigem o Tesseract OCR instalado

Clique em **Criar agente**. O processamento dos arquivos leva alguns segundos.

> Em *Ajustes avançados* dá para trocar o modelo, a temperatura (0 = mais
> conservador, 1 = mais criativo) e quantos trechos da base entram em cada resposta.

### 2. Conversar

![Chat](img/01-chat.png)

Escolha o agente no topo e pergunte. A resposta aparece sendo escrita, e:

- os números azuis **1** **2** dentro do texto apontam de onde veio a informação;
- as **etiquetas cinzas embaixo** são os trechos usados — clique em uma para ler o
  trecho e abrir o arquivo original;
- a etiqueta verde ao lado do nome mostra quantos documentos aquele agente tem.

Se a resposta não estiver na base, o agente **avisa** antes de completar com
conhecimento geral. Cada conversa fica salva na coluna da direita.

> **Enter** envia · **Shift+Enter** quebra a linha.

### 3. Gerir agentes

![Gerir agentes](img/03-gerir-agentes.png)

Cada card mostra documentos e trechos indexados. Você pode:

- **Editar** — mudar nome, propósito, observações e **adicionar ou remover
  documentos** da base;
- **Arquivar** — tira o agente do chat sem apagar nada (volta em *Arquivados*);
- **Excluir** (ícone vermelho) — apaga o agente, seus documentos e conversas. Não
  tem volta.

### 4. Prompt mestre

![Prompt mestre](img/04-prompt-mestre.png)

É a regra geral que vale para **todos** os agentes: idioma, tom, obrigação de
citar a fonte e o que fazer quando a base não cobre o assunto.

As variáveis `{{agent_name}}`, `{{agent_purpose}}` e `{{agent_observations}}` são
trocadas automaticamente pelos dados de cada agente. Clique em
**Pré-visualizar** para ver exatamente o texto que será enviado à IA.

Regra prática:

- vale para todos → **prompt mestre**;
- vale só para um assunto → **observações do agente**.

---

## Perguntas frequentes

**Preciso de internet?**
Só nos passos 1 e 3 (baixar o Ollama e o modelo). Depois disso o NEXOS funciona
offline.

**Meus documentos vão para a nuvem?**
Não. Ficam em `C:\Users\<seu usuário>\AppData\Local\NEXOS`, junto com o banco de
dados das conversas.

**A IA aprende com o que eu converso?**
Não. O modelo não muda. O que melhora o agente é você **adicionar documentos** ou
**editar as observações / o prompt mestre**.

**A barra lateral mostra "Embeddings: básico". É problema?**
Não impede o uso — é a busca simples. Para busca semântica melhor, rode
`ollama pull nomic-embed-text`, clique em **Atualizar status** e reenvie os
documentos.

**O antivírus reclamou do arquivo.**
Programas empacotados dessa forma (PyInstaller) às vezes geram alerta falso. O
código-fonte completo está em https://github.com/felpp25/nexos.

**Como faço backup?**
Copie a pasta `C:\Users\<seu usuário>\AppData\Local\NEXOS`. Ela contém tudo.

**Como desinstalo?**
Apague o `NEXOS.exe` e, se quiser remover os dados, a pasta acima. O Ollama se
desinstala pelo Painel de Controle.
