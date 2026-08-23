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
