<!-- SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
     SPDX-License-Identifier: AGPL-3.0-or-later -->
<script setup lang="ts">
/**
 * Shown once per device before anything is recorded (brief §43).
 *
 * People at the table are about to have their voices recorded, so they are
 * told in plain language what happens to that audio: which engine transcribes
 * it, whether that engine belongs to somebody else, and how long the recording
 * is kept. Everything here comes from the server's live configuration, so it
 * cannot drift from what the app actually does.
 */
import { computed } from 'vue'
import type { DataHandling } from '../api'

const props = defineProps<{ handling: DataHandling | null; tableNumber: number }>()
const emit = defineEmits<{ (event: 'accept'): void }>()

const ENGINE_NAMES: Record<string, string> = {
	deepgram: 'Deepgram',
	mistral: 'Mistral',
	whisper: 'Whisper',
	vosk: 'Vosk',
}

const engine = computed(() => ENGINE_NAMES[props.handling?.stt_provider ?? ''] ?? 'a transcription engine')

const audioDestination = computed(() => {
	if (!props.handling) return 'This assembly is not yet set up to transcribe recordings.'
	if (!props.handling.stt_configured) return 'No transcription engine is configured, so the audio stays on this server.'
	return props.handling.stt_hosted
		? `The recording is sent to ${engine.value}, an outside service, to be turned into text.`
		: `The recording is transcribed by ${engine.value} on this organisation's own server. The audio is not sent to any outside company.`
})

const transcriptDestination = computed(() => {
	if (!props.handling?.analysis_enabled) return null
	return props.handling.analysis_hosted
		? 'The written transcript — never the audio — is also sent to an outside AI service to draft a summary.'
		: "The written transcript is summarised by AI on this organisation's own server."
})

const retention = computed(() => {
	const days = props.handling?.audio_retention_days ?? 0
	if (days > 0) return `The audio recording is deleted ${days} days after the assembly ends.`
	return 'The audio recording is kept until an organiser deletes it.'
})
</script>

<template>
	<div class="rc-scroll">
		<div class="rc-pad">
			<h1>Table {{ tableNumber }}</h1>
			<p class="rc-lead">Before you start, here is what happens to this recording.</p>

			<ul class="rc-consent">
				<li>This phone records the conversation at your table.</li>
				<li>{{ audioDestination }}</li>
				<li v-if="transcriptDestination">{{ transcriptDestination }}</li>
				<li>{{ retention }}</li>
				<li>
					Speakers are labelled only as “Speaker 1”, “Speaker 2” and so on. Nobody's
					name is attached to what they said unless an organiser adds it.
				</li>
				<li>Nothing is published until a person has reviewed it.</li>
			</ul>

			<p class="rc-muted rc-consent__ask">
				Please make sure everyone at the table has heard this before you begin.
			</p>

			<button class="rc-btn rc-btn--primary rc-btn--block" @click="emit('accept')">
				Everyone at this table agrees — continue
			</button>
		</div>
	</div>
</template>

<style scoped>
.rc-consent {
	margin: 18px 0 0;
	padding-left: 20px;
	line-height: 1.55;
}
.rc-consent li + li {
	margin-top: 10px;
}
.rc-consent__ask {
	margin: 20px 0 18px;
}
</style>
