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
    full_name?: string;
    name?: string;
    email?: string;
  };
  diagnostic_text?: string;
  diagnostic_json?: unknown;
  diagnostic_id?: string;
  diagnostic_pdf_url?: string;
  product?: string;
  birth_profile?: {
    birth_date: string;
    birth_time: string;
    birth_city: string;
    birth_state?: string;
    birth_country?: string;
  };
  chart_json?: unknown;
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

export interface SignedUpload {
  bucket: string;
  path: string;
  signed_url: string;
  token?: string;
}

export interface GenerateAudioRequest {
  audio_blocks: AudioBlock[];
  voice_id?: string;
  model_id?: string;
  voice_settings?: VoiceSettings;
  speed?: number;
  customer_name?: string;
  upload_mode?: "return_base64" | "signed_upload";
  signed_upload?: SignedUpload;
}

export interface GenerateAudioResponse {
  audio_base64: string;
  audio_url: string;
  uploaded: boolean | null;
  storage_path: string;
  filename: string;
  mime_type: string;
  audio_status: string;
  duration_seconds: number | null;
  metadata: Record<string, unknown>;
}

export interface AsyncJobResponse {
  job_id: string;
  status: "pending" | "generating" | "completed" | "completed_no_upload" | "failed";
  blocks_total: number;
  blocks_completed: number;
  message?: string;
}

export interface JobStatusResponse {
  job_id: string;
  status: "pending" | "generating" | "completed" | "completed_no_upload" | "failed";
  blocks_total: number;
  blocks_completed: number;
  created_at: string;
  uploaded?: boolean;
  storage_path?: string;
  filename?: string;
  duration_seconds?: number | null;
  completed_at?: string;
  error?: string;
  metadata?: Record<string, unknown>;
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

/** Gera áudio síncrono (apenas para testes curtos). */
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

/** Inicia geração de áudio em background. Retorna job_id imediatamente. */
export async function generateAudioAsync(
  data: GenerateAudioRequest
): Promise<AsyncJobResponse> {
  const res = await fetch(`${ANCORADA_AUDIO_API_URL}/generate-audio-async`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `Erro ao iniciar geração: ${res.status}`);
  }

  return res.json();
}

/** Consulta status de um job de geração de áudio. */
export async function getAudioJobStatus(
  jobId: string
): Promise<JobStatusResponse> {
  const res = await fetch(`${ANCORADA_AUDIO_API_URL}/audio-job-status/${jobId}`);

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `Erro ao consultar job: ${res.status}`);
  }

  return res.json();
}

// ── Fluxo completo assíncrono (recomendado para áudio completo) ───

export async function generateFullAudioAsync(
  scriptRequest: AudioScriptRequest,
  signedUpload: SignedUpload,
  voiceSettings?: Partial<GenerateAudioRequest>
): Promise<{
  script: AudioScriptResponse;
  job: AsyncJobResponse;
}> {
  // 1. Gerar roteiro via Claude (síncrono, ~30s)
  const script = await generateAudioScript(scriptRequest);

  // 2. Iniciar geração de áudio em background (retorna imediatamente)
  const job = await generateAudioAsync({
    audio_blocks: script.audio_blocks,
    customer_name: scriptRequest.customer.full_name || scriptRequest.customer.name || "",
    upload_mode: "signed_upload",
    signed_upload: signedUpload,
    ...voiceSettings,
  });

  return { script, job };
}

/**
 * Poll até o job completar ou falhar.
 * Retorna o status final.
 */
export async function pollAudioJob(
  jobId: string,
  intervalMs = 5000,
  maxAttempts = 60,
  onProgress?: (status: JobStatusResponse) => void
): Promise<JobStatusResponse> {
  for (let i = 0; i < maxAttempts; i++) {
    const status = await getAudioJobStatus(jobId);

    if (onProgress) onProgress(status);

    if (status.status === "completed" || status.status === "completed_no_upload") {
      return status;
    }
    if (status.status === "failed") {
      throw new Error(status.error || "Geração de áudio falhou.");
    }

    await new Promise((r) => setTimeout(r, intervalMs));
  }

  throw new Error("Timeout: geração de áudio demorou mais que o esperado.");
}
