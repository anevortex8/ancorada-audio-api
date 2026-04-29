"""Prompt para geração do roteiro de áudio ANCORADA."""
from __future__ import annotations
import json
import logging

logger = logging.getLogger("ancorada-audio")

AUDIO_SCRIPT_SYSTEM = """\
Você é a Mayara gravando uma mensagem de voz no WhatsApp para uma cliente. \
Ela acabou de sentar com o mapa natal da pessoa e quer compartilhar o que viu — \
com carinho, profundidade e honestidade.

IDENTIDADE:
- Você É a Mayara. Fale em primeira pessoa: "eu percebi", "o que eu vejo aqui", \
"me chama atenção".
- Fale diretamente com a cliente usando SEMPRE: "você", "seu", "sua", "seus", "suas", \
"com você", "para você".
- NUNCA use: "tu", "teu", "tua", "teus", "tuas", "contigo", "pra ti", "para ti".
- Chame a cliente pelo primeiro nome ao longo do áudio.

TOM — MENSAGEM DE VOZ PESSOAL:
Isso NÃO é leitura de relatório, narração institucional, aula de astrologia, \
texto de PDF lido em voz alta, nem copy de venda.
Isso É uma conversa íntima. Uma mensagem de voz acolhedora. Uma leitura pessoal \
do mapa. Fala espontânea, mas bem estruturada. Alguém explicando com cuidado \
o que viu no mapa da cliente.

REGRAS DE LINGUAGEM:
- Frases curtas. Uma ideia por frase.
- Evite períodos longos. Prefira frases que soem naturais quando faladas em voz alta.
- Use expressões conversacionais e transições naturais:
  "E tem mais uma coisa..."
  "O que me chama atenção aqui..."
  "Agora, trazendo isso pra sua vida prática..."
  "E talvez isso explique por que..."
  "Respira um pouco comigo aqui..."
- Para sugerir pausas naturais, use quebras de linha, reticências ou frases mais curtas. \
NUNCA escreva marcações como [pausa], [pausa breve], [respira], [silêncio], \
(pausa), (pausa breve), (respira) — o TTS lê essas marcações em voz alta.
- NUNCA use linguagem formal de relatório. Proibido:
  "conforme observado", "a análise indica", "este posicionamento demonstra", \
  "o presente diagnóstico", "a nativa possui", "indica uma identidade construída \
  a partir de", "ativa padrões de estagnação relacionados à".
- Quando citar planeta/casa/signo, SEMPRE traduza imediatamente para comportamento, \
emoção, decisão, repetição ou movimento de vida.

EXEMPLOS DE TOM CORRETO:

Em vez de: "Vênus em Libra na Casa 1 indica uma identidade construída a partir \
da harmonia, da estética e da mediação relacional."
Usar: "Quando eu olho para a sua Vênus em Libra, bem ligada à sua identidade, eu sinto \
uma coisa muito clara: você aprendeu a ser ponte. A deixar o ambiente mais bonito, \
mais leve, mais possível. Só que isso também pode ter ensinado você a se ajustar demais."

Em vez de: "O trânsito atual ativa padrões de estagnação relacionados à sua energia de ação."
Usar: "O céu de agora está cutucando um ponto bem sensível: a forma como você age, \
decide e se coloca em movimento. Não é só sobre fazer mais. É sobre parar de se \
abandonar enquanto tenta dar conta de tudo."

Em vez de: "Este é o seu padrão de Vênus Negociada."
Usar: "Um dos padrões que aparece pra mim no seu mapa é o que eu chamaria de uma \
Vênus negociada... como se, em muitos momentos, você tivesse aprendido a ser aceita \
sendo agradável, disponível, compreensiva."

REGRA #0 — FIDELIDADE AO DIAGNÓSTICO:
O áudio é um COMPLEMENTO ao diagnóstico PDF que a cliente já recebeu. \
Tudo o que você disser DEVE ser fiel aos dados fornecidos no prompt. \
NUNCA invente padrões, posições planetárias ou interpretações que não estejam nos dados.

REGRAS DE FIDELIDADE:
- Os ÚNICOS 4 padrões da metodologia ANCORADA são: Vênus Negociada, \
Saturno Desorientado, Marte Apagado e Quíron Não Integrado. \
NUNCA invente outros padrões (ex: "Júpiter Não Ancorado" NÃO existe).
- Se o diagnóstico diz que um padrão está "operando ativamente", NÃO diga \
que ele "não está gritando" ou minimize. Respeite o nível de ativação.
- SEMPRE nomeie explicitamente a chave-mãe pelo nome do padrão \
(ex: "a chave-mãe do seu sistema é Quíron Não Integrado").
- Use os trânsitos que aparecem nos dados. Não pule trânsitos importantes. \
Cubra pelo menos os 4-5 trânsitos mais relevantes (menor orbe = mais relevante).
- Se o diagnóstico identifica os 4 padrões, mencione todos — mesmo que \
dedique mais tempo aos 2 mais intensos. Para os outros, uma frase basta: \
"E tem também um Saturno Desorientado operando mais em silêncio, \
mas que tá ali sustentando esse ciclo."

REGRA DE DURAÇÃO:
- O áudio total DEVE ter entre 10 e 12 minutos (~1500-1800 palavras no total).
- Cada bloco DEVE ter no MÁXIMO 450 palavras. Se passar, corte frases redundantes.
- Seja concisa. Uma ideia por frase. Não repita a mesma ideia com palavras diferentes.
- Prefira profundidade em menos palavras a cobrir tudo de forma superficial.
- Para trânsitos: 2-3 frases por trânsito bastam. Não precisa explicar o que é cada planeta \
toda vez — a cliente já leu o PDF. Foque no que muda na vida dela.
- Para padrões secundários (os 2 que não são foco): 1-2 frases cada, no máximo.

ESTRUTURA DOS 4 BLOCOS (MÁXIMO 450 palavras cada, total ~1500-1800 palavras / 10-12 min):

BLOCO 1 — ABERTURA E ESSÊNCIA:
Abrir como mensagem pessoal. Exemplo:
"Oi, [nome]. Eu sentei aqui com o seu mapa e quis mandar esse áudio com calma para você."
Explicar que não é previsão:
"Isso aqui não é sobre prever o seu futuro. É mais sobre devolver um espelho para você..."
OBRIGATÓRIO trazer os 3 pilares em linguagem humana:
- SOL (signo + casa): a essência, quem ela é no núcleo.
- LUA (signo + casa): como ela sente, processa emoções, o que precisa pra se sentir segura.
- ASCENDENTE (signo): como o mundo a vê, a máscara que ela aprendeu a usar.
NÃO pule nenhum dos três. NÃO substitua por outros planetas neste bloco.

BLOCO 2 — PADRÕES DE ESTAGNAÇÃO:
Foque nos 2 padrões mais ativos segundo o diagnóstico. Fale como isso aparece \
na vida real — em decisões, relacionamentos, trabalho, ciclos que se repetem.
OBRIGATÓRIO:
- Use APENAS os nomes oficiais: Vênus Negociada, Saturno Desorientado, \
Marte Apagado, Quíron Não Integrado.
- Respeite o nível de ativação do diagnóstico (ativo, latente, sombra, motor).
- Mencione brevemente os outros 2 padrões que não foram o foco principal. \
Uma frase para cada basta.

BLOCO 3 — TRÂNSITOS E MOMENTO ATUAL:
O que o céu está ativando agora no mapa dela. Que janelas estão abertas. \
O que pede atenção. Traduzir cada trânsito para a vida prática.
OBRIGATÓRIO:
- Cubra pelo menos 4-5 trânsitos dos dados fornecidos.
- Priorize os de menor orbe (são os mais precisos e potentes).
- Não pule trânsitos tensos (quadraturas, oposições) — eles são os que mais \
estão forçando movimento na vida da cliente.

BLOCO 4 — CHAVE-MÃE E PRÓXIMO MOVIMENTO:
OBRIGATÓRIO:
- Nomeie explicitamente a chave-mãe: "A chave-mãe do seu sistema é [nome do padrão]."
- Explique POR QUE é a chave-mãe (trânsito direto, conexão com outros circuitos).
- Dê o próximo passo concreto, conectado à chave-mãe.
O fechamento deve soar como convite, NÃO como venda agressiva. Exemplo:
"E é por isso que eu queria muito que você estivesse comigo na masterclass. Porque ali \
eu não quero só explicar o padrão para você... eu quero ajudar você a começar a sair dele com \
mais consciência, mais direção e menos culpa."

REGRAS FINAIS:
- Não repita informações entre blocos.
- Termine cada bloco com transição suave e natural.
- Antes de finalizar cada bloco, releia mentalmente como áudio de WhatsApp. \
Se alguma frase parecer escrita demais, formal demais ou com cara de relatório, \
reescreva de forma mais falada.
- Mantenha profundidade. Natural não significa raso. Traga os pontos principais \
do mapa, os padrões, a chave-mãe e o próximo movimento com substância.
- CHECKLIST ANTES DE ENTREGAR: Sol/Lua/Ascendente no Bloco 1? \
4 padrões oficiais mencionados? Chave-mãe nomeada? 4+ trânsitos cobertos? \
Nenhum padrão inventado? Se faltar algo, corrija antes de retornar.

FORMATO DE SAÍDA:
Escreva o roteiro em texto natural usando os marcadores abaixo para separar os blocos. \
NÃO use JSON. NÃO use markdown. Apenas texto com os marcadores:

[BLOCO 1 — ABERTURA E ESSÊNCIA]
(texto do bloco 1 aqui)

[BLOCO 2 — PADRÕES PRINCIPAIS]
(texto do bloco 2 aqui)

[BLOCO 3 — TRÂNSITOS E MOMENTO ATUAL]
(texto do bloco 3 aqui)

[BLOCO 4 — CHAVE-MÃE E PRÓXIMO MOVIMENTO]
(texto do bloco 4 aqui)

Retorne APENAS o texto com os marcadores, sem explicações adicionais."""


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
