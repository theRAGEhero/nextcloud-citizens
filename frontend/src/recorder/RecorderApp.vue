<script setup lang="ts">
import { mdiAlertCircleOutline, mdiQrcodeScan } from '@mdi/js'
import { computed, onMounted, ref } from 'vue'
import SvgIcon from '../components/ui/SvgIcon.vue'
import { recorderApi, type JoinResult, type RoundInfo } from './api'
import ArmedScreen from './components/ArmedScreen.vue'
import Preflight from './components/Preflight.vue'
import RecordingScreen from './components/RecordingScreen.vue'
import RecoverySync from './components/RecoverySync.vue'
import { idb, type StoredRecording } from './idb'
import { initLogger } from './logger'

const SESSION_KEY = 'citizens-recorder-session'

type Screen = 'joining' | 'no-invite' | 'recovery' | 'preflight' | 'armed' | 'recording' | 'error'

const screen = ref<Screen>('joining')
const error = ref('')
const session = ref<JoinResult | null>(null)
const selectedRound = ref<RoundInfo | null>(null)
const recoveryRecording = ref<StoredRecording | null>(null)

const orchestrated = computed(() => session.value?.assembly.recording_mode === 'orchestrated')

function startRound(round: RoundInfo): void {
	selectedRound.value = round
	screen.value = 'recording'
}

async function enterWithSession(joined: JoinResult): Promise<void> {
	session.value = joined
	initLogger(joined.session_token)
	// reload/crash recovery: unsynchronized local recordings take priority (brief §20)
	try {
		const unfinished = await idb.unfinishedRecordings()
		const candidate = unfinished.find((r) => r.totalChunks !== null || r.startedAt > 0)
		if (candidate) {
			const chunks = await idb.chunksFor(candidate.recordingId)
			if (chunks.length > 0) {
				recoveryRecording.value = candidate
				screen.value = 'recovery'
				return
			}
			await idb.deleteRecording(candidate.recordingId)
		}
	} catch {
		/* recovery scan failure must not block a fresh session */
	}
	screen.value = 'preflight'
}

onMounted(async () => {
	// 1) fresh QR join: #/join/<token>
	const match = window.location.hash.match(/#\/join\/(.+)$/)
	if (match) {
		try {
			const joined = await recorderApi.join(decodeURIComponent(match[1]))
			sessionStore(joined)
			// remove the invite secret from the visible URL (brief §14)
			history.replaceState(null, '', window.location.pathname + window.location.search)
			await enterWithSession(joined)
			return
		} catch (err) {
			error.value = err instanceof Error ? err.message : String(err)
			screen.value = 'error'
			return
		}
	}
	// 2) returning device with a stored session
	const stored = sessionLoad()
	if (stored) {
		try {
			const status = await recorderApi.status(stored.session_token)
			await enterWithSession({ ...stored, ...status })
			return
		} catch {
			sessionStorageClear()
		}
	}
	screen.value = 'no-invite'
})

function sessionStore(joined: JoinResult): void {
	try {
		localStorage.setItem(SESSION_KEY, JSON.stringify(joined))
	} catch {
		/* private mode: session survives only until reload */
	}
}

function sessionLoad(): JoinResult | null {
	try {
		const raw = localStorage.getItem(SESSION_KEY)
		return raw ? (JSON.parse(raw) as JoinResult) : null
	} catch {
		return null
	}
}

function sessionStorageClear(): void {
	try {
		localStorage.removeItem(SESSION_KEY)
	} catch {
		/* ignore */
	}
}
</script>

<template>
	<div class="rc-screen">
		<div v-if="screen === 'joining'" class="rc-scroll">
			<div class="rc-hero" style="padding-top: 26vh">
				<div class="rc-hero__icon"><span class="rc-spin" style="width: 30px; height: 30px"></span></div>
				<p class="rc-muted">Connecting to the assembly…</p>
			</div>
		</div>

		<div v-else-if="screen === 'no-invite'" class="rc-scroll">
			<div class="rc-hero" style="padding-top: 18vh">
				<div class="rc-hero__icon"><SvgIcon :path="mdiQrcodeScan" :size="44" style="color: var(--rc-blue)" /></div>
				<h1>Table Recorder</h1>
				<p class="rc-muted" style="margin-top: 14px">
					Open this page by scanning your table's QR code.<br />
					Ask the facilitator for the QR sheet.
				</p>
			</div>
		</div>

		<div v-else-if="screen === 'error'" class="rc-scroll">
			<div class="rc-hero" style="padding-top: 14vh">
				<div class="rc-hero__icon"><SvgIcon :path="mdiAlertCircleOutline" :size="44" style="color: var(--rc-red)" /></div>
				<h1>Cannot join</h1>
				<div class="rc-alert" style="text-align: left">{{ error }}</div>
				<p class="rc-muted">The QR code may have been revoked. Ask the facilitator for a new one.</p>
			</div>
		</div>

		<RecoverySync
			v-else-if="screen === 'recovery' && session && recoveryRecording"
			:session="session"
			:recording="recoveryRecording"
			@done="recoveryRecording = null; screen = 'preflight'" />

		<Preflight
			v-else-if="screen === 'preflight' && session"
			:session="session"
			@ready="screen = 'armed'"
			@start="startRound" />

		<ArmedScreen
			v-else-if="screen === 'armed' && session"
			:session="session"
			@start="startRound"
			@back="screen = 'preflight'" />

		<RecordingScreen
			v-else-if="screen === 'recording' && session && selectedRound"
			:key="selectedRound.id"
			:session="session"
			:round="selectedRound"
			@exit="screen = orchestrated ? 'armed' : 'preflight'"
			@next-round="startRound" />
	</div>
</template>
