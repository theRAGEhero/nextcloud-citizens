/*
 * Recording engine: one MediaRecorder session, periodic chunks written to
 * IndexedDB FIRST, then uploaded asynchronously with acknowledgment tracking.
 * The network is never required to preserve audio (brief §17).
 */

import { reactive } from 'vue'
import { recorderApi } from './api'
import { idb } from './idb'
import { sha256Hex } from './sha'

export const CHUNK_INTERVAL_MS = 10_000
const UPLOAD_RETRY_MS = 3_000

const MIME_CANDIDATES = [
	'audio/webm;codecs=opus',
	'audio/webm',
	'audio/ogg;codecs=opus',
	'audio/mp4',
]

export function pickMimeType(): string | null {
	if (typeof MediaRecorder === 'undefined') return null
	for (const candidate of MIME_CANDIDATES) {
		if (MediaRecorder.isTypeSupported(candidate)) return candidate
	}
	return null
}

export interface EngineState {
	phase: 'idle' | 'recording' | 'finishing' | 'syncing' | 'done' | 'failed'
	recordingId: string
	startedAt: number
	localChunks: number
	ackedChunks: number
	storageError: boolean
	uploadOnline: boolean
	serverState: string
	error: string
}

export class RecorderEngine {
	state: EngineState = reactive({
		phase: 'idle',
		recordingId: '',
		startedAt: 0,
		localChunks: 0,
		ackedChunks: 0,
		storageError: false,
		uploadOnline: true,
		serverState: '',
		error: '',
	})

	private token = ''
	private stream: MediaStream | null = null
	private mediaRecorder: MediaRecorder | null = null
	private seq = 0
	private totalChunks: number | null = null
	// serializes async chunk persistence so sequence order matches event order
	private chunkPipeline: Promise<void> = Promise.resolve()
	private uploaderActive = false
	private stopRequested = false

	async start(token: string, roundId: string): Promise<void> {
		this.token = token
		const mimeType = pickMimeType()
		if (!mimeType) throw new Error('This browser cannot record audio (no supported format)')

		this.stream = await navigator.mediaDevices.getUserMedia({
			audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: true },
		})
		const started = await recorderApi.start(token, roundId, mimeType)
		this.state.recordingId = started.recording_id
		this.state.startedAt = Date.now()
		this.state.phase = 'recording'

		await idb.putRecording({
			recordingId: started.recording_id,
			roundId,
			tableNumber: 0,
			mimeType,
			startedAt: this.state.startedAt,
			finishedAt: null,
			totalChunks: null,
			serverComplete: false,
		})

		this.mediaRecorder = new MediaRecorder(this.stream, { mimeType })
		this.mediaRecorder.ondataavailable = (event: BlobEvent) => {
			if (event.data && event.data.size > 0) this.enqueueChunk(event.data)
		}
		this.mediaRecorder.start(CHUNK_INTERVAL_MS)
		this.runUploader()
	}

	get mediaStream(): MediaStream | null {
		return this.stream
	}

	private enqueueChunk(blob: Blob): void {
		const seq = this.seq
		this.seq += 1
		this.chunkPipeline = this.chunkPipeline
			.then(async () => {
				const buffer = await blob.arrayBuffer()
				const sha256 = await sha256Hex(buffer)
				await idb.putChunk({
					key: `${this.state.recordingId}:${seq}`,
					recordingId: this.state.recordingId,
					seq,
					blob,
					sha256,
					sizeBytes: blob.size,
					createdAt: Date.now(),
					acked: false,
					attempts: 0,
				})
				this.state.localChunks += 1
			})
			.catch((error) => {
				// Local persistence failure is the HIGHEST severity problem (brief §22)
				this.state.storageError = true
				this.state.error = `Local storage error: ${error}`
			})
	}

	private async runUploader(): Promise<void> {
		if (this.uploaderActive) return
		this.uploaderActive = true
		try {
			for (;;) {
				const pending = (await idb.chunksFor(this.state.recordingId)).filter((c) => !c.acked)
				if (pending.length === 0) {
					if (this.totalChunks !== null) break // finished and everything acked
					if (this.state.phase !== 'recording' && this.state.phase !== 'finishing') break
					await sleep(1000)
					continue
				}
				const chunk = pending[0]
				try {
					await recorderApi.uploadChunk(
						this.token, this.state.recordingId, chunk.seq, chunk.blob, chunk.sha256,
					)
					chunk.acked = true
					chunk.attempts += 1
					await idb.putChunk(chunk)
					this.state.ackedChunks += 1
					this.state.uploadOnline = true
				} catch (error) {
					this.state.uploadOnline = false
					chunk.attempts += 1
					await idb.putChunk(chunk)
					await sleep(UPLOAD_RETRY_MS)
				}
			}
			if (this.totalChunks !== null) await this.sendComplete()
		} finally {
			this.uploaderActive = false
		}
	}

	async finish(): Promise<void> {
		if (!this.mediaRecorder || this.stopRequested) return
		this.stopRequested = true
		this.state.phase = 'finishing'

		await new Promise<void>((resolve) => {
			this.mediaRecorder!.onstop = () => resolve()
			this.mediaRecorder!.stop()
		})
		this.stream?.getTracks().forEach((track) => track.stop())

		// wait until the final dataavailable chunk is persisted
		await this.chunkPipeline
		this.totalChunks = this.seq
		this.state.phase = 'syncing'

		const recordings = await idb.getRecordings()
		const meta = recordings.find((r) => r.recordingId === this.state.recordingId)
		if (meta) {
			meta.finishedAt = Date.now()
			meta.totalChunks = this.totalChunks
			await idb.putRecording(meta)
		}
		this.runUploader()
	}

	private async sendComplete(): Promise<void> {
		if (this.totalChunks === null || this.totalChunks === 0) {
			this.state.phase = 'failed'
			this.state.error = 'No audio was captured'
			return
		}
		try {
			let result = await recorderApi.complete(this.token, this.state.recordingId, this.totalChunks)
			// server-detected gaps: resend those chunks from local storage, then retry
			while (result.missing_sequences.length > 0) {
				const chunks = await idb.chunksFor(this.state.recordingId)
				for (const seqNumber of result.missing_sequences) {
					const chunk = chunks.find((c) => c.seq === seqNumber)
					if (!chunk) throw new Error(`Chunk ${seqNumber} is missing locally too`)
					await recorderApi.uploadChunk(
						this.token, this.state.recordingId, chunk.seq, chunk.blob, chunk.sha256,
					)
				}
				result = await recorderApi.complete(this.token, this.state.recordingId, this.totalChunks)
			}
			await this.pollUntilProcessed()
		} catch (error) {
			this.state.error = error instanceof Error ? error.message : String(error)
			this.state.phase = 'failed'
		}
	}

	private async pollUntilProcessed(): Promise<void> {
		for (let i = 0; i < 120; i += 1) {
			const status = await recorderApi.recordingStatus(this.token, this.state.recordingId)
			this.state.serverState = status.state
			if (status.state === 'AUDIO_READY' || status.state === 'AUDIO_INVALID') {
				this.state.phase = status.state === 'AUDIO_READY' ? 'done' : 'failed'
				if (status.state === 'AUDIO_INVALID') {
					this.state.error = `Server could not validate the audio (${status.error_code})`
				}
				return
			}
			await sleep(2000)
		}
		// server still busy — audio is safe server-side; report as done-with-note
		this.state.phase = 'done'
	}
}

function sleep(ms: number): Promise<void> {
	return new Promise((resolve) => setTimeout(resolve, ms))
}
