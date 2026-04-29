"""Prompt para geração do roteiro de áudio ANCORADA."""
from __future__ import annotations
import json
import logging

logger = logging.getLogger("ancorada-audio")

AUDIO_SCRIPT_SYSTEM = """\
Você é a voz do Diagnóstico ANCORADA — um áudio personalizado que a pessoa vai ouvir \
como se fosse uma conversa íntima e ritualística sobre o próprio mapa natal.

Tom: conversacional, íntimo, ritualístico. Como se estivesse falando diretamente \
ao ouvido da pessoa, com cuidado e profundidade. Sem ser professoral. \
Sem termos técnicos soltos — sempre contextualize.

REGRAS:
- Sempre fale diretamente com a pessoa pelo primeiro nome.
- Use linguagem oral natural — contrações, pausas naturais (use "..." para pausas).
- NÃO use jargão astrológico sem explicar. Ex: não diga "Quíron em Áries", diga \
"essa ferida que você carrega desde cedo, que no seu mapa aparece como Quíron em Áries..."
- Cada bloco deve ter entre 2-3 minutos de fala (~300-450 palavras).
- Total: 4 blocos (~10-12 minutos).
- Não repita informações já ditas em blocos anteriores.
- Termine cada bloco com uma frase de transição suave.
- O último bloco deve fechar com um convite à ação gentil (masterclass, sessão, reflexão).

ESTRUTURA DOS 4 BLOCOS:
BLOCO 1 — ABERTURA E ESSÊNCIA: Saudação pessoal. Contexto do Sol, Lua e Ascendente. \
Quem essa pessoa é na essência vs. como o mundo a vê.

BLOCO 2 — PADRÕES DE ESTAGNAÇÃO: Os 1-2 padrões mais relevantes do diagnóstico. \
Vênus Negociada, Saturno Desorientado, Marte Apagado ou Quíron Não Integrado. \
Fale como isso aparece na vida real da pessoa.

BLOCO 3 — TRÂNSITOS E MOMENTO ATUAL: O que o céu está ativando agora no mapa dela. \
Que janelas estão abertas. O que pede atenção.

BLOCO 4 — CHAVE-MÃE E PRÓXIMO MOVIMENTO: A chave-mãe do sistema (a alavanca principal). \
O próximo passo concreto. Fechamento ritualístico com encorajamento.

FORMATO DE SAÍDA (JSON):
{
  "audio_blocks": [
    {"label": "BLOCO 1 — ABERTURA E ESSÊNCIA", "text": "..."},
    {"label": "BLOCO 2 — PADRÕES DE ESTAGNAÇÃO", "text": "..."},
    {"label": "BLOCO 3 — TRÂNSITOS E MOMENTO ATUAL", "text": "..."},
    {"label": "BLOCO 4 — CHAVE-MÃE E PRÓXIMO MOVIMENTO", "text": "..."}
  ]
}

Retorne APENAS o JSON, sem markdown, sem ```json, sem explicações."""


def safe_compact_for_prompt(value, max_depth: int = 3, max_items: int = 20, _depth: int = 0) -> str:
    """Converte qualquer valor para texto seguro para prompt.

    Aceita dict, list, str, number, None — nunca quebra com .items().
    """
    if value is None:
        return ""

    if isinstance(value, str):
        return value[:3000] if len(value) > 3000 else value

    if isinstance(value, (int, float, bool)):
        return str(value)

    if _depth >= max_depth:
        if isinstance(value, dict):
            return f"{{...{len(value)} keys}}"
        if isinstance(value, list):
            return f"[...{len(value)} items]"
        return str(value)[:200]

    if isinstance(value, dict):
        lines = []
        for i, (k, v) in enumerate(value.items()):
            if i >= max_items:
                lines.append(f"  ... (+{len(value) - max_items} more)")
                break
            lines.append(f"  {k}: {safe_compact_for_prompt(v, max_depth, max_items, _depth + 1)}")
        return "\n".join(lines)

    if isinstance(value, list):
        lines = []
        for i, v in enumerate(value):
            if i >= max_items:
                lines.append(f"  ... (+{len(value) - max_items} more)")
                break
            lines.append(f"  [{i}] {safe_compact_for_prompt(v, max_depth, max_items, _depth + 1)}")
        return "\n".join(lines)

    return str(value)[:200]


def _extract_patterns_from_json(diagnostic_json) -> str:
    """Extrai padrões do diagnostic_json de forma robusta."""
    if not diagnostic_json:
        return ""

    if not isinstance(diagnostic_json, dict):
        return safe_compact_for_prompt(diagnostic_json, max_depth=2, max_items=10)

    parts = []

    # Tentar formato com "patterns" (lista)
    patterns = diagnostic_json.get("patterns", [])
    if isinstance(patterns, list):
        for p in patterns[:10]:
            if isinstance(p, dict):
                name = p.get("name", p.get("title", ""))
                interp = p.get("interpretation", p.get("text", []))
                if isinstance(interp, list):
                    interp = " ".join(str(x) for x in interp[:2])
                elif not isinstance(interp, str):
                    interp = str(interp)[:300]
                parts.append(f"- {name}: {interp}")
            elif isinstance(p, str):
                parts.append(f"- {p}")
    elif isinstance(patterns, dict):
        for k, v in patterns.items():
            parts.append(f"- {k}: {safe_compact_for_prompt(v, max_depth=1)}")

    # Tentar chave-mãe
    final_sections = diagnostic_json.get("final_sections", [])
    if isinstance(final_sections, list):
        for section in final_sections:
            if isinstance(section, dict):
                title = section.get("title", "")
                if isinstance(title, str) and "chave" in title.lower():
                    paragraphs = section.get("paragraphs", [])
                    if isinstance(paragraphs, list):
                        parts.append(f"\nCHAVE-MÃE: {' '.join(str(x) for x in paragraphs)}")
                    elif isinstance(paragraphs, str):
                        parts.append(f"\nCHAVE-MÃE: {paragraphs}")
    elif isinstance(final_sections, dict):
        for k, v in final_sections.items():
            if isinstance(k, str) and "chave" in k.lower():
                parts.append(f"\nCHAVE-MÃE: {safe_compact_for_prompt(v, max_depth=1)}")

    # Fallback: pegar tudo que pareça relevante
    if not parts:
        for key in ["ancorada_extraction", "diagnosis", "summary", "resultado"]:
            val = diagnostic_json.get(key)
            if val:
                parts.append(f"\n--- {key.upper()} ---\n{safe_compact_for_prompt(val, max_depth=2)}")
                break

    return "\n".join(parts)


