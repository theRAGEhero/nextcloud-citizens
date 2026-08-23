<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { recorderApi, type JoinResult, type RoundInfo } from './api'
import Preflight from './components/Preflight.vue'
import RecordingScreen from './components/RecordingScreen.vue'

const SESSION_KEY = 'citizens-recorder-session'

type Screen = 'joining' | 'no-invite' | 'preflight' | 'ready' | 'recording' | 'error'

const screen = ref<Screen>('joining')
const error = ref('')
const session = ref<JoinResult | null>(null)
const selectedRound = ref<RoundInfo | null>(null)

function pickRound(rounds: RoundInfo[]): RoundInfo | null {
	return rounds.find((r) => r.status === 'ACTIVE') ?? rounds.find((r) => r.status === 'NOT_STARTED') ?? rounds[0] ?? null
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
			session.value = joined
			selectedRound.value = pickRound(joined.rounds)
			screen.value = 'preflight'
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
			session.value = { ...stored, ...status }
			selectedRound.value = pickRound(status.rounds)
			screen.value = 'preflight'
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
		<div v-if="screen === 'joining'" class="rc-center" style="padding-top: 80px">
			<div class="rc-big-icon">⏳</div>
			<p class="rc-muted">Connecting to the assembly…</p>
		</div>

		<div v-else-if="screen === 'no-invite'" class="rc-center" style="padding-top: 60px">
			<div class="rc-big-icon">📷</div>
			<h1>Table Recorder</h1>
			<p class="rc-muted" style="margin-top: 14px">
				Open this page by scanning your table's QR code.<br />
				Ask the facilitator for the QR sheet.
			</p>
		</div>

		<div v-else-if="screen === 'error'" class="rc-center" style="padding-top: 60px">
			<div class="rc-big-icon">⚠️</div>
			<h1>Cannot join</h1>
			<div class="rc-alert" style="text-align: left">{{ error }}</div>
			<p class="rc-muted">The QR code may have been revoked. Ask the facilitator for a new one.</p>
		</div>

		<Preflight
			v-else-if="screen === 'preflight' && session"
			:session="session"
			@ready="screen = 'ready'" />

		<div v-else-if="screen === 'ready' && session">
			<div class="rc-header">
				<span class="rc-table-badge">TABLE {{ session.table_number }}</span>
			</div>
			<div class="rc-card">
				<h2>{{ session.assembly.name }}</h2>
				<template v-if="selectedRound">
					<p class="rc-muted">
						Round {{ selectedRound.position }} of {{ session.rounds.length }} ·
						{{ selectedRound.duration_minutes }} minutes
					</p>
					<p class="rc-question">{{ selectedRound.question || selectedRound.title }}</p>
					<div v-if="session.rounds.length > 1" style="margin-top: 12px">
						<select
							style="width: 100%; padding: 10px; border-radius: 8px; background: #333; color: #eee; border: 1px solid #444"
							:value="selectedRound.id"
							@change="selectedRound = session.rounds.find((r) => r.id === ($event.target as HTMLSelectElement).value) ?? selectedRound">
							<option v-for="round in session.rounds" :key="round.id" :value="round.id">
								Round {{ round.position }} — {{ round.title || round.question || 'Untitled' }}
							</option>
						</select>
					</div>
				</template>
				<p v-else class="rc-alert">This assembly has no rounds yet.</p>
			</div>
			<button
				class="rc-btn rc-record"
				:disabled="!selectedRound"
				@click="screen = 'recording'">
				● Start recording
			</button>
			<button class="rc-btn rc-subtle" @click="screen = 'preflight'">Back to microphone test</button>
		</div>

		<RecordingScreen
			v-else-if="screen === 'recording' && session && selectedRound"
			:session="session"
			:round="selectedRound"
			@exit="screen = 'ready'" />
	</div>
</template>
