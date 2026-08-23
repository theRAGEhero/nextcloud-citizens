<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { recorderApi, type JoinResult } from '../api'
import { pickMimeType } from '../engine'
import { idb } from '../idb'

const props = defineProps<{ session: JoinResult }>()
const emit = defineEmits<{ ready: [] }>()

type CheckState = 'pending' | 'ok' | 'warn' | 'fail'

const checks = ref<Record<string, { state: CheckState; note: string }>>({
	microphone: { state: 'pending', note: '' },
	recorder: { state: 'pending', note: '' },
	storage: { state: 'pending', note: '' },
	persistent: { state: 'pending', note: '' },
	server: { state: 'pending', note: '' },
})
const level = ref(0)
const testState = ref<'idle' | 'recording' | 'ready' | 'playing'>('idle')

let stream: MediaStream | null = null
let audioContext: AudioContext | null = null
let levelTimer = 0
let testRecorder: MediaRecorder | null = null
let testBuffer: AudioBuffer | null = null
let testSource: AudioBufferSourceNode | null = null

function set(check: string, state: CheckState, note = ''): void {
	checks.value[check] = { state, note }
}

onMounted(async () => {
	// microphone + level meter
	try {
		stream = await navigator.mediaDevices.getUserMedia({ audio: true })
		set('microphone', 'ok')
		audioContext = new AudioContext()
		const source = audioContext.createMediaStreamSource(stream)
		const analyser = audioContext.createAnalyser()
		analyser.fftSize = 512
		source.connect(analyser)
		const samples = new Uint8Array(analyser.fftSize)
		levelTimer = window.setInterval(() => {
			analyser.getByteTimeDomainData(samples)
			let peak = 0
			for (const value of samples) peak = Math.max(peak, Math.abs(value - 128))
			level.value = Math.min(100, Math.round((peak / 128) * 160))
		}, 90)
	} catch {
		set('microphone', 'fail', 'Microphone access denied or unavailable')
	}

	// MediaRecorder support
	const mime = pickMimeType()
	if (mime) set('recorder', 'ok', mime.split(';')[0])
	else set('recorder', 'fail', 'No supported recording format')

	// IndexedDB write test + storage estimate
	try {
		await idb.selfTest()
		let note = ''
		if (navigator.storage?.estimate) {
			const { quota, usage } = await navigator.storage.estimate()
			if (quota) note = `${Math.round(((quota - (usage ?? 0)) / 1024 / 1024) * 10) / 10} MB free`
		}
		set('storage', 'ok', note)
	} catch {
		set('storage', 'fail', 'Cannot write to local storage')
	}

	// persistent storage (best effort)
	try {
		if (navigator.storage?.persist) {
			const persisted = await navigator.storage.persist()
			set('persistent', persisted ? 'ok' : 'warn', persisted ? '' : 'Browser may evict data under pressure')
		} else {
			set('persistent', 'warn', 'Not supported by this browser')
		}
	} catch {
		set('persistent', 'warn', 'Could not request persistence')
	}

	// server connectivity
	try {
		await recorderApi.status(props.session.session_token)
		set('server', 'ok')
	} catch {
		set('server', 'warn', 'Server unreachable — recording still works locally')
	}
})

onBeforeUnmount(() => {
	window.clearInterval(levelTimer)
	testSource?.stop()
	stream?.getTracks().forEach((track) => track.stop())
	audioContext?.close()
})

function recordTest(): void {
	if (!stream) return
	const mime = pickMimeType()
	if (!mime) return
	testState.value = 'recording'
	const blobs: Blob[] = []
	testRecorder = new MediaRecorder(stream, { mimeType: mime })
	testRecorder.ondataavailable = (event) => blobs.push(event.data)
	testRecorder.onstop = async () => {
		// Decode via WebAudio: blob: URLs in an <audio> element are blocked by
		// the Nextcloud proxy's CSP (media-src 'self'); decodeAudioData is not.
		try {
			const data = await new Blob(blobs, { type: mime }).arrayBuffer()
			if (!audioContext) audioContext = new AudioContext()
			testBuffer = await audioContext.decodeAudioData(data)
			testState.value = 'ready'
		} catch {
			testBuffer = null
			testState.value = 'idle'
		}
	}
	testRecorder.start()
	window.setTimeout(() => testRecorder?.stop(), 5000)
}

function playTest(): void {
	if (!testBuffer || !audioContext) return
	testState.value = 'playing'
	testSource = audioContext.createBufferSource()
	testSource.buffer = testBuffer
	testSource.connect(audioContext.destination)
	testSource.onended = () => (testState.value = 'ready')
	testSource.start()
}

// Only microphone or local-storage failure blocks recording (brief §15)
function canProceed(): boolean {
	return checks.value.microphone.state === 'ok' &&
		checks.value.recorder.state === 'ok' &&
		checks.value.storage.state === 'ok'
}

const LABELS: Record<string, string> = {
	microphone: 'Microphone',
	recorder: 'Audio recording',
	storage: 'Local storage',
	persistent: 'Persistent storage',
	server: 'Server connection',
}

const ICONS: Record<CheckState, string> = { pending: '…', ok: '✓', warn: '⚠', fail: '✕' }
const CLASSES: Record<CheckState, string> = {
	pending: 'rc-muted', ok: 'rc-ok', warn: 'rc-warn', fail: 'rc-bad',
}
</script>

<template>
	<div>
		<div class="rc-header">
			<span class="rc-table-badge">TABLE {{ session.table_number }}</span>
		</div>
		<div class="rc-card">
			<h2>Microphone test</h2>
			<div v-for="(check, key) in checks" :key="key" class="rc-status-row">
				<span>
					{{ LABELS[key] }}
					<span v-if="check.note" class="rc-muted" style="font-size: 12px"> — {{ check.note }}</span>
				</span>
				<span :class="CLASSES[check.state]">{{ ICONS[check.state] }}</span>
			</div>

			<p class="rc-muted" style="margin: 14px 0 4px">Audio level — speak at the table</p>
			<div class="rc-level"><div class="rc-level-fill" :style="{ width: level + '%' }"></div></div>

			<button
				class="rc-btn"
				:disabled="testState === 'recording' || checks.microphone.state !== 'ok'"
				@click="recordTest">
				{{ testState === 'recording' ? 'Recording 5 seconds…' : 'Record 5-second test' }}
			</button>
			<button
				v-if="testState === 'ready' || testState === 'playing'"
				class="rc-btn"
				:disabled="testState === 'playing'"
				@click="playTest">
				▶ Listen to the test
			</button>
		</div>

		<div v-if="checks.microphone.state === 'fail'" class="rc-alert">
			Microphone access is required. Allow microphone access in the browser and reload this page.
		</div>
		<div v-else-if="checks.storage.state === 'fail'" class="rc-alert">
			This browser cannot store audio locally. Recording would not be safe — please use a different
			browser or disable private mode.
		</div>

		<button class="rc-btn rc-primary" :disabled="!canProceed()" @click="emit('ready')">READY</button>
	</div>
</template>