def _extract_chart_summary(chart_json) -> str:
    """Extrai resumo do chart_json de forma robusta. Nunca quebra."""
    if not chart_json:
        return ""

    if not isinstance(chart_json, dict):
        logger.warning("[audio-script] chart_json não é dict, ignorando")
        return ""

    parts = []

    # Posições planetárias
    natal = chart_json.get("natal_chart", chart_json.get("natal_planets", chart_json.get("planets", {})))
    if isinstance(natal, dict):
        planet_lines = []
        for planet, data in natal.items():
            if isinstance(data, dict):
                planet_lines.append(f"{planet}: {data.get('sign', '')} casa {data.get('house', '')}")
            elif isinstance(data, str):
                planet_lines.append(f"{planet}: {data}")
        if planet_lines:
            parts.append("--- POSIÇÕES PLANETÁRIAS ---\n" + "\n".join(planet_lines[:15]))
    elif isinstance(natal, list):
        planet_lines = []
        for item in natal[:15]:
            if isinstance(item, dict):
                name = item.get("name", item.get("planet", ""))
                sign = item.get("sign", "")
                house = item.get("house", "")
                planet_lines.append(f"{name}: {sign} casa {house}")
            elif isinstance(item, str):
                planet_lines.append(item)
        if planet_lines:
            parts.append("--- POSIÇÕES PLANETÁRIAS ---\n" + "\n".join(planet_lines))

    # Trânsitos (pode ser lista ou dict)
    transits = chart_json.get("current_transits", {})
    if isinstance(transits, list):
        transit_lines = []
        for item in transits[:15]:
            if isinstance(item, dict):
                tp = item.get("transit_planet", item.get("planet", ""))
                target = item.get("natal_target", "")
                aspect = item.get("aspect", "")
                pos = item.get("transit_position", {})
                sign = pos.get("sign", "") if isinstance(pos, dict) else ""
                transit_lines.append(f"{tp} {aspect} {target} (em {sign})")
            elif isinstance(item, str):
                transit_lines.append(item)
        if transit_lines:
            parts.append("--- TRÂNSITOS ATUAIS ---\n" + "\n".join(transit_lines))
    elif isinstance(transits, dict):
        transit_lines = []
        for planet, data in transits.items():
            if isinstance(data, dict):
                transit_lines.append(f"{planet} transitando em {data.get('sign', '')} casa {data.get('house', '')}")
            elif isinstance(data, str):
                transit_lines.append(f"{planet}: {data}")
        if transit_lines:
            parts.append("--- TRÂNSITOS ATUAIS ---\n" + "\n".join(transit_lines))

    return "\n".join(parts)


def build_audio_prompt(customer_name: str, birth_profile: dict | None,
                       diagnostic_text: str, diagnostic_json: Any,
                       chart_json: Any) -> str:
    """Monta o prompt do usuário para geração do roteiro.

    Prioridade: diagnostic_text > diagnostic_json > chart_json.
    Nunca quebra com estruturas inesperadas.
    """
    parts = [f"Nome da cliente: {customer_name}"]

    # Birth profile (opcional)
    if birth_profile and isinstance(birth_profile, dict):
        bd = birth_profile.get("birth_date", "")
        bt = birth_profile.get("birth_time", "")
        bc = birth_profile.get("birth_city", "")
        bs = birth_profile.get("birth_state", "")
        bco = birth_profile.get("birth_country", "Brasil")
        if bd:
            parts.append(f"Nascimento: {bd} às {bt}")
            parts.append(f"Local: {bc}, {bs}, {bco}")

    # Fonte principal: diagnostic_text
    if diagnostic_text:
        parts.append(f"\n--- DIAGNÓSTICO COMPLETO ---\n{diagnostic_text[:12000]}")

    # Fonte secundária: diagnostic_json
    if diagnostic_json:
        try:
            extracted = _extract_patterns_from_json(diagnostic_json)
            if extracted:
                parts.append(f"\n--- PADRÕES IDENTIFICADOS ---\n{extracted}")
        except Exception as e:
            logger.warning("[audio-script] Erro ao extrair diagnostic_json: %s", e)

    # Fonte terciária: chart_json (opcional, nunca obrigatório)
    if chart_json:
        try:
            chart_summary = _extract_chart_summary(chart_json)
            if chart_summary:
                parts.append(f"\n{chart_summary}")
        except Exception as e:
            logger.warning("[audio-script] Erro ao extrair chart_json: %s", e)

    return "\n".join(parts)


# Type alias for flexibility
from typing import Any
