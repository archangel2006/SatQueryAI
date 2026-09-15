export type ImageMetadata = {
  width: number
  height: number
  band_count: number
  crs: string | null
  bounds: number[] | null
  modality_guess: 'optical' | 'sar' | 'unknown'
  format_kind: 'geotiff' | 'raster'
  filename: string
}

export type PreviewResponse = {
  preview_png_base64: string
  metadata: ImageMetadata
}

export type FusionResponse = {
  text: string
  overlay_png_base64: string | null
  cloud_pct: number | null
  score: number | null
  evidence: Record<string, unknown>
}

export type ChangeResponse = {
  text: string
  overlay_png_base64: string | null
  score: number | null
  change_pct: number | null
  analysis_id: string
  evidence: Record<string, unknown>
}


export type Analysis = {
  id: string
  session_id: string
  before_asset_id: string | null
  after_asset_id: string | null
  analysis_text: string
  change_pct: number | null
  score: number | null
  method: string | null
  evidence: Record<string, unknown>
  overlay_gcs_uri: string | null
  created_at: string
}

export type SessionListItem = {
  id: string
  title: string
  job_type: string
  created_at: string
  updated_at: string
}

export type AssetOut = {
  id: string
  filename: string
  content_type: string
  gcs_uri: string
  preview_gcs_uri: string
  metadata: ImageMetadata
  preview_png_base64: string | null
  created_at: string
}

export type SessionOut = SessionListItem & {
  assets: AssetOut[]
}

export type MessageAttachmentOut = {
  id: string
  filename: string
  preview_png_base64: string | null
}

export type MessageOut = {
  id: string
  role: string
  content: string
  asset_id: string | null
  attachment: MessageAttachmentOut | null
  created_at: string
}

export type SendMessageResponse = {
  user_message: MessageOut
  assistant_message: MessageOut
}

export type UploadAssetResponse = {
  asset: AssetOut
  user_message: MessageOut
  assistant_message: MessageOut
}

export async function getSessionAnalyses(
  getToken: TokenFn,
  sessionId: string,
): Promise<Analysis[]> {
  const headers = await authHeaders(getToken)

  const res = await fetch(
    `${API_URL}/sessions/${sessionId}/analyses`,
    {
      method: 'GET',
      headers,
    },
  )

  if (!res.ok) {
    throw new Error(
      await readError(res, 'Could not load analyses'),
    )
  }

  return (await res.json()) as Analysis[]
}


export type Report = {
  id: string
  session_id: string
  analysis_id: string
  title: string
  pdf_gcs_uri: string
  created_at: string
}


const API_URL =
  (import.meta.env.VITE_API_URL as string | undefined) ??
  'http://127.0.0.1:8000'

type TokenFn = () => Promise<string | null>

async function authHeaders(getToken: TokenFn): Promise<HeadersInit> {
  const token = await getToken()
  if (!token) throw new Error('Not signed in')
  return { Authorization: `Bearer ${token}` }
}

async function readError(res: Response, fallback: string): Promise<string> {
  try {
    const err = (await res.json()) as { detail?: string | unknown }
    if (typeof err.detail === 'string') return err.detail
  } catch {
    /* ignore */
  }
  return fallback
}

export async function postPreview(file: File): Promise<PreviewResponse> {
  const body = new FormData()
  body.append('file', file)
  const res = await fetch(`${API_URL}/preview`, {
    method: 'POST',
    body,
  })
  if (!res.ok) throw new Error(await readError(res, 'Preview failed'))
  return (await res.json()) as PreviewResponse
}

export async function postFusion(
  optical: File,
  sar: File,
  query?: string,
): Promise<FusionResponse> {
  const body = new FormData()
  body.append('files', optical)
  body.append('files', sar)
  if (query?.trim()) body.append('query', query.trim())
  const res = await fetch(`${API_URL}/fusion`, {
    method: 'POST',
    body,
  })
  if (!res.ok) throw new Error(await readError(res, 'Fusion failed'))
  return (await res.json()) as FusionResponse
}

export async function postChange(
  getToken: TokenFn,
  before: File | Blob,
  after: File | Blob,
  sessionId: string,
  query?: string,
  beforeAssetId?: string,
  afterAssetId?: string,
): Promise<ChangeResponse> {
  const body = new FormData()

  body.append('files', before)
  body.append('files', after)
  body.append('session_id', sessionId)

  if (query?.trim()) {
    body.append('query', query.trim())
  }

  if (beforeAssetId) {
    body.append('before_asset_id', beforeAssetId)
  }

  if (afterAssetId) {
    body.append('after_asset_id', afterAssetId)
  }

  const headers = await authHeaders(getToken)

  const res = await fetch(`${API_URL}/change`, {
    method: 'POST',
    headers,
    body,
  })

  if (!res.ok) {
    throw new Error(await readError(res, 'Change detection failed'))
  }

  return (await res.json()) as ChangeResponse
}


