"""Arquitetura hibrida de prompts: mestre global + camada por agente.

O prompt mestre define a POLITICA (idioma, tom, uso da base de conhecimento,
formato da resposta). Cada agente adiciona a sua IDENTIDADE (nome, proposito,
observacoes). Em runtime montamos:

    system = mestre_renderizado + bloco_do_agente + contexto_recuperado

Um agente pode marcar `use_master = 0` e usar `prompt_override` para ignorar
totalmente o mestre (casos excepcionais).
"""
from __future__ import annotations

from typing import Iterable, Mapping

DEFAULT_MASTER_PROMPT = """Voce e {{agent_name}}, um assistente especializado que opera 100% local.

## Identidade
- Proposito: {{agent_purpose}}
- Observacoes do responsavel: {{agent_observations}}

## Regras de resposta
1. Responda sempre em portugues do Brasil, com objetividade e sem rodeios.
2. Priorize SEMPRE a base de conhecimento fornecida em CONTEXTO. Ela e a fonte
   de verdade sobre este dominio.
3. Ao usar um trecho do contexto, cite a origem no formato [1], [2] conforme a
   numeracao dos trechos.
4. Se a resposta nao estiver no contexto, diga explicitamente que a base de
   conhecimento nao cobre o assunto antes de complementar com conhecimento
   geral e sinalize o que e inferencia sua.
5. Nunca invente numeros, datas, autores ou citacoes.
6. Estruture respostas longas com titulos curtos e listas; use tabela quando
   comparar itens.
7. Se a pergunta for ambigua, faca no maximo uma pergunta de esclarecimento
   antes de responder.
"""

_AGENT_BLOCK = """
## Instrucoes especificas deste agente
Nome: {name}
Proposito: {purpose}
Observacoes: {observations}
"""

_NO_CONTEXT = """
## CONTEXTO
Nenhum documento relevante foi encontrado na base de conhecimento deste agente
para esta pergunta. Deixe isso claro na resposta.
"""

_CONTEXT_HEADER = """
## CONTEXTO (base de conhecimento de {name})
Use os trechos abaixo como fonte primaria. Cite-os como [n].

{blocks}
"""


def render_master(master: str, agent: Mapping) -> str:
    """Substitui as variaveis {{...}} do prompt mestre pelos dados do agente."""
    values = {
        "agent_name": (agent.get("name") or "Agente").strip(),
        "agent_purpose": (agent.get("purpose") or "assistente de uso geral").strip(),
        "agent_observations": (agent.get("observations") or "nenhuma").strip(),
        "master_date": "",
    }
    out = master or ""
    for key, value in values.items():
        out = out.replace("{{" + key + "}}", value)
    return out.strip()


def build_context_block(agent_name: str, passages: Iterable[Mapping]) -> str:
    passages = list(passages)
    if not passages:
        return _NO_CONTEXT
    blocks = []
    for i, p in enumerate(passages, start=1):
        source = p.get("filename") or "documento"
        loc = p.get("location") or ""
        label = f"[{i}] {source}" + (f" - {loc}" if loc else "")
        blocks.append(f"{label}\n{(p.get('text') or '').strip()}")
    return _CONTEXT_HEADER.format(name=agent_name, blocks="\n\n---\n\n".join(blocks))


def compose_system_prompt(agent: Mapping, master: str, passages: Iterable[Mapping]) -> str:
    """Monta o system prompt final do agente (mestre + agente + contexto)."""
    use_master = bool(agent.get("use_master", 1))
    override = (agent.get("prompt_override") or "").strip()

    if not use_master and override:
        base = render_master(override, agent)
    else:
        base = render_master(master or DEFAULT_MASTER_PROMPT, agent)
        if override:
            base += "\n" + render_master(override, agent)

    parts = [base]
    if use_master or not override:
        parts.append(
            _AGENT_BLOCK.format(
                name=(agent.get("name") or "Agente").strip(),
                purpose=(agent.get("purpose") or "nao informado").strip(),
                observations=(agent.get("observations") or "nenhuma").strip(),
            )
        )
    parts.append(build_context_block((agent.get("name") or "Agente").strip(), passages))
    return "\n".join(p.strip() for p in parts if p and p.strip())
