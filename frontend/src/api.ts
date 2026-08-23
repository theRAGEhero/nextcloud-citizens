import type {
	Assembly,
	AssemblyDetail,
	Invite,
	InviteGenerated,
	Participant,
	ProvidersSummary,
	Round,
	RoundIn,
	RoundMonitor,
	Table,
} from './types'

// Derive the ExApp base URL from our own <script src>, so the app works both
// through /apps/app_api/proxy/citizens/... and a /exapps/citizens rewrite.
function detectBase(): string {
	const current = document.currentScript as HTMLScriptElement | null
	const el =
		current && current.src
			? current
			: document.querySelector<HTMLScriptElement>('script[src*="citizens-main"]')
	if (el && el.src) {
		return el.src.replace(/\/js\/citizens-main\.js.*$/, '')
	}
	return '/exapps/citizens'
}

export const BASE = detectBase()

export class ApiError extends Error {
	status: number

	constructor(status: number, message: string) {
		super(message)
		this.status = status
	}
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
	const response = await fetch(BASE + path, {
		method,
		headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
		body: body === undefined ? undefined : JSON.stringify(body),
		credentials: 'same-origin',
	})
	if (!response.ok) {
		let detail = `HTTP ${response.status}`
		try {
			const data = await response.json()
			if (data && typeof data.detail === 'string') detail = data.detail
		} catch {
			/* not JSON */
		}
		throw new ApiError(response.status, detail)
	}
	if (response.status === 204) return undefined as T
	return (await response.json()) as T
}

export const api = {
	listAssemblies: () => request<Assembly[]>('GET', '/api/v1/assemblies'),
	createAssembly: (data: {
		name: string
		description: string
		language: string
		expected_participants: number
		default_table_count: number
		rounds: RoundIn[]
	}) => request<AssemblyDetail>('POST', '/api/v1/assemblies', data),
	getAssembly: (id: string) => request<AssemblyDetail>('GET', `/api/v1/assemblies/${id}`),
	deleteAssembly: (id: string) => request<void>('DELETE', `/api/v1/assemblies/${id}`),

	addRound: (assemblyId: string, data: RoundIn) =>
		request<Round>('POST', `/api/v1/assemblies/${assemblyId}/rounds`, data),
	updateRound: (roundId: string, data: Partial<RoundIn> & { position?: number }) =>
		request<Round>('PATCH', `/api/v1/rounds/${roundId}`, data),
	deleteRound: (roundId: string) => request<void>('DELETE', `/api/v1/rounds/${roundId}`),

	listParticipants: (assemblyId: string) =>
		request<Participant[]>('GET', `/api/v1/assemblies/${assemblyId}/participants`),
	addParticipants: (assemblyId: string, participants: Array<Partial<Participant> & { label: string }>) =>
		request<Participant[]>('POST', `/api/v1/assemblies/${assemblyId}/participants`, { participants }),
	importCsv: (assemblyId: string, csv: string) =>
		request<Participant[]>('POST', `/api/v1/assemblies/${assemblyId}/participants/import-csv`, { csv }),
	deleteParticipant: (id: string) => request<void>('DELETE', `/api/v1/participants/${id}`),

	roundTables: (roundId: string) => request<Table[]>('GET', `/api/v1/rounds/${roundId}/tables`),
	randomize: (roundId: string) =>
		request<Table[]>('POST', `/api/v1/rounds/${roundId}/assignments/randomize`),
	copyPrevious: (roundId: string) =>
		request<Table[]>('POST', `/api/v1/rounds/${roundId}/assignments/copy-previous`),
	moveParticipant: (roundId: string, participantId: string, toTableId: string) =>
		request<Table[]>('POST', `/api/v1/rounds/${roundId}/assignments/move`, {
			participant_id: participantId,
			to_table_id: toTableId,
		}),

	adminPing: () => request<{ ok: boolean }>('GET', '/api/v1/admin/ping'),
	getProviders: () => request<ProvidersSummary>('GET', '/api/v1/admin/providers'),
	updateProviders: (payload: Record<string, unknown>) =>
		request<ProvidersSummary>('PUT', '/api/v1/admin/providers', payload),
	testProvider: (target: 'mistral' | 'deepgram' | 'analysis') =>
		request<{ ok: boolean; message: string }>('POST', '/api/v1/admin/providers/test', { target }),

	startRound: (roundId: string) => request<Round>('POST', `/api/v1/rounds/${roundId}/start`),
	endRound: (roundId: string) => request<Round>('POST', `/api/v1/rounds/${roundId}/end`),
	roundMonitor: (roundId: string) => request<RoundMonitor>('GET', `/api/v1/rounds/${roundId}/monitor`),
	deviceLogs: (assemblyId: string, tableNumber: number, tail = 200) =>
		request<{ session_id: string | null; lines: string[] }>(
			'GET',
			`/api/v1/assemblies/${assemblyId}/tables/${tableNumber}/device-logs?tail=${tail}`,
		),

	listInvites: (assemblyId: string) =>
		request<Invite[]>('GET', `/api/v1/assemblies/${assemblyId}/invites`),
	generateInvites: (assemblyId: string) =>
		request<InviteGenerated[]>('POST', `/api/v1/assemblies/${assemblyId}/invites/generate`),
	revokeInvites: (assemblyId: string) =>
		request<void>('POST', `/api/v1/assemblies/${assemblyId}/invites/revoke`),
}
