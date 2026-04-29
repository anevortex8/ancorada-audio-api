"""Gera o roteiro de áudio via Claude API."""
from __future__ import annotations
import json
import logging
from typing import Any

import anthropic

from . import config
from .prompts import AUDIO_SCRIPT_SYSTEM, build_audio_prompt

logger = logging.getLogger("ancorada-audio")


def generate_audio_script(
    customer_name: str,
    birth_profile: dict | None,
    diagnostic_text: str,
    diagnostic_json: Any = None,
    chart_json: Any = None,
) -> tuple[list[dict], str]:
    """Retorna (audio_blocks, full_script_text)."""

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

    # Parse JSON
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{[\s\S]*\}', raw_text)
        if match:
            data = json.loads(match.group())
        else:
            raise ValueError(f"Claude não retornou JSON válido. Início da resposta: {raw_text[:200]}")

    blocks = data.get("audio_blocks", [])
    if not blocks:
        raise ValueError("Nenhum bloco de áudio retornado pelo Claude.")

    full_script = "\n\n".join(f"[{b['label']}]\n{b['text']}" for b in blocks)

    logger.info("[audio-script] Roteiro gerado: %d blocos, ~%d palavras", len(blocks), len(full_script.split()))

    return blocks, full_script
