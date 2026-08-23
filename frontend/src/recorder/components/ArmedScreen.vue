<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { recorderApi, type JoinResult, type RoundInfo } from '../api'

/*
 * Orchestrated mode: the table is ARMED. The phone waits for the facilitator
 * to start a round and then begins recording automatically — the arming tap
 * on READY was the human consent at the table.
 */

const props = defineProps<{ session: JoinResult }>()
const emit = defineEmits<{ start: [round: RoundInfo]; back: [] }>()

const rounds = ref<RoundInfo[]>(props.session.rounds)
const offline = ref(false)

let pollTimer = 0
let heartbeatTimer = 0

const nextRound = computed(() => rounds.value.find((r) => !r.recorded_state) ?? null)
const allRecorded = computed(() => rounds.value.length > 0 && !nextRound.value)

async function poll(): Promise<void> {
	try {
		const status = await recorderApi.status(props.session.session_token)
		rounds.value = status.rounds
		offline.value = false
		const active = status.rounds.find((r) => r.status === 'ACTIVE' && !r.recorded_state)
		if (active) emit('start', active)
	} catch {
		offline.value = true
	}
}

async function heartbeat(): Promise<void> {
	try {
		await recorderApi.heartbeat(props.session.session_token, {
			recording_active: false,
			armed: true,
			local_chunks: 0,
			acked_chunks: 0,
			storage_ok: true,
		})
	} catch {
		/* offline — retried */
	}
}

onMounted(() => {
	void poll()
	void heartbeat()
	pollTimer = window.setInterval(() => void poll(), 5000)
	heartbeatTimer = window.setInterval(() => void heartbeat(), 15000)
})

onBeforeUnmount(() => {
	window.clearInterval(pollTimer)
	window.clearInterval(heartbeatTimer)
})
</script>

<template>
	<div class="rc-fill">
		<div class="rc-scroll">
			<div class="rc-hero" style="padding-top: 16px; padding-bottom: 8px">
				<p class="rc-eyebrow">{{ session.assembly.name }}</p>
				<div class="rc-hero__table">TABLE {{ session.table_number }}</div>
			</div>

			<template v-if="allRecorded">
				<div class="rc-card rc-center">
					<p class="rc-eyebrow">All rounds recorded</p>
					<p class="rc-muted" style="margin: 0">This table has completed every round. Thank you!</p>
				</div>
			</template>

			<template v-else>
				<div class="rc-card rc-center">
					<p class="rc-eyebrow" style="color: var(--rc-green)">
						<span class="rc-live" style="color: var(--rc-green); display: inline-flex">ARMED</span>
					</p>
					<p style="font-size: 17px; font-weight: 600; margin: 8px 0 4px">
						Waiting for the facilitator to start
						{{ nextRound ? `Round ${nextRound.position}` : 'the round' }}
					</p>
					<p class="rc-muted" style="margin: 0; font-size: 14px">
						Recording begins automatically. Keep this page open and the phone on the table.
					</p>
				</div>
				<div v-if="nextRound && (nextRound.question || nextRound.title)" class="rc-card">
					<p class="rc-eyebrow" style="margin-bottom: 4px">
						Round {{ nextRound.position }} · {{ nextRound.duration_minutes }} minutes
					</p>
					<p class="rc-question" style="margin: 0">{{ nextRound.question || nextRound.title }}</p>
				</div>
				<div v-if="offline" class="rc-note">
					Network unavailable — reconnecting… the phone stays armed.
				</div>
			</template>
		</div>

		<div class="rc-actions">
			<button class="rc-btn rc-subtle" @click="emit('back')">Back to microphone test</button>
		</div>
	</div>
</template>
