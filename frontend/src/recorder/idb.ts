/*
 * IndexedDB persistence for the recorder. Chunks are written here BEFORE any
 * upload attempt — local storage is the source of truth (brief §17.3).
 */

const DB_NAME = 'citizens-recorder'
const DB_VERSION = 1

export interface StoredRecording {
	recordingId: string
	roundId: string
	tableNumber: number
	mimeType: string
	startedAt: number
	finishedAt: number | null
	totalChunks: number | null
	serverComplete: boolean
}

export interface StoredChunk {
	key: string // `${recordingId}:${seq}`
	recordingId: string
	seq: number
	blob: Blob
	sha256: string
	sizeBytes: number
	createdAt: number
	acked: boolean
	attempts: number
}

let dbPromise: Promise<IDBDatabase> | null = null

function openDb(): Promise<IDBDatabase> {
	if (!dbPromise) {
		dbPromise = new Promise((resolve, reject) => {
			const request = indexedDB.open(DB_NAME, DB_VERSION)
			request.onupgradeneeded = () => {
				const db = request.result
				if (!db.objectStoreNames.contains('recordings')) {
					db.createObjectStore('recordings', { keyPath: 'recordingId' })
				}
				if (!db.objectStoreNames.contains('chunks')) {
					const store = db.createObjectStore('chunks', { keyPath: 'key' })
					store.createIndex('byRecording', 'recordingId', { unique: false })
				}
			}
			request.onsuccess = () => resolve(request.result)
			request.onerror = () => reject(request.error ?? new Error('IndexedDB open failed'))
		})
	}
	return dbPromise
}

function tx<T>(
	storeName: string,
	mode: IDBTransactionMode,
	run: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
	return openDb().then(
		(db) =>
			new Promise<T>((resolve, reject) => {
				const transaction = db.transaction(storeName, mode)
				const request = run(transaction.objectStore(storeName))
				request.onsuccess = () => resolve(request.result)
				request.onerror = () => reject(request.error ?? new Error('IndexedDB request failed'))
			}),
	)
}

export const idb = {
	async selfTest(): Promise<void> {
		await tx('recordings', 'readwrite', (store) =>
			store.put({
				recordingId: '__selftest__',
				roundId: '',
				tableNumber: 0,
				mimeType: '',
				startedAt: Date.now(),
				finishedAt: null,
				totalChunks: null,
				serverComplete: false,
			} satisfies StoredRecording),
		)
		await tx('recordings', 'readwrite', (store) => store.delete('__selftest__'))
	},

	putRecording: (recording: StoredRecording) =>
		tx('recordings', 'readwrite', (store) => store.put(recording)),

	getRecordings: () =>
		tx<StoredRecording[]>('recordings', 'readonly', (store) => store.getAll()),

	deleteRecording: (recordingId: string) =>
		tx('recordings', 'readwrite', (store) => store.delete(recordingId)),

	putChunk: (chunk: StoredChunk) => tx('chunks', 'readwrite', (store) => store.put(chunk)),

	chunksFor(recordingId: string): Promise<StoredChunk[]> {
		return openDb().then(
			(db) =>
				new Promise((resolve, reject) => {
					const store = db.transaction('chunks', 'readonly').objectStore('chunks')
					const request = store.index('byRecording').getAll(recordingId)
					request.onsuccess = () =>
						resolve((request.result as StoredChunk[]).sort((a, b) => a.seq - b.seq))
					request.onerror = () => reject(request.error ?? new Error('IndexedDB read failed'))
				}),
		)
	},

	async deleteChunksFor(recordingId: string): Promise<void> {
		const chunks = await this.chunksFor(recordingId)
		for (const chunk of chunks) {
			await tx('chunks', 'readwrite', (store) => store.delete(chunk.key))
		}
	},
}