export function previewToObjectUrl(base64: string): string {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
  const blob = new Blob([bytes], { type: 'image/png' })
  return URL.createObjectURL(blob)
}

export async function createSession(
  getToken: TokenFn,
  title = 'New chat',
  jobType = 'ask_scene',
): Promise<SessionOut> {
  const res = await fetch(`${API_URL}/sessions`, {
    method: 'POST',
    headers: {
      ...(await authHeaders(getToken)),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ title, job_type: jobType }),
  })
  if (!res.ok) throw new Error(await readError(res, 'Could not create chat'))
  return (await res.json()) as SessionOut
}

export async function listSessions(getToken: TokenFn): Promise<SessionListItem[]> {
  const res = await fetch(`${API_URL}/sessions`, {
    headers: await authHeaders(getToken),
  })
  if (!res.ok) throw new Error(await readError(res, 'Could not load chats'))
  return (await res.json()) as SessionListItem[]
}

export async function getSession(
  getToken: TokenFn,
  sessionId: string,
): Promise<SessionOut> {
  const res = await fetch(`${API_URL}/sessions/${sessionId}`, {
    headers: await authHeaders(getToken),
  })
  if (!res.ok) throw new Error(await readError(res, 'Could not load chat'))
  return (await res.json()) as SessionOut
}

export async function renameSession(
  getToken: TokenFn,
  sessionId: string,
  title: string,
): Promise<SessionListItem> {
  const res = await fetch(`${API_URL}/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: {
      ...(await authHeaders(getToken)),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ title }),
  })
  if (!res.ok) throw new Error(await readError(res, 'Could not rename chat'))
  return (await res.json()) as SessionListItem
}

export async function deleteSession(
  getToken: TokenFn,
  sessionId: string,
): Promise<void> {
  const res = await fetch(`${API_URL}/sessions/${sessionId}`, {
    method: 'DELETE',
    headers: await authHeaders(getToken),
  })
  if (!res.ok) throw new Error(await readError(res, 'Could not delete chat'))
}

export async function getMessages(
  getToken: TokenFn,
  sessionId: string,
): Promise<MessageOut[]> {
  const res = await fetch(`${API_URL}/sessions/${sessionId}/messages`, {
    headers: await authHeaders(getToken),
  })
  if (!res.ok) throw new Error(await readError(res, 'Could not load messages'))
  return (await res.json()) as MessageOut[]
}

export async function uploadSessionAsset(
  getToken: TokenFn,
  sessionId: string,
  file: File,
  message?: string,
): Promise<UploadAssetResponse> {
  const body = new FormData()
  body.append('file', file)
  if (message?.trim()) body.append('message', message.trim())
  const res = await fetch(`${API_URL}/sessions/${sessionId}/assets`, {
    method: 'POST',
    headers: await authHeaders(getToken),
    body,
  })
  if (!res.ok) throw new Error(await readError(res, 'Upload failed'))
  return (await res.json()) as UploadAssetResponse
}

export async function sendSessionMessage(
  getToken: TokenFn,
  sessionId: string,
  content: string,
): Promise<SendMessageResponse> {
  const res = await fetch(`${API_URL}/sessions/${sessionId}/messages`, {
    method: 'POST',
    headers: {
      ...(await authHeaders(getToken)),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ content }),
  })
  if (!res.ok) throw new Error(await readError(res, 'Send failed'))
  return (await res.json()) as SendMessageResponse
}


export async function generateAnalysisReport(
  getToken: TokenFn,
  sessionId: string,
  analysisId: string,
): Promise<Report> {
  const headers = await authHeaders(getToken)

  const res = await fetch(
    `${API_URL}/sessions/${sessionId}/analyses/${analysisId}/report`,
    {
      method: 'POST',
      headers,
    },
  )

  if (!res.ok) {
    throw new Error(
      await readError(res, 'Could not generate report'),
    )
  }

  return (await res.json()) as Report
}


export async function getSessionReports(
  getToken: TokenFn,
  sessionId: string,
): Promise<Report[]> {
  const headers = await authHeaders(getToken)

  const res = await fetch(
    `${API_URL}/sessions/${sessionId}/reports`,
    {
      method: 'GET',
      headers,
    },
  )

  if (!res.ok) {
    throw new Error(
      await readError(res, 'Could not load reports'),
    )
  }

  return (await res.json()) as Report[]
}


export async function downloadReport(
  getToken: TokenFn,
  sessionId: string,
  reportId: string,
): Promise<Blob> {
  const headers = await authHeaders(getToken)

  const res = await fetch(
    `${API_URL}/sessions/${sessionId}/reports/${reportId}/download`,
    {
      method: 'GET',
      headers,
    },
  )

  if (!res.ok) {
    throw new Error(await readError(res, 'Could not download report'))
  }

  return await res.blob()
}