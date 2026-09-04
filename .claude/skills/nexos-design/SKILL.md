---
name: nexos-design
description: Sistema de design dark do NEXOS, derivado de designmd.me. Use SEMPRE que for criar ou alterar qualquer tela, componente, CSS ou HTML deste projeto - inclui tokens de cor, tipografia (Inter + Newsreader), espacamento, componentes (cards, botoes, inputs, badges, tabs, modais, toasts) e regras de movimento.
---

# NEXOS Design System

Visual de landing page dark moderna: fundo quase preto neutro, superficies em
camadas, uma unica cor de acento (azul), tipografia serif para display e
sans para interface. Nada de neon, nada de multiplas cores de marca.

## 1. Tokens (fonte da verdade)

Todos os tokens vivem em `:root` no arquivo [web/static/css/nexos.css](../../../web/static/css/nexos.css).
Nunca escreva um hex solto no CSS de um componente - use a variavel.

```css
--bg:            #0f1012;  /* fundo da aplicacao */
--bg-elevated:   #131417;  /* barras, sidebars */
--card:          #17181b;  /* cards, popovers, bolhas */
--muted:         #1d1f23;  /* inputs, chips, hover */
--border:        #2a2c31;  /* todas as bordas */
--border-strong: #3a3d44;  /* borda em hover/foco */
--fg:            #f5f6f8;  /* texto principal */
--fg-muted:      #9aa0ab;  /* texto secundario */
--fg-subtle:     #6b7280;  /* legendas, timestamps */
--primary:       #3b82f6;  /* acento unico */
--primary-hover: #2563eb;
--primary-soft:  rgba(59,130,246,.12);
--success:       #00c758;
--warning:       #f99c00;
--danger:        #f4444d;
--radius:        .625rem; /* 10px - padrao */
--radius-lg:     1rem;
--radius-full:   999px;
```

Escala de texto (Tailwind-like): `.75 / .875 / 1 / 1.125 / 1.25 / 1.5 / 1.875 / 2.25 / 3rem`.
Tracking: titulos usam `-0.025em`; labels em caixa alta usam `0.05em`.

## 2. Tipografia

- **Display (h1, h2, numeros de destaque, nome do produto): `Newsreader`, serif.**
  E a assinatura do visual. Peso 400-500, `letter-spacing: -.02em`.
- **Interface (todo o resto): `Inter`, sans-serif.** Peso 400/500/600.
- Nunca use serif em botao, label, input ou tabela.
- Fallback obrigatorio: `"Newsreader", Georgia, serif` e
  `"Inter", -apple-system, "Segoe UI", sans-serif` (o app roda offline).

## 3. Camadas e profundidade

A profundidade vem de **cor + borda de 1px**, quase nunca de sombra pesada.

1. Fundo `--bg`
2. Card `--card` + `1px solid var(--border)` + `--radius`
3. Elemento interno `--muted`

Sombra permitida: `0 1px 2px rgba(0,0,0,.4)` em cards flutuantes e
`0 24px 60px rgba(0,0,0,.55)` em modais. Barras fixas usam
`backdrop-filter: blur(12px)` sobre `rgba(15,16,18,.72)`.

## 4. Componentes

- **Botao primario**: fundo `--primary`, texto `#fff`, `--radius`, altura 38px,
  peso 500. Hover: `--primary-hover` + `translateY(-1px)`. Foco: anel
  `0 0 0 3px var(--primary-soft)`.
- **Botao secundario**: fundo `--muted`, borda `--border`, texto `--fg`.
- **Botao fantasma**: transparente, texto `--fg-muted`, hover fundo `--muted`.
- **Botao destrutivo**: texto/borda `--danger`, fundo `rgba(244,68,77,.1)`.
- **Input / textarea**: fundo `--muted`, borda `--border`, foco muda para
  `--primary` + anel suave. Placeholder em `--fg-subtle`.
- **Card**: `--card` + borda + `--radius-lg` + padding 20-24px. Titulo em
  Newsreader, subtitulo em `--fg-muted` 0.875rem.
- **Badge/pill**: `--radius-full`, 0.75rem, borda 1px, fundo translucido da cor
  semantica (ex.: `rgba(0,199,88,.12)` + texto `--success`).
- **Tabs**: linha inferior de 1px em `--border`; aba ativa ganha texto `--fg` e
  uma barra de 2px em `--primary`; inativa em `--fg-muted`.
- **Toast**: canto inferior direito, card com borda esquerda 3px na cor
  semantica, some em 4s.
- **Estado vazio**: icone circular 48px em `--muted`, titulo serif, uma linha de
  apoio em `--fg-muted` e um botao primario de acao.
- **Indicador de trabalho**: atomo de 19px com tres orbitas girando + rotulo curto
  (`consultando a base` -> `pensando` -> `escrevendo`), em `#7fb0ff`, ao lado do nome
  do agente. A rotacao usa `<animateTransform>` dentro do SVG com centro explicito
  (`from="A 0 0"`), nunca `transform-origin` do CSS - em SVG isso resolve diferente
  entre navegadores e desloca o eixo de giro. Ver `atomSvg()` em `web/static/js/app.js`.

## 5. Movimento

Herdado do site de referencia - discreto e curto.

- Transicao padrao: `150ms ease` (cor, borda, transform).
- `breathe`: brilho pulsante lento (4s) para indicar "processando"/"online".
- `border-spin`: gradiente conico girando na borda de um card em destaque.
- `float-3d`: flutuacao vertical de 6px, 6s, so em elementos decorativos.
- Streaming de texto usa cursor `▍` piscando, nunca spinner no meio da resposta.
- Respeite `prefers-reduced-motion: reduce` desligando animacoes. Animacao SMIL
  (dentro de SVG) nao e afetada pela regra CSS: verifique com
  `matchMedia('(prefers-reduced-motion: reduce)')` e emita a versao estatica.

## 6. Layout

- Grade principal: sidebar fixa de 260px + area de conteudo fluida.
- Largura maxima de leitura: 860px para formularios e texto corrido.
- Espacamento vertical entre secoes: 24px; dentro de card: 16px.
- Cabecalho fixo de 56px com blur, mostrando status do Ollama e do backend de
  embeddings.

## 7. Regras que nao se quebram

1. Uma unica cor de acento (azul). Verde/ambar/vermelho so como status.
2. Bordas de 1px sempre em `--border` - nada de bordas grossas.
3. Serif apenas em display; sans em todo o resto.
4. Nenhum gradiente colorido de fundo; no maximo um brilho radial azul de baixa
   opacidade (<= 8%) atras do hero/cabecalho.
5. Texto em `--fg-muted` nunca abaixo de 0.8125rem.
6. Contraste minimo AA: `--fg` sobre `--bg` = 15:1, `--fg-muted` = 6:1.
