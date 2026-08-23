<script setup lang="ts">
import {
	mdiBroadcast,
	mdiCheckCircle,
	mdiCloudUploadOutline,
	mdiDatabaseOutline,
	mdiTrayFull,
} from '@mdi/js'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import SvgIcon from '../../components/ui/SvgIcon.vue'
import { recorderApi, type JoinResult, type RoundInfo } from '../api'
import { clearSynchronizedRecordings, RecorderEngine } from '../engine'

const props = defineProps<{ session: JoinResult; round: RoundInfo }>()
const emit = defineEmits<{ exit: []; nextRound: [round: RoundInfo] }>()

const engine = new RecorderEngine()
const state = engine.state
const now = ref(Date.now())
const confirmFinish = ref(false)
const level = ref(0)
const startError = ref('')
const roundEnded = ref(false)
const finishCountdown = ref(0)
const keepTalking = ref(false)
const nextStartCountdown = ref(0)
const clearedNote = ref('')

const orchestrated = props.session.assembly.recording_mode === 'orchestrated'

let countdownTimer = 0
let nextStartTimer = 0

// orchestrated: the facilitator ended the round → auto-finish after a short
// cancellable countdown so a last sentence can be completed
function beginFinishCountdown(): void {
	if (countdownTimer || keepTalking.value) return
	finishCountdown.value = 15
	countdownTimer = window.setInterval(() => {
		finishCountdown.value -= 1
		if (finishCountdown.value <= 0) {
			window.clearInterval(countdownTimer)
			countdownTimer = 0
			void finishRecording()
		}
	}, 1000)
}

function cancelFinishCountdown(): void {
	window.clearInterval(countdownTimer)
	countdownTimer = 0
	finishCountdown.value = 0
	keepTalking.value = true
}
const showLive = ref(true)
const liveLines = ref<Array<{ t: number; text: string; speaker?: number | null }>>([])
const liveChecked = ref(false)
const captionsBox = ref<HTMLElement | null>(null)
const nextRound = ref<RoundInfo | null>(null)
const qbarOpen = ref(false)
const techOpen = ref(false)

// consecutive caption fragments from the same speaker flow together as one
// block; a new block starts when the speaker changes
const captionBlocks = computed(() => {
	const blocks: Array<{ speaker: number | null; text: string }> = []
	for (const line of liveLines.value) {
		const speaker = line.speaker ?? null
		const last = blocks[blocks.length - 1]
		if (last && last.speaker === speaker) last.text += ' ' + line.text
		else blocks.push({ speaker, text: line.text })
	}
	return blocks
})

let nextRoundTimer = 0

// After finishing, the device is locked: it only offers the next un-recorded
// round once the facilitator activates it (no accidental re-recordings).
function watchForNextRound(): void {
	if (nextRoundTimer) return
	const poll = async () => {
		try {
			const status = await recorderApi.status(props.session.session_token)
			nextRound.value =
				status.rounds.find((r) => r.status === 'ACTIVE' && !r.recorded_state && r.id !== props.round.id) ??
				null
			// orchestrated: the armed table auto-starts the next round after a
			// short visible countdown (consent was given when arming)
			if (orchestrated && nextRound.value && !nextStartTimer) {
				nextStartCountdown.value = 3
				nextStartTimer = window.setInterval(() => {
					nextStartCountdown.value -= 1
					if (nextStartCountdown.value <= 0 && nextRound.value) {
						window.clearInterval(nextStartTimer)
						nextStartTimer = 0
						emit('nextRound', nextRound.value)
					}
				}, 1000)
			}
		} catch {
			/* offline — retried on next tick */
		}
	}
	void poll()
	nextRoundTimer = window.setInterval(() => void poll(), 10_000)
}

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

watch(liveLines, () => {
	void nextTick(() => {
		captionsBox.value?.scrollTo({ top: captionsBox.value.scrollHeight })
	})
})

watch(
	() => state.phase,
	(phase) => {
		if (phase === 'done') watchForNextRound()
	},
)

