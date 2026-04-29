"""Gera o roteiro de áudio via Claude API."""
from __future__ import annotations
import json
import logging
import re
from typing import Any

import anthropic

from . import config
from .prompts import AUDIO_SCRIPT_SYSTEM, build_audio_prompt

logger = logging.getLogger("ancorada-audio")

# Marcadores esperados nos blocos
BLOCK_LABELS = [
    "BLOCO 1 — ABERTURA E ESSÊNCIA",
    "BLOCO 2 — PADRÕES PRINCIPAIS",
    "BLOCO 3 — TRÂNSITOS E MOMENTO ATUAL",
    "BLOCO 4 — CHAVE-MÃE E PRÓXIMO MOVIMENTO",
]

# Regex flexível: [BLOCO 1 ...], [BLOCO 2 ...], etc.
_BLOCK_RE = re.compile(r"\[BLOCO\s+(\d)\s*[—–\-]\s*([^\]]*)\]", re.IGNORECASE)


def parse_audio_blocks_from_text(text: str) -> tuple[list[dict], str]:
    """Parseia blocos de áudio a partir de texto com marcadores [BLOCO N — TÍTULO].

    Fallback: se não encontrar os 4 blocos, divide o texto em 4 partes iguais.
    Nunca levanta exceção de parse.

    Returns:
        (blocks, parser_used)
    """
    matches = list(_BLOCK_RE.finditer(text))

    if len(matches) >= 4:
        blocks = []
        for i, match in enumerate(matches):
            label = f"BLOCO {match.group(1)} — {match.group(2).strip()}"
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            block_text = text[start:end].strip()
            blocks.append({"label": label, "text": block_text})
        return blocks, "text_blocks"

    # Fallback: dividir por tamanho aproximado
    clean = text.strip()
    if not clean:
        return [], "empty"

    chunk_size = len(clean) // 4
    blocks = []
    for i, label in enumerate(BLOCK_LABELS):
        start = i * chunk_size
        end = (i + 1) * chunk_size if i < 3 else len(clean)
        blocks.append({"label": label, "text": clean[start:end].strip()})

    return blocks, "fallback_split"


def _try_parse_json(raw_text: str) -> list[dict] | None:
    """Tenta extrair blocos de JSON. Retorna None se falhar."""
    try:
        data = json.loads(raw_text)
        blocks = data.get("audio_blocks", [])
        if blocks and isinstance(blocks, list) and all(isinstance(b, dict) and "text" in b for b in blocks):
            return blocks
    except (json.JSONDecodeError, AttributeError):
        pass

    # Tentar extrair JSON de dentro do texto
    try:
        match = re.search(r'\{[\s\S]*\}', raw_text)
        if match:
            data = json.loads(match.group())
            blocks = data.get("audio_blocks", [])
            if blocks and isinstance(blocks, list) and all(isinstance(b, dict) and "text" in b for b in blocks):
                return blocks
    except (json.JSONDecodeError, AttributeError):
        pass

    return None


def generate_audio_script(
    customer_name: str,
    birth_profile: dict | None,
    diagnostic_text: str,
    diagnostic_json: Any = None,
    chart_json: Any = None,
) -> tuple[list[dict], str, str]:
    """Retorna (audio_blocks, full_script_text, parser_used)."""

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    user_prompt = build_audio_prompt(
        customer_name=customer_name,
        birth_profile=birth_profile,
        diagnostic_text=diagnostic_text,
        diagnostic_json=diagnostic_json or {},
        chart_json=chart_json or {},
    )

    logger.info("[audio-script] Gerando roteiro para %s (model=%s)", customer_name, config.ANTHROPIC_MODEL)

    response = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=config.MAX_TOKENS,
        system=AUDIO_SCRIPT_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = response.content[0].text.strip()
    logger.info("[audio-script] raw response length: %d", len(raw_text))

    # 1. Tentar JSON primeiro (caso o modelo ainda retorne JSON)
    json_blocks = _try_parse_json(raw_text)
    if json_blocks:
        parser_used = "json"
        blocks = json_blocks
    else:
        # 2. Parse por marcadores de texto (método principal)
        blocks, parser_used = parse_audio_blocks_from_text(raw_text)

    word_count = len(raw_text.split())
    logger.info("[audio-script] parser used: %s", parser_used)
    logger.info("[audio-script] blocks count: %d", len(blocks))
    logger.info("[audio-script] words count: %d", word_count)

    # Validar conteúdo mínimo
    if not blocks or word_count < 100:
        raise ValueError("Roteiro insuficiente gerado.")

    full_script = "\n\n".join(f"[{b['label']}]\n{b['text']}" for b in blocks)

    return blocks, full_script, parser_used
