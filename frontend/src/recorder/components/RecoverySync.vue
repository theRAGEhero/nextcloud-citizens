<script setup lang="ts">
import { computed, onMounted } from 'vue'
import type { JoinResult } from '../api'
import { RecorderEngine } from '../engine'
import type { StoredRecording } from '../idb'

const props = defineProps<{ session: JoinResult; recording: StoredRecording }>()
const emit = defineEmits<{ done: [] }>()

const engine = new RecorderEngine()
const state = engine.state

const pending = computed(() => state.localChunks - state.ackedChunks)

onMounted(() => {
	void engine.resumeSync(props.session.session_token, props.recording)
})
</script>

<template>
	<div>
		<div class="rc-header">
			<span class="rc-table-badge">TABLE {{ session.table_number }}</span>
		</div>

		<div class="rc-card">
			<h2>Recovered recording</h2>
			<p class="rc-muted">
				This phone has a recording that was not fully synchronized — for example after the page
				was reloaded or the browser closed. All locally saved audio is intact.
			</p>
			<div class="rc-status-row">
				<span>Chunks stored locally</span><span>{{ state.localChunks }}</span>
			</div>
			<div class="rc-status-row">
				<span>Awaiting upload</span>
				<span :class="pending > 0 ? 'rc-warn' : 'rc-ok'">{{ pending }}</span>
			</div>
			<div class="rc-status-row">
				<span>Server</span><span>{{ state.serverState || '—' }}</span>
			</div>
		</div>

		<template v-if="state.phase === 'syncing'">
			<div v-if="!state.uploadOnline" class="rc-note">
				Waiting for network… the audio is safe on this phone. Keep this page open.
				<button class="rc-btn" style="margin-top: 10px" @click="engine.retryNow()">Retry now</button>
			</div>
			<p v-else class="rc-muted rc-center">Synchronizing…</p>
		</template>

		<template v-else-if="state.phase === 'done'">
			<div class="rc-note">✅ Recovered recording fully synchronized and validated.</div>
			<button class="rc-btn rc-primary" @click="emit('done')">Continue</button>
		</template>

		<template v-else-if="state.phase === 'failed'">
			<div class="rc-alert">
				Recovery synchronization failed: {{ state.error }}<br />
				Local audio remains stored on this phone. Notify the facilitator.
			</div>
			<button class="rc-btn" @click="engine.retryNow()">Try again</button>
			<button class="rc-btn rc-subtle" @click="emit('done')">Skip for now</button>
		</template>
	</div>
</template>
