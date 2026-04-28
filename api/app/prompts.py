"""Prompt para geração do roteiro de áudio ANCORADA."""

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


def build_audio_prompt(customer_name: str, birth_profile: dict, diagnostic_text: str,
                       diagnostic_json: dict, chart_json: dict) -> str:
    """Monta o prompt do usuário para geração do roteiro."""
    parts = [
        f"Nome da cliente: {customer_name}",
        f"Nascimento: {birth_profile.get('birth_date', '')} às {birth_profile.get('birth_time', '')}",
        f"Local: {birth_profile.get('birth_city', '')}, {birth_profile.get('birth_state', '')}, {birth_profile.get('birth_country', 'Brasil')}",
    ]

    if diagnostic_text:
        parts.append(f"\n--- DIAGNÓSTICO COMPLETO ---\n{diagnostic_text[:12000]}")

    if diagnostic_json:
        # Extrair padrões
        patterns = diagnostic_json.get("patterns", [])
        if patterns:
            patterns_text = "\n".join(
                f"- {p.get('name', '')}: {' '.join(p.get('interpretation', [])[:2])}"
                for p in patterns
            )
            parts.append(f"\n--- PADRÕES IDENTIFICADOS ---\n{patterns_text}")

        # Chave-mãe
        for section in diagnostic_json.get("final_sections", []):
            if "chave" in section.get("title", "").lower():
                parts.append(f"\n--- CHAVE-MÃE ---\n{' '.join(section.get('paragraphs', []))}")

    if chart_json:
        natal = chart_json.get("natal_chart", chart_json.get("natal_planets", chart_json.get("planets", {})))
        if isinstance(natal, dict):
            planet_summary = []
            for planet, data in natal.items():
                if isinstance(data, dict):
                    planet_summary.append(f"{planet}: {data.get('sign', '')} casa {data.get('house', '')}")
            if planet_summary:
                parts.append(f"\n--- POSIÇÕES PLANETÁRIAS ---\n" + "\n".join(planet_summary))

        transits = chart_json.get("current_transits", {})
        if transits:
            transit_lines = []
            for planet, data in transits.items():
                if isinstance(data, dict):
                    transit_lines.append(f"{planet} transitando em {data.get('sign', '')} casa {data.get('house', '')}")
            if transit_lines:
                parts.append(f"\n--- TRÂNSITOS ATUAIS ---\n" + "\n".join(transit_lines))

    return "\n".join(parts)
