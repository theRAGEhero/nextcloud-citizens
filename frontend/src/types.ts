export interface RoundIn {
	title: string
	question: string
	duration_minutes: number
}

export interface Round extends RoundIn {
	id: string
	position: number
	status: string
	started_at: string | null
	ended_at: string | null
}

export interface Assembly {
	id: string
	name: string
	description: string
	language: string
	scheduled_at: string | null
	status: string
	expected_participants: number
	default_table_count: number
	created_by: string
	created_at: string
}

export interface AssemblyDetail extends Assembly {
	rounds: Round[]
	participant_count: number
}

export interface Participant {
	id: string
	label: string
	name: string
	email: string
	notes: string
}

export interface Table {
	id: string
	number: number
	label: string
	status: string
	participants: Participant[]
}

export interface Invite {
	id: string
	table_number: number
	active: boolean
	created_at: string
}

export interface InviteGenerated {
	table_number: number
	url: string
	qr_svg: string
}

export interface DeviceStatus {
	recording_active?: boolean
	local_chunks?: number
	acked_chunks?: number
	storage_ok?: boolean
	storage_free_mb?: number
}

export interface MonitorTable {
	table_id: string
	number: number
	device: { connected: boolean; seconds_since_contact: number | null; status: DeviceStatus }
	local_recording_safe: boolean
	recording: {
		id: string
		state: string
		started_at: string | null
		received_chunks: number
		total_chunks: number | null
		error_code: string
	} | null
}

export interface ProvidersSummary {
	stt: {
		provider: 'mistral' | 'deepgram'
		live_enabled: boolean
		batch_enabled: boolean
		mistral_configured: boolean
		mistral_key_hint: string
		mistral_model: string
		deepgram_configured: boolean
		deepgram_key_hint: string
		deepgram_model: string
	}
	analysis: {
		base_url: string
		model: string
		configured: boolean
		key_hint: string
	}
}

export interface TranscriptSegment {
	id: string
	speaker: string
	start: number
	end: number
	text: string
}

export interface TranscriptData {
	transcript_id: string
	recording_id: string
	provider: string
	model: string
	language: string
	segments: TranscriptSegment[]
}

export interface RoundMonitor {
	round_id: string
	status: string
	started_at: string | null
	duration_minutes: number
	tables: MonitorTable[]
}
