/**
 * ANCORADA Audio API Service
 *
 * Chama a API separada no Render para gerar roteiro e áudio MP3.
 * A chave ElevenLabs fica SOMENTE no backend — nunca no frontend.
 *
 * Para usar no Lovable:
 * 1. Copiar este arquivo para src/services/audioApiService.ts
 * 2. Configurar ANCORADA_AUDIO_API_URL no .env ou inline abaixo
 */

const ANCORADA_AUDIO_API_URL =
  import.meta.env.VITE_ANCORADA_AUDIO_API_URL ||
  "https://ancorada-audio-api.onrender.com";

// ── Types ──────────────────────────────────────────────────────────

export interface AudioScriptRequest {
  customer: {
    full_name: string;
    email?: string;
  };
  diagnostic_text?: string;
  diagnostic_json?: Record<string, unknown>;
  birth_profile: {
    birth_date: string; // YYYY-MM-DD
    birth_time: string; // HH:MM
    birth_city: string;
    birth_state?: string;
    birth_country?: string;
  };
  chart_json?: Record<string, unknown>;
}

export interface AudioBlock {
  label: string;
  text: string;
}

export interface AudioScriptResponse {
  audio_script: string;
  audio_blocks: AudioBlock[];
  estimated_duration_minutes: number;
  metadata: Record<string, unknown>;
}

export interface VoiceSettings {
  stability?: number;
  similarity_boost?: number;
  style?: number;
  use_speaker_boost?: boolean;
}

export interface GenerateAudioRequest {
  audio_blocks: AudioBlock[];
  voice_id?: string;
  model_id?: string;
  voice_settings?: VoiceSettings;
  speed?: number;
  customer_name?: string;
}

export interface GenerateAudioResponse {
  audio_url: string;
  audio_status: string;
  duration_seconds: number | null;
  metadata: Record<string, unknown>;
}

// ── API Calls ──────────────────────────────────────────────────────

export async function generateAudioScript(
  data: AudioScriptRequest
): Promise<AudioScriptResponse> {
  const res = await fetch(`${ANCORADA_AUDIO_API_URL}/generate-audio-script`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `Erro ao gerar roteiro: ${res.status}`);
  }

  return res.json();
}

export async function generateAudio(
  data: GenerateAudioRequest
): Promise<GenerateAudioResponse> {
  const res = await fetch(`${ANCORADA_AUDIO_API_URL}/generate-audio`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `Erro ao gerar áudio: ${res.status}`);
  }

  return res.json();
}

// ── Fluxo completo (roteiro + áudio) ───────────────────────────────

export async function generateFullAudio(
  scriptRequest: AudioScriptRequest,
  voiceSettings?: Partial<GenerateAudioRequest>
): Promise<{
  script: AudioScriptResponse;
  audio: GenerateAudioResponse;
}> {
  // 1. Gerar roteiro via Claude
  const script = await generateAudioScript(scriptRequest);

  // 2. Gerar MP3 via ElevenLabs (no backend)
  const audio = await generateAudio({
    audio_blocks: script.audio_blocks,
    customer_name: scriptRequest.customer.full_name,
    ...voiceSettings,
  });

  return { script, audio };
}
