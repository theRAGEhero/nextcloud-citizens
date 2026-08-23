<script setup lang="ts">
import { mdiAlertCircleOutline, mdiQrcodeScan, mdiRecordCircleOutline } from '@mdi/js'
import { onMounted, ref } from 'vue'
import SvgIcon from '../components/ui/SvgIcon.vue'
import { recorderApi, type JoinResult, type RoundInfo } from './api'
import Preflight from './components/Preflight.vue'
import RecordingScreen from './components/RecordingScreen.vue'
import RecoverySync from './components/RecoverySync.vue'
import { idb, type StoredRecording } from './idb'
import { initLogger } from './logger'

const SESSION_KEY = 'citizens-recorder-session'

type Screen = 'joining' | 'no-invite' | 'recovery' | 'preflight' | 'ready' | 'recording' | 'error'

const screen = ref<Screen>('joining')
const error = ref('')
const session = ref<JoinResult | null>(null)
const selectedRound = ref<RoundInfo | null>(null)
const recoveryRecording = ref<StoredRecording | null>(null)

async function enterWithSession(joined: JoinResult): Promise<void> {
	session.value = joined
	selectedRound.value = pickRound(joined.rounds)
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

function pickRound(rounds: RoundInfo[]): RoundInfo | null {
	const open = rounds.filter((r) => !r.recorded_state)
	return (
		open.find((r) => r.status === 'ACTIVE') ??
		open.find((r) => r.status === 'NOT_STARTED') ??
		open[0] ??
		null
	)
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
	<div>
		<div v-if="screen === 'joining'" class="rc-hero" style="padding-top: 90px">
			<div class="rc-hero__icon"><span class="rc-spin" style="width: 30px; height: 30px"></span></div>
			<p class="rc-muted">Connecting to the assembly…</p>
		</div>

		<div v-else-if="screen === 'no-invite'" class="rc-hero" style="padding-top: 70px">
			<div class="rc-hero__icon"><SvgIcon :path="mdiQrcodeScan" :size="44" style="color: var(--rc-blue)" /></div>
			<h1>Table Recorder</h1>
			<p class="rc-muted" style="margin-top: 14px">
				Open this page by scanning your table's QR code.<br />
				Ask the facilitator for the QR sheet.
			</p>
		</div>

		<div v-else-if="screen === 'error'" class="rc-hero" style="padding-top: 70px">
			<div class="rc-hero__icon"><SvgIcon :path="mdiAlertCircleOutline" :size="44" style="color: var(--rc-red)" /></div>
			<h1>Cannot join</h1>
			<div class="rc-alert" style="text-align: left">{{ error }}</div>
			<p class="rc-muted">The QR code may have been revoked. Ask the facilitator for a new one.</p>
		</div>

		<RecoverySync
			v-else-if="screen === 'recovery' && session && recoveryRecording"
			:session="session"
			:recording="recoveryRecording"
			@done="recoveryRecording = null; screen = 'preflight'" />

		<Preflight
			v-else-if="screen === 'preflight' && session"
			:session="session"
			@ready="screen = 'ready'" />

		<div v-else-if="screen === 'ready' && session">
			<div class="rc-hero" style="padding-top: 16px; padding-bottom: 8px">
				<p class="rc-eyebrow">{{ session.assembly.name }}</p>
				<div class="rc-hero__table">TABLE {{ session.table_number }}</div>
			</div>

			<template v-if="selectedRound">
				<div class="rc-card">
					<p class="rc-eyebrow" style="margin-bottom: 4px">
						Round {{ selectedRound.position }} of {{ session.rounds.length }} ·
						{{ selectedRound.duration_minutes }} minutes
					</p>
					<p class="rc-question" style="margin: 0">{{ selectedRound.question || selectedRound.title }}</p>
					<div v-if="session.rounds.length > 1" style="margin-top: 14px">
						<select
							style="width: 100%; padding: 11px; border-radius: 10px; background: var(--rc-surface-2); color: var(--rc-text); border: 1px solid var(--rc-border); font-size: 15px"
							:value="selectedRound.id"
							@change="selectedRound = session.rounds.find((r) => r.id === ($event.target as HTMLSelectElement).value) ?? selectedRound">
							<option
								v-for="round in session.rounds"
								:key="round.id"
								:value="round.id"
								:disabled="!!round.recorded_state">
								Round {{ round.position }} — {{ round.title || round.question || 'Untitled' }}
								{{ round.recorded_state ? ' ✓ recorded' : '' }}
							</option>
						</select>
					</div>
				</div>
				<button
					class="rc-btn rc-record"
					:disabled="!!selectedRound.recorded_state"
					@click="screen = 'recording'">
					<SvgIcon :path="mdiRecordCircleOutline" :size="22" />
					Start recording
				</button>
			</template>

			<template v-else-if="session.rounds.length === 0">
				<div class="rc-alert">This assembly has no rounds yet.</div>
			</template>

			<template v-else>
				<div class="rc-card rc-center">
					<p class="rc-eyebrow">All rounds recorded</p>
					<p class="rc-muted" style="margin: 0">
						This table has completed every round. Thank you!
					</p>
				</div>
			</template>

			<button class="rc-btn rc-subtle" @click="screen = 'preflight'">Back to microphone test</button>
		</div>

		<RecordingScreen
			v-else-if="screen === 'recording' && session && selectedRound"
			:key="selectedRound.id"
			:session="session"
			:round="selectedRound"
			@exit="screen = 'ready'"
			@next-round="(round: RoundInfo) => { selectedRound = round; }" />
	</div>
</template>
