"""ANCORADA Audio API — FastAPI application."""
from __future__ import annotations
import base64
import logging
import re
import threading
import unicodedata
import uuid
from datetime import datetime, timezone

import requests

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .models import (
    AudioScriptRequest,
    AudioScriptResponse,
    AudioBlock,
    GenerateAudioRequest,
    GenerateAudioResponse,
)
from .script_generator import generate_audio_script
from .elevenlabs_client import generate_audio_block, concatenate_mp3_blocks

logging.basicConfig(level=logging.INFO, format="%(name)s | %(levelname)s | %(message)s")
logger = logging.getLogger("ancorada-audio")

# ── Job store (in-memory) ──────────────────────────────────────────
# Em produção no Render (single instance), dict em memória é suficiente.
_jobs: dict[str, dict] = {}

app = FastAPI(
    title="ANCORADA Audio API",
    description="Gera roteiro de áudio personalizado e MP3 via ElevenLabs para o Diagnóstico ANCORADA.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ────────────────────────────────────────────────────────

INVALID_VOICE_IDS = {"", "sarah", "mayara", "default", "null", "none", "undefined"}


def _resolve_voice_id(raw: str) -> tuple[str, str]:
    """Retorna (voice_id, source). Nunca fallback silencioso."""
    raw = (raw or "").strip()
    if raw.lower() not in INVALID_VOICE_IDS and len(raw) > 10:
        return raw, "payload"
    if config.ELEVENLABS_DEFAULT_VOICE_ID:
        return config.ELEVENLABS_DEFAULT_VOICE_ID, "env_default"
    return "", "none"


def _make_slug(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower().strip()
    return re.sub(r"[-\s]+", "-", normalized) or "cliente"


def _validate_signed_upload(signed) -> None:
    """Valida campos do signed_upload antes de tentar upload. Levanta HTTPException 400."""
    if not isinstance(signed.token, str) or not signed.token.strip():
        raise HTTPException(status_code=400, detail="signed_upload.token precisa ser string")
    if not isinstance(signed.path, str) or not signed.path.strip():
        raise HTTPException(status_code=400, detail="signed_upload.path precisa ser string")
    if not isinstance(signed.signed_url, str) or not signed.signed_url.strip():
        raise HTTPException(status_code=400, detail="signed_upload.signed_url precisa ser string")


def _do_signed_upload(signed, audio_data: bytes, audio_generation_id: str = "", job_label: str = "") -> tuple[bool, str]:
    """Faz upload via signed URL. Retorna (success, error_message)."""
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

    token = signed.token.strip()
    base_url = signed.signed_url.strip()

    # Montar URL com token via urllib.parse (nunca concatenação frágil)
    parsed = urlparse(base_url)
    existing_params = parse_qs(parsed.query, keep_blank_values=True)

    signed_url_has_token = "token" in existing_params

    # Só adicionar token se a signed_url não trouxer um
    if not signed_url_has_token:
        existing_params["token"] = [token]

    # Rebuild querystring com valores flat (não listas)
    flat_params = {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in existing_params.items()}
    new_query = urlencode(flat_params, doseq=True)
    upload_url = urlunparse(parsed._replace(query=new_query))

    upload_url_has_token = "token=" in upload_url

    logger.info("[audio-upload] %stoken_type=%s", job_label, type(token).__name__)
    logger.info("[audio-upload] %ssigned_url_has_token=%s", job_label, signed_url_has_token)
    logger.info("[audio-upload] %supload_url_has_token=%s", job_label, upload_url_has_token)
    logger.info("[audio-upload] %smp3_size=%d", job_label, len(audio_data))

    try:
        resp = requests.put(
            upload_url,
            data=audio_data,
            headers={"Content-Type": "audio/mpeg"},
            timeout=120,
        )
        if resp.status_code in (200, 201):
            logger.info("[audio-upload] %suploaded=true", job_label)
            logger.info("[audio-upload] %saudio_generation_id=%s", job_label, audio_generation_id or "(none)")
            logger.info("[audio-upload] %sstorage_path=%s", job_label, signed.path)
            logger.info("[audio-upload] %sfinal_size=%d", job_label, len(audio_data))
            return True, ""
        else:
            error_text = resp.text[:300]
            try:
                error_json = resp.json()
                error_text = str(error_json.get("message", error_json))
            except Exception:
                pass
            logger.error("[audio-upload] %sresponse_status=%d", job_label, resp.status_code)
            logger.error("[audio-upload] %sresponse_text=%s", job_label, error_text)
            return False, error_text
    except Exception as e:
        logger.exception("[audio-upload] %suploaded=false, exception", job_label)
        return False, str(e)


def _generate_and_upload(job_id: str, req: GenerateAudioRequest, voice_id: str, voice_source: str):
    """Roda em background thread: gera áudio + faz upload via signed URL."""
    try:
        _jobs[job_id]["status"] = "generating"
        _jobs[job_id]["started_at"] = datetime.now(timezone.utc).isoformat()

        # Gerar áudio bloco a bloco
        audio_parts: list[bytes] = []
        for i, block in enumerate(req.audio_blocks):
            logger.info("[job:%s] bloco %d/%d: %s", job_id[:8], i + 1, len(req.audio_blocks), block.label)
            audio_bytes = generate_audio_block(
                text=block.text,
                voice_id=voice_id,
                model_id=req.model_id,
                stability=req.voice_settings.stability,
                similarity_boost=req.voice_settings.similarity_boost,
                style=req.voice_settings.style,
                use_speaker_boost=req.voice_settings.use_speaker_boost,
                speed=req.speed,
                block_label=block.label,
            )
            audio_parts.append(audio_bytes)
            _jobs[job_id]["blocks_completed"] = i + 1

        # Concatenar
        logger.info("[job:%s] concatenando %d blocos", job_id[:8], len(audio_parts))
        final_audio = concatenate_mp3_blocks(audio_parts)

        # Duração
        duration_seconds = None
        try:
            from pydub import AudioSegment
            import io
            segment = AudioSegment.from_mp3(io.BytesIO(final_audio))
            duration_seconds = round(len(segment) / 1000, 1)
        except Exception:
            pass

        customer_name = req.customer_name or "cliente"
        filename = f"audio-ancorada-{_make_slug(customer_name)}.mp3"

        # Upload via signed URL
        uploaded = False
        storage_path = ""
        upload_mode = "signed_upload" if (req.signed_upload and req.signed_upload.signed_url) else "none"
        upload_error = ""

        if req.signed_upload and req.signed_upload.signed_url:
            signed = req.signed_upload
            if not isinstance(signed.token, str) or not signed.token.strip():
                upload_error = f"token inválido: tipo={type(signed.token).__name__}"
                logger.error("[job:%s] %s", job_id[:8], upload_error)
            elif not isinstance(signed.path, str) or not signed.path.strip():
                upload_error = "path inválido"
                logger.error("[job:%s] %s", job_id[:8], upload_error)
            else:
                uploaded, err = _do_signed_upload(
                    signed, final_audio,
                    audio_generation_id=req.audio_generation_id,
                    job_label=f"[job:{job_id[:8]}] ",
                )
                storage_path = signed.path
                if not uploaded:
                    upload_error = err or "Upload para Supabase falhou"

        # Status: completed somente se upload deu certo (quando signed_upload foi pedido)
        if upload_mode == "signed_upload" and not uploaded:
            status = "failed"
        else:
            status = "completed"

        _jobs[job_id].update({
            "status": status,
            "uploaded": uploaded,
            "storage_path": storage_path,
            "filename": filename,
            "duration_seconds": duration_seconds,
            "file_size_bytes": len(final_audio),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "voice_id_source": voice_source,
            "voice_id_prefix": voice_id[:6] if voice_id else "",
            "model": req.model_id,
            "blocks_count": len(req.audio_blocks),
            "upload_mode": upload_mode,
            "tts_speed": req.speed,
            "script_sanitized": True,
            "pronoun_style": "voce_seu_sua",
        })
        if upload_error:
            _jobs[job_id]["error"] = upload_error

        logger.info("[job:%s] status=%s, uploaded=%s, size=%d bytes", job_id[:8], status, uploaded, len(final_audio))

    except Exception as e:
        logger.exception("[job:%s] failed", job_id[:8])
        _jobs[job_id].update({
            "status": "failed",
            "error": str(e),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })


# ── Endpoints ──────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "2.0.0",
        "model": config.ANTHROPIC_MODEL,
        "elevenlabs_configured": bool(config.ELEVENLABS_API_KEY),
        "active_jobs": sum(1 for j in _jobs.values() if j["status"] in ("pending", "generating")),
    }


@app.post("/generate-audio-script", response_model=AudioScriptResponse)
def generate_script_endpoint(req: AudioScriptRequest):
    """Gera o roteiro de áudio personalizado via Claude."""

    customer_name = req.customer.get_name()

    logger.info("[audio-script] customer: %s", customer_name)
    logger.info("[audio-script] has diagnostic_text: %s (len=%d)", bool(req.diagnostic_text), len(req.diagnostic_text))
    logger.info("[audio-script] has diagnostic_json: %s", bool(req.diagnostic_json))
    logger.info("[audio-script] diagnostic_id: %s", req.diagnostic_id or "(none)")

    has_diagnostic_text = bool(req.diagnostic_text and req.diagnostic_text.strip())
    has_diagnostic_json = bool(req.diagnostic_json)

    if not has_diagnostic_text and not has_diagnostic_json:
        raise HTTPException(
            status_code=422,
            detail="Pelo menos diagnostic_text ou diagnostic_json deve ser fornecido.",
        )

    source = "diagnostic_text" if has_diagnostic_text else "diagnostic_json"
    logger.info("[audio-script] using source: %s", source)

    if not config.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    birth_profile = req.birth_profile.model_dump() if req.birth_profile else None

    try:
        blocks, full_script, parser_used = generate_audio_script(
            customer_name=customer_name,
            birth_profile=birth_profile,
            diagnostic_text=req.diagnostic_text,
            diagnostic_json=req.diagnostic_json,
            chart_json=req.chart_json,
            is_mentorada=req.is_mentorada,
        )
    except ValueError as e:
        logger.warning("[audio-script] Roteiro insuficiente: %s", e)
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("[audio-script] Erro na geração do roteiro")
        raise HTTPException(status_code=500, detail=str(e))

    word_count = len(full_script.split())
    estimated_minutes = round(word_count / 150, 1)

    return AudioScriptResponse(
        audio_script=full_script,
        audio_blocks=[AudioBlock(label=b["label"], text=b["text"]) for b in blocks],
        estimated_duration_minutes=estimated_minutes,
        metadata={
            "template": config.TEMPLATE_VERSION,
            "model": config.ANTHROPIC_MODEL,
            "word_count": word_count,
            "blocks_count": len(blocks),
            "source": source,
            "style_mode": "whatsapp_voice_note",
            "parser": parser_used,
            "diagnostic_id": req.diagnostic_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.post("/generate-audio-async")
def generate_audio_async_endpoint(req: GenerateAudioRequest):
    """Inicia geração de áudio em background. Retorna job_id imediatamente."""

    if not config.ELEVENLABS_API_KEY:
        raise HTTPException(status_code=500, detail="ELEVENLABS_API_KEY not configured")

    voice_id, voice_source = _resolve_voice_id(req.voice_id)
    logger.info("[audio-async] voice_id source: %s, configured: %s", voice_source, bool(voice_id))

    if not voice_id:
        raise HTTPException(
            status_code=400,
            detail="voice_id obrigatório. Configure ELEVENLABS_DEFAULT_VOICE_ID no Render ou envie voice_id no body.",
        )

    if not req.audio_blocks:
        raise HTTPException(status_code=400, detail="audio_blocks não pode ser vazio")

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": "pending",
        "blocks_total": len(req.audio_blocks),
        "blocks_completed": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "customer_name": req.customer_name or "cliente",
        "audio_generation_id": req.audio_generation_id or "",
    }

    logger.info("[audio-async] job %s created, blocks=%d, audio_generation_id=%s",
                job_id[:8], len(req.audio_blocks), req.audio_generation_id or "(none)")

    thread = threading.Thread(
        target=_generate_and_upload,
        args=(job_id, req, voice_id, voice_source),
        daemon=True,
    )
    thread.start()

    return {
        "job_id": job_id,
        "status": "pending",
        "blocks_total": len(req.audio_blocks),
        "message": "Geração de áudio iniciada. Consulte /audio-job-status/{job_id} para acompanhar.",
    }


@app.get("/audio-job-status/{job_id}")
def audio_job_status(job_id: str):
    """Consulta status de um job de geração de áudio."""

    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} não encontrado.")

    status = job["status"]
    # Normalizar: processing = pending ou generating
    if status in ("pending", "generating"):
        display_status = "processing"
    else:
        display_status = status

    response = {
        "job_id": job_id,
        "status": display_status,
        "audio_generation_id": job.get("audio_generation_id", ""),
        "blocks_total": job.get("blocks_total", 0),
        "blocks_completed": job.get("blocks_completed", 0),
        "created_at": job.get("created_at"),
    }

    if status == "completed":
        response.update({
            "uploaded": job.get("uploaded", False),
            "storage_path": job.get("storage_path", ""),
            "filename": job.get("filename", ""),
            "duration_seconds": job.get("duration_seconds"),
            "completed_at": job.get("completed_at"),
            "metadata": {
                "provider": "elevenlabs",
                "upload_mode": job.get("upload_mode", ""),
                "model": job.get("model", ""),
                "voice_id_source": job.get("voice_id_source", ""),
                "voice_id_prefix": job.get("voice_id_prefix", ""),
                "blocks_count": job.get("blocks_count", 0),
                "file_size_bytes": job.get("file_size_bytes", 0),
                "tts_speed": job.get("tts_speed", 1.03),
                "script_sanitized": job.get("script_sanitized", True),
                "pronoun_style": job.get("pronoun_style", "voce_seu_sua"),
            },
        })

    if status == "failed":
        response.update({
            "uploaded": False,
            "error": job.get("error", "Erro desconhecido"),
            "completed_at": job.get("completed_at"),
        })

    return response


# ── Endpoint síncrono (mantido para testes curtos) ──────────────────

@app.post("/generate-audio", response_model=GenerateAudioResponse)
def generate_audio_endpoint(req: GenerateAudioRequest):
    """Gera áudio MP3 síncrono. Use /generate-audio-async para áudios completos."""

    if not config.ELEVENLABS_API_KEY:
        raise HTTPException(status_code=500, detail="ELEVENLABS_API_KEY not configured")

    voice_id, voice_source = _resolve_voice_id(req.voice_id)
    logger.info("[audio] voice_id source: %s, configured: %s", voice_source, bool(voice_id))
    if voice_id:
        logger.info("[audio] voice_id prefix: %s", voice_id[:6])

    if not voice_id:
        raise HTTPException(
            status_code=400,
            detail="voice_id obrigatório. Configure ELEVENLABS_DEFAULT_VOICE_ID no Render ou envie voice_id no body.",
        )

    if not req.audio_blocks:
        raise HTTPException(status_code=400, detail="audio_blocks não pode ser vazio")

    audio_parts: list[bytes] = []
    for i, block in enumerate(req.audio_blocks):
        logger.info("Gerando áudio bloco %d/%d: %s", i + 1, len(req.audio_blocks), block.label)
        try:
            audio_bytes = generate_audio_block(
                text=block.text,
                voice_id=voice_id,
                model_id=req.model_id,
                stability=req.voice_settings.stability,
                similarity_boost=req.voice_settings.similarity_boost,
                style=req.voice_settings.style,
                use_speaker_boost=req.voice_settings.use_speaker_boost,
                speed=req.speed,
                block_label=block.label,
            )
            audio_parts.append(audio_bytes)
        except Exception as e:
            logger.exception("Erro no bloco %d (%s)", i + 1, block.label)
            raise HTTPException(
                status_code=502,
                detail=f"ElevenLabs falhou no bloco {i + 1} ({block.label}): {str(e)}",
            )

    logger.info("Concatenando %d blocos de áudio", len(audio_parts))
    try:
        final_audio = concatenate_mp3_blocks(audio_parts)
    except Exception as e:
        logger.exception("Erro na concatenação dos blocos")
        raise HTTPException(status_code=500, detail=f"Erro ao concatenar áudio: {str(e)}")

    duration_seconds = None
    try:
        from pydub import AudioSegment
        import io
        segment = AudioSegment.from_mp3(io.BytesIO(final_audio))
        duration_seconds = round(len(segment) / 1000, 1)
    except Exception:
        pass

    customer_name = req.customer_name or "cliente"
    filename = f"audio-ancorada-{_make_slug(customer_name)}.mp3"

    upload_mode = req.upload_mode or config.AUDIO_UPLOAD_MODE or "return_base64"
    logger.info("[audio] upload_mode=%s, file=%s, size=%d bytes, blocks=%d",
                upload_mode, filename, len(final_audio), len(req.audio_blocks))

    # signed_upload
    if upload_mode == "signed_upload":
        if not req.signed_upload or not req.signed_upload.signed_url:
            raise HTTPException(status_code=400, detail="signed_upload.signed_url é obrigatório no modo signed_upload.")

        signed = req.signed_upload
        _validate_signed_upload(signed)
        uploaded, upload_err = _do_signed_upload(
            signed, final_audio,
            audio_generation_id=req.audio_generation_id,
        )

        if not uploaded:
            raise HTTPException(
                status_code=502,
                detail=f"Upload para Supabase falhou: {upload_err}",
            )

        return GenerateAudioResponse(
            uploaded=True,
            storage_path=signed.path,
            filename=filename,
            mime_type="audio/mpeg",
            audio_status="audio_ready",
            duration_seconds=duration_seconds,
            metadata={
                "provider": "elevenlabs",
                "model": req.model_id,
                "voice_id_source": voice_source,
                "voice_id_prefix": voice_id[:6] if voice_id else "",
                "blocks_count": len(req.audio_blocks),
                "file_size_bytes": len(final_audio),
                "upload_mode": "signed_upload",
                "audio_generation_id": req.audio_generation_id,
                "tts_speed": req.speed,
                "script_sanitized": True,
                "pronoun_style": "voce_seu_sua",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    # return_base64 (default)
    audio_b64 = base64.b64encode(final_audio).decode("utf-8")

    return GenerateAudioResponse(
        audio_base64=audio_b64,
        filename=filename,
        mime_type="audio/mpeg",
        audio_status="audio_ready",
        duration_seconds=duration_seconds,
        metadata={
            "provider": "elevenlabs",
            "model": req.model_id,
            "voice_id_source": voice_source,
            "voice_id_prefix": voice_id[:6] if voice_id else "",
            "blocks_count": len(req.audio_blocks),
            "file_size_bytes": len(final_audio),
            "upload_mode": "return_base64",
            "tts_speed": req.speed,
            "script_sanitized": True,
            "pronoun_style": "voce_seu_sua",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
