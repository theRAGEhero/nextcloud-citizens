<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import type { ProvidersSummary } from '../types'

const emit = defineEmits<{ back: [] }>()

const summary = ref<ProvidersSummary | null>(null)
const error = ref('')
const savedNote = ref('')
const busy = ref(false)

const sttProvider = ref<'mistral' | 'deepgram'>('mistral')
const liveEnabled = ref(true)
const batchEnabled = ref(true)
const mistralKey = ref('')
const deepgramKey = ref('')
const analysisBaseUrl = ref('')
const analysisModel = ref('')
const analysisKey = ref('')
const testResults = ref<Record<string, { ok: boolean; message: string }>>({})

async function reload(): Promise<void> {
	summary.value = await api.getProviders()
	sttProvider.value = summary.value.stt.provider
	liveEnabled.value = summary.value.stt.live_enabled
	batchEnabled.value = summary.value.stt.batch_enabled
	analysisBaseUrl.value = summary.value.analysis.base_url
	analysisModel.value = summary.value.analysis.model
}

onMounted(async () => {
	try {
		await reload()
	} catch (err) {
		error.value = err instanceof Error ? err.message : String(err)
	}
})

async function save(): Promise<void> {
	busy.value = true
	error.value = ''
	savedNote.value = ''
	try {
		const payload: Record<string, unknown> = {
			stt_provider: sttProvider.value,
			stt_live_enabled: liveEnabled.value,
			stt_batch_enabled: batchEnabled.value,
			analysis_base_url: analysisBaseUrl.value.trim(),
			analysis_model: analysisModel.value.trim(),
		}
		// key fields: only send when the admin typed something (empty input = keep)
		if (mistralKey.value) payload.mistral_api_key = mistralKey.value
		if (deepgramKey.value) payload.deepgram_api_key = deepgramKey.value
		if (analysisKey.value) payload.analysis_api_key = analysisKey.value
		summary.value = await api.updateProviders(payload)
		mistralKey.value = ''
		deepgramKey.value = ''
		analysisKey.value = ''
		savedNote.value = 'Settings saved.'
	} catch (err) {
		error.value = err instanceof Error ? err.message : String(err)
	} finally {
		busy.value = false
	}
}

async function test(target: 'mistral' | 'deepgram' | 'analysis'): Promise<void> {
	busy.value = true
	try {
		testResults.value = { ...testResults.value, [target]: await api.testProvider(target) }
	} catch (err) {
		testResults.value = {
			...testResults.value,
			[target]: { ok: false, message: err instanceof Error ? err.message : String(err) },
		}
	} finally {
		busy.value = false
	}
}

function keyPlaceholder(configured: boolean, hint: string): string {
	return configured ? `configured — ${hint} (type to replace)` : 'Paste API key'
}
</script>

<template>
	<div>
		<button class="cz-btn cz-small" @click="emit('back')">← Assemblies</button>
		<h2 style="margin-top: 14px">Speech &amp; AI settings</h2>
		<p class="cz-muted">
			API keys are stored encrypted in Nextcloud and are never sent to browsers or table phones.
		</p>

		<div v-if="error" class="cz-error">{{ error }}</div>
		<div v-if="savedNote" class="cz-ok-note">{{ savedNote }}</div>

		<template v-if="summary">
			<div class="cz-card">
				<h3>Transcription provider</h3>
				<div class="cz-row" style="gap: 24px; margin-bottom: 14px">
					<label style="display: flex; align-items: center; gap: 8px">
						<input v-model="sttProvider" type="radio" value="mistral" /> Mistral (Voxtral)
					</label>
					<label style="display: flex; align-items: center; gap: 8px">
						<input v-model="sttProvider" type="radio" value="deepgram" /> Deepgram
					</label>
				</div>

				<div class="cz-field" style="max-width: 480px">
					<label>Mistral API key</label>
					<div class="cz-row">
						<input
							v-model="mistralKey"
							type="password"
							autocomplete="off"
							style="flex: 1"
							:placeholder="keyPlaceholder(summary.stt.mistral_configured, summary.stt.mistral_key_hint)" />
						<button class="cz-btn cz-small" :disabled="busy" @click="test('mistral')">Test</button>
					</div>
					<span
						v-if="testResults.mistral"
						:class="testResults.mistral.ok ? 'cz-ok-note' : 'cz-error'"
						style="margin: 6px 0 0; padding: 6px 10px">
						{{ testResults.mistral.ok ? '✓' : '✕' }} {{ testResults.mistral.message }}
					</span>
				</div>

				<div class="cz-field" style="max-width: 480px">
					<label>Deepgram API key</label>
					<div class="cz-row">
						<input
							v-model="deepgramKey"
							type="password"
							autocomplete="off"
							style="flex: 1"
							:placeholder="keyPlaceholder(summary.stt.deepgram_configured, summary.stt.deepgram_key_hint)" />
						<button class="cz-btn cz-small" :disabled="busy" @click="test('deepgram')">Test</button>
					</div>
					<span
						v-if="testResults.deepgram"
						:class="testResults.deepgram.ok ? 'cz-ok-note' : 'cz-error'"
						style="margin: 6px 0 0; padding: 6px 10px">
						{{ testResults.deepgram.ok ? '✓' : '✕' }} {{ testResults.deepgram.message }}
					</span>
				</div>

				<div class="cz-row" style="gap: 24px">
					<label style="display: flex; align-items: center; gap: 8px">
						<input v-model="liveEnabled" type="checkbox" /> Live transcription
					</label>
					<label style="display: flex; align-items: center; gap: 8px">
						<input v-model="batchEnabled" type="checkbox" /> Final transcription
					</label>
				</div>
			</div>

			<div class="cz-card">
				<h3>AI analysis</h3>
				<p class="cz-muted" style="font-size: 13px; margin-top: 0">
					Any OpenAI-compatible endpoint works: Mistral (default), Ollama Cloud, a remote Ollama
					server, vLLM…
				</p>
				<div class="cz-row" style="align-items: flex-start">
					<div class="cz-field" style="flex: 2; min-width: 260px">
						<label>Base URL</label>
						<input v-model="analysisBaseUrl" type="text" placeholder="https://api.mistral.ai/v1" />
					</div>
					<div class="cz-field" style="flex: 1; min-width: 180px">
						<label>Model</label>
						<input v-model="analysisModel" type="text" placeholder="mistral-large-latest" />
					</div>
				</div>
				<div class="cz-field" style="max-width: 480px">
					<label>API key</label>
					<div class="cz-row">
						<input
							v-model="analysisKey"
							type="password"
							autocomplete="off"
							style="flex: 1"
							:placeholder="keyPlaceholder(summary.analysis.configured, summary.analysis.key_hint)" />
						<button class="cz-btn cz-small" :disabled="busy" @click="test('analysis')">Test</button>
					</div>
					<span
						v-if="testResults.analysis"
						:class="testResults.analysis.ok ? 'cz-ok-note' : 'cz-error'"
						style="margin: 6px 0 0; padding: 6px 10px">
						{{ testResults.analysis.ok ? '✓' : '✕' }} {{ testResults.analysis.message }}
					</span>
				</div>
			</div>

			<button class="cz-btn cz-primary" :disabled="busy" @click="save">
				{{ busy ? 'Saving…' : 'Save settings' }}
			</button>
		</template>
	</div>
</template>