onMounted(async () => {
	clockTimer = window.setInterval(() => (now.value = Date.now()), 500)
	try {
		await engine.start(props.session.session_token, props.round.id)
	} catch (error) {
		startError.value = error instanceof Error ? error.message : String(error)
		return
	}
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
	try {
		wakeLock = (await navigator.wakeLock?.request('screen')) ?? null
		document.addEventListener('visibilitychange', reacquireWakeLock)
	} catch {
		/* not supported — the UI warns to keep the page open */
	}
	roundPollTimer = window.setInterval(async () => {
		if (state.phase !== 'recording') return
		try {
			const status = await recorderApi.status(props.session.session_token)
			const current = status.rounds.find((r) => r.id === props.round.id)
			if (current && current.status === 'ENDED') {
				roundEnded.value = true
				if (orchestrated) beginFinishCountdown()
			}
		} catch {
			/* offline — round state resumes with the network */
		}
	}, 5000)
	startLivePoll()
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

onBeforeUnmount(() => {
	window.clearInterval(clockTimer)
	window.clearInterval(levelTimer)
	window.clearInterval(roundPollTimer)
	window.clearInterval(livePollTimer)
	window.clearInterval(nextRoundTimer)
	window.clearInterval(countdownTimer)
	window.clearInterval(nextStartTimer)
	audioContext?.close()
	wakeLock?.release().catch(() => undefined)
	document.removeEventListener('visibilitychange', reacquireWakeLock)
})

function startLivePoll(): void {
	if (livePollTimer) return
	const poll = async () => {
		if (!showLive.value || !state.recordingId || state.phase !== 'recording') return
		try {
			const result = await recorderApi.liveTranscript(props.session.session_token, state.recordingId)
			liveLines.value = result.lines.slice(-40)
			liveChecked.value = true
		} catch {
			/* captions are best-effort */
		}
	}
	void poll()
	livePollTimer = window.setInterval(() => void poll(), 6000)
}

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
	<div class="rc-fill">
		<div class="rc-header">
			<span class="rc-table-badge">TABLE {{ session.table_number }}</span>
			<span v-if="state.phase === 'recording'" class="rc-live">RECORDING</span>
		</div>

		<div v-if="startError" class="rc-scroll">
			<div class="rc-alert">
				Could not start recording: {{ startError }}
				<button class="rc-btn" style="margin-top: 12px" @click="emit('exit')">Back</button>
			</div>
		</div>

		<template v-else-if="state.phase === 'recording' || state.phase === 'finishing'">
			<button class="rc-qbar" :class="{ 'rc-qbar--open': qbarOpen }" @click="qbarOpen = !qbarOpen">
				<span class="rc-eyebrow" style="margin: 0">Round {{ round.position }} of {{ session.rounds.length }}</span>
				<p class="rc-qbar__q">{{ round.question || round.title }}</p>
			</button>

			<div class="rc-scroll">
			<div class="rc-timer-wrap">
				<div class="rc-timer-ring" :class="{ 'rc-timer-ring--live': state.phase === 'recording' }">
					<span class="rc-timer">{{ elapsed }}</span>
					<span class="rc-timer-label">{{ state.phase === 'recording' ? 'recording' : 'stopping…' }}</span>
				</div>
			</div>

			<div class="rc-level"><div class="rc-level-fill" :style="{ width: level + '%' }"></div></div>

			<button class="rc-techbar" @click="techOpen = !techOpen">
				<span class="rc-techbar__item">
					<span class="rc-dot" :class="{ 'rc-dot--bad': state.storageError }"></span>
					{{ state.storageError ? 'Storage error' : 'Audio safe' }}
				</span>
				<span class="rc-techbar__item">
					<span class="rc-dot" :class="{ 'rc-dot--warn': !state.uploadOnline }"></span>
					{{ state.uploadOnline ? 'Uploading' : 'Offline' }}
				</span>
				<span class="rc-techbar__item">
					<span class="rc-dot" :class="{ 'rc-dot--warn': pendingChunks > 3 }"></span>
					{{ pendingChunks }} pending
				</span>
			</button>

			<div v-if="techOpen" class="rc-card" style="padding: 8px 18px">
				<div class="rc-status-row">
					<span class="rc-status-row__label">
						<SvgIcon :path="mdiDatabaseOutline" :size="19" style="color: var(--rc-muted)" />
						Local audio
					</span>
					<span :class="state.storageError ? 'rc-bad' : 'rc-ok'">
						{{ state.storageError ? '✕ STORAGE ERROR' : '✓ SAFE' }}
					</span>
				</div>
				<div class="rc-status-row">
					<span class="rc-status-row__label">
						<SvgIcon :path="mdiCloudUploadOutline" :size="19" style="color: var(--rc-muted)" />
						Server upload
					</span>
					<span :class="state.uploadOnline ? 'rc-ok' : 'rc-warn'">
						{{ state.uploadOnline ? '✓' : 'OFFLINE' }}
					</span>
				</div>
				<div class="rc-status-row">
					<span class="rc-status-row__label">
						<SvgIcon :path="mdiTrayFull" :size="19" style="color: var(--rc-muted)" />
						Pending upload
					</span>
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
			<p v-else class="rc-muted rc-center" style="font-size: 13.5px">
				Keep this page open while the table is recording.
			</p>

			<div v-if="state.lowStorage" class="rc-alert">
				Phone storage is getting low. Notify the facilitator after this round.
			</div>

			<div v-if="roundEnded && state.phase === 'recording'" class="rc-note">
				<template v-if="orchestrated && finishCountdown > 0">
					<strong>The round has ended — finishing in {{ finishCountdown }} s.</strong>
					<button class="rc-btn" style="margin-top: 10px" @click="cancelFinishCountdown">
						Keep talking
					</button>
				</template>
				<template v-else>
					<strong>The round has ended.</strong> Finish recording?
					<button class="rc-btn rc-primary" style="margin-top: 10px" @click="finishRecording">
						Finish and synchronize
					</button>
				</template>
			</div>

			<template v-if="state.phase === 'recording'">
				<div v-if="showLive" class="rc-card">
					<p class="rc-eyebrow">Live transcript — provisional</p>
					<p v-if="captionBlocks.length === 0" class="rc-muted" style="font-size: 14px; margin: 0">
						{{ liveChecked ? 'Live captions temporarily unavailable. Recording continues safely.' : 'Waiting for captions…' }}
					</p>
					<div v-else ref="captionsBox" class="rc-captions">
						<div v-for="(block, index) in captionBlocks" :key="index" class="rc-caption">
							<span v-if="block.speaker !== null" class="rc-caption__speaker">
								Speaker {{ block.speaker + 1 }}
							</span>
							{{ block.text }}
						</div>
					</div>
				</div>
				<button class="rc-btn rc-subtle" @click="showLive = !showLive">
					<SvgIcon :path="mdiBroadcast" :size="18" />
					{{ showLive ? 'Hide live transcript' : 'Show live transcript' }}
				</button>
			</template>
			</div>

			<div v-if="state.phase === 'recording'" class="rc-actions">
				<button v-if="!confirmFinish" class="rc-btn" @click="confirmFinish = true">
					Finish recording
				</button>
				<template v-else>
					<div class="rc-note" style="margin: 0 0 8px">Finish and synchronize this table's recording?</div>
					<button class="rc-btn rc-primary" style="margin-top: 0" @click="finishRecording">Yes, finish and synchronize</button>
					<button class="rc-btn rc-subtle" @click="confirmFinish = false">Keep recording</button>
				</template>
			</div>
		</template>

		<template v-else-if="state.phase === 'syncing'">
			<div class="rc-scroll">
				<div class="rc-hero">
					<div class="rc-hero__icon"><SvgIcon :path="mdiCloudUploadOutline" :size="44" style="color: var(--rc-blue)" /></div>
					<h1>Synchronizing</h1>
					<p class="rc-muted" style="margin-top: 10px; font-size: 16px">
						<span style="font-variant-numeric: tabular-nums">{{ state.ackedChunks }} / {{ state.localChunks }}</span>
						chunks uploaded
						<template v-if="state.serverState"><br />Server: {{ state.serverState }}</template>
					</p>
					<div v-if="!state.uploadOnline" class="rc-note" style="text-align: left">
						Waiting for network… the audio is safe on this phone. Keep this page open.
					</div>
				</div>
			</div>
		</template>

		<template v-else-if="state.phase === 'done'">
			<div class="rc-scroll">
				<div class="rc-hero">
					<div class="rc-hero__icon rc-hero__icon--ok"><SvgIcon :path="mdiCheckCircle" :size="52" /></div>
					<h1>Recording synchronized</h1>
					<p class="rc-muted" style="margin-top: 10px">
						Round {{ round.position }} is complete for this table.
						The recording was uploaded and validated by the server.
					</p>
					<p v-if="clearedNote" class="rc-muted">{{ clearedNote }}</p>

					<div v-if="nextRound" class="rc-note" style="text-align: left; margin-top: 20px">
						<strong>Round {{ nextRound.position }} has started.</strong>
						<template v-if="orchestrated && nextStartCountdown > 0">
							Recording begins in {{ nextStartCountdown }} s…
						</template>
						<br />
						{{ nextRound.question || nextRound.title }}
					</div>
					<p v-else class="rc-muted rc-center" style="margin-top: 20px; font-size: 13.5px">
						Keep this page open — the next round will appear here when the facilitator starts it.
					</p>
				</div>
			</div>

			<div class="rc-actions">
				<button
					v-if="nextRound && !orchestrated"
					class="rc-btn rc-record"
					style="margin-top: 0"
					@click="emit('nextRound', nextRound)">
					Start recording — Round {{ nextRound.position }}
				</button>
				<button v-if="!clearedNote" class="rc-linkbtn" @click="clearSynced">
					Clear synchronized audio from this phone
				</button>
			</div>
		</template>

		<template v-else-if="state.phase === 'failed'">
			<div class="rc-scroll">
				<div class="rc-alert" style="margin-top: 30px">
					<strong>Something went wrong:</strong><br />{{ state.error }}
					<br /><br />
					Local audio chunks remain stored on this phone.
				</div>
			</div>
			<div class="rc-actions">
				<button class="rc-btn" style="margin-top: 0" @click="emit('exit')">Back</button>
			</div>
		</template>
	</div>
</template>
