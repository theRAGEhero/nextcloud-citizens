<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { recorderApi, type JoinResult, type RoundInfo } from '../api'
import { clearSynchronizedRecordings, RecorderEngine } from '../engine'

const props = defineProps<{ session: JoinResult; round: RoundInfo }>()
const emit = defineEmits<{ exit: [] }>()

const engine = new RecorderEngine()
const state = engine.state
const now = ref(Date.now())
const confirmFinish = ref(false)
const level = ref(0)
const startError = ref('')
const roundEnded = ref(false)
const clearedNote = ref('')
const showLive = ref(false)
const liveLines = ref<Array<{ t: number; text: string }>>([])
const liveChecked = ref(false)

let clockTimer = 0
let levelTimer = 0
let roundPollTimer = 0
let livePollTimer = 0
let audioContext: AudioContext | null = null
let wakeLock: WakeLockSentinel | null = null

const elapsed = computed(() => {
	if (!state.startedAt) return '00:00'
	const seconds = Math.max(0, Math.floor((now.value - state.startedAt) / 1000))
	const minutes = Math.floor(seconds / 60)
	return `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
})

const pendingChunks = computed(() => state.localChunks - state.ackedChunks)

onMounted(async () => {
	clockTimer = window.setInterval(() => (now.value = Date.now()), 500)
	try {
		await engine.start(props.session.session_token, props.round.id)
	} catch (error) {
		startError.value = error instanceof Error ? error.message : String(error)
		return
	}
	// level meter on the recording stream
	const stream = engine.mediaStream
	if (stream) {
		audioContext = new AudioContext()
		const analyser = audioContext.createAnalyser()
		analyser.fftSize = 512
		audioContext.createMediaStreamSource(stream).connect(analyser)
		const samples = new Uint8Array(analyser.fftSize)
		levelTimer = window.setInterval(() => {
			analyser.getByteTimeDomainData(samples)
			let peak = 0
			for (const value of samples) peak = Math.max(peak, Math.abs(value - 128))
			level.value = Math.min(100, Math.round((peak / 128) * 160))
		}, 120)
	}
	// keep the screen on where supported (brief §21)
	try {
		wakeLock = (await navigator.wakeLock?.request('screen')) ?? null
		document.addEventListener('visibilitychange', reacquireWakeLock)
	} catch {
		/* not supported — the UI warns to keep the page open */
	}
	// notice when the facilitator ends the round (brief §26)
	roundPollTimer = window.setInterval(async () => {
		if (state.phase !== 'recording') return
		try {
			const status = await recorderApi.status(props.session.session_token)
			const current = status.rounds.find((r) => r.id === props.round.id)
			if (current && current.status === 'ENDED') roundEnded.value = true
		} catch {
			/* offline — round state resumes with the network */
		}
	}, 10_000)
})

async function reacquireWakeLock(): Promise<void> {
	if (document.visibilityState === 'visible' && state.phase === 'recording') {
		try {
			wakeLock = (await navigator.wakeLock?.request('screen')) ?? null
		} catch {
			/* ignore */
		}
	}
}

function toggleLive(): void {
	showLive.value = !showLive.value
	if (showLive.value && !livePollTimer) {
		const poll = async () => {
			if (!state.recordingId || state.phase !== 'recording') return
			try {
				const result = await recorderApi.liveTranscript(props.session.session_token, state.recordingId)
				liveLines.value = result.lines.slice(-8)
				liveChecked.value = true
			} catch {
				/* captions are best-effort */
			}
		}
		void poll()
		livePollTimer = window.setInterval(() => void poll(), 6000)
	}
}

onBeforeUnmount(() => {
	window.clearInterval(clockTimer)
	window.clearInterval(levelTimer)
	window.clearInterval(roundPollTimer)
	window.clearInterval(livePollTimer)
	audioContext?.close()
	wakeLock?.release().catch(() => undefined)
	document.removeEventListener('visibilitychange', reacquireWakeLock)
})

async function finishRecording(): Promise<void> {
	confirmFinish.value = false
	roundEnded.value = false
	await engine.finish()
}

async function clearSynced(): Promise<void> {
	const cleared = await clearSynchronizedRecordings()
	clearedNote.value = `${cleared} synchronized recording(s) removed from this phone.`
}
</script>

<template>
	<div>
		<div class="rc-header">
			<span class="rc-table-badge">TABLE {{ session.table_number }}</span>
			<span v-if="state.phase === 'recording'" class="rc-live">RECORDING</span>
		</div>

		<div v-if="startError" class="rc-alert">
			Could not start recording: {{ startError }}
			<button class="rc-btn" style="margin-top: 12px" @click="emit('exit')">Back</button>
		</div>

		<template v-else-if="state.phase === 'recording' || state.phase === 'finishing'">
			<div class="rc-card">
				<p class="rc-muted">Round {{ round.position }} of {{ session.rounds.length }}</p>
				<p class="rc-question">{{ round.question || round.title }}</p>
			</div>

			<div class="rc-timer">{{ elapsed }}</div>
			<div class="rc-level"><div class="rc-level-fill" :style="{ width: level + '%' }"></div></div>

			<div class="rc-card">
				<div class="rc-status-row">
					<span>Local audio</span>
					<span :class="state.storageError ? 'rc-bad' : 'rc-ok'">
						{{ state.storageError ? '✕ STORAGE ERROR' : '✓ SAFE' }}
					</span>
				</div>
				<div class="rc-status-row">
					<span>Server upload</span>
					<span :class="state.uploadOnline ? 'rc-ok' : 'rc-warn'">
						{{ state.uploadOnline ? '✓' : 'OFFLINE' }}
					</span>
				</div>
				<div class="rc-status-row">
					<span>Pending upload</span>
					<span :class="pendingChunks > 3 ? 'rc-warn' : ''">{{ pendingChunks }} chunks</span>
				</div>
			</div>

			<div v-if="state.storageError" class="rc-alert">
				<strong>LOCAL STORAGE ERROR</strong><br />
				Recording can no longer be safely stored. Please notify the facilitator immediately.
			</div>
			<div v-else-if="!state.uploadOnline" class="rc-note">
				Network unavailable — the recording continues safely on this phone and will upload when
				the connection returns. Keep this page open.
				<button class="rc-btn" style="margin-top: 10px" @click="engine.retryNow()">Retry upload now</button>
			</div>
			<p v-else class="rc-muted rc-center">Keep this page open while the table is recording.</p>

			<div v-if="state.lowStorage" class="rc-alert">
				Phone storage is getting low. Notify the facilitator after this round.
			</div>

			<div v-if="roundEnded && state.phase === 'recording'" class="rc-note">
				<strong>The round has ended.</strong> Finish recording?
				<button class="rc-btn rc-primary" style="margin-top: 10px" @click="finishRecording">
					Finish and synchronize
				</button>
			</div>

			<template v-if="state.phase === 'recording'">
				<button class="rc-btn rc-subtle" @click="toggleLive">
					{{ showLive ? 'Hide live transcript' : 'Show live transcript' }}
				</button>
				<div v-if="showLive" class="rc-card">
					<p class="rc-muted" style="margin: 0 0 8px; font-size: 12px; letter-spacing: 0.05em">
						LIVE TRANSCRIPT — PROVISIONAL
					</p>
					<p v-if="liveLines.length === 0" class="rc-muted" style="font-size: 14px">
						{{ liveChecked ? 'Live captions temporarily unavailable. Recording continues safely.' : 'Waiting for captions…' }}
					</p>
					<p v-for="(line, index) in liveLines" :key="index" style="font-size: 15px; margin: 6px 0">
						{{ line.text }}
					</p>
				</div>

				<button v-if="!confirmFinish" class="rc-btn" @click="confirmFinish = true">
					Finish recording
				</button>
				<template v-else>
					<div class="rc-note">Finish and synchronize this table's recording?</div>
					<button class="rc-btn rc-primary" @click="finishRecording">Yes, finish and synchronize</button>
					<button class="rc-btn rc-subtle" @click="confirmFinish = false">Keep recording</button>
				</template>
			</template>
			<p v-else class="rc-muted rc-center">Stopping…</p>
		</template>

		<template v-else-if="state.phase === 'syncing'">
			<div class="rc-center" style="padding-top: 40px">
				<div class="rc-big-icon">📤</div>
				<h1>Synchronizing</h1>
				<p class="rc-muted" style="margin-top: 10px">
					{{ state.ackedChunks }} / {{ state.localChunks }} chunks uploaded
					<template v-if="state.serverState"><br />Server: {{ state.serverState }}</template>
				</p>
				<div v-if="!state.uploadOnline" class="rc-note" style="text-align: left">
					Waiting for network… the audio is safe on this phone. Keep this page open.
				</div>
			</div>
		</template>

		<template v-else-if="state.phase === 'done'">
			<div class="rc-center" style="padding-top: 40px">
				<div class="rc-big-icon">✅</div>
				<h1>Recording synchronized</h1>
				<p class="rc-muted" style="margin-top: 10px">
					The table recording was uploaded and validated by the server.
				</p>
				<p v-if="clearedNote" class="rc-muted">{{ clearedNote }}</p>
				<button class="rc-btn" style="margin-top: 24px" @click="emit('exit')">Back to start</button>
				<button v-if="!clearedNote" class="rc-btn rc-subtle" @click="clearSynced">
					Clear synchronized audio from this phone
				</button>
			</div>
		</template>

		<template v-else-if="state.phase === 'failed'">
			<div class="rc-alert" style="margin-top: 30px">
				<strong>Something went wrong:</strong><br />{{ state.error }}
				<br /><br />
				Local audio chunks remain stored on this phone.
			</div>
			<button class="rc-btn" @click="emit('exit')">Back</button>
		</template>
	</div>
</template>
