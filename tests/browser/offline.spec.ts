/*
 * Release-blocker offline tests (brief §56):
 *  - Test A: network loss during recording — recording continues locally,
 *    everything synchronizes after reconnection, server reconstructs audio.
 *  - Test C: browser reload — persisted chunks are recovered and synchronized.
 *
 * Runs against the throwaway instance from scripts/browser-test-env.sh
 * (fake microphone; 2-second chunks via ?chunkms=2000).
 */

import { execSync } from 'node:child_process'
import { expect, test, type Page } from '@playwright/test'

const CHUNK_MS = 2000

interface Seed {
	assembly_id: string
	round_id: string
	token: string
}

function seed(): Seed {
	const output = execSync('sh ../scripts/browser-test-env.sh seed', { encoding: 'utf-8' })
	return JSON.parse(output.trim()) as Seed
}

async function startRecording(page: Page, token: string): Promise<void> {
	await page.goto(`/recorder.html?chunkms=${CHUNK_MS}#/join/${encodeURIComponent(token)}`)
	await expect(page.getByText('Microphone test')).toBeVisible({ timeout: 15_000 })
	await expect(page.getByRole('button', { name: 'READY' })).toBeEnabled({ timeout: 15_000 })
	await page.getByRole('button', { name: 'READY' }).click()
	await page.getByRole('button', { name: /Start recording/ }).click()
	await expect(page.getByText('RECORDING', { exact: true })).toBeVisible({ timeout: 15_000 })
}

async function localChunkCount(page: Page): Promise<number> {
	return page.evaluate(
		() =>
			new Promise<number>((resolve, reject) => {
				const open = indexedDB.open('citizens-recorder')
				open.onsuccess = () => {
					const db = open.result
					const request = db.transaction('chunks', 'readonly').objectStore('chunks').count()
					request.onsuccess = () => resolve(request.result)
					request.onerror = () => reject(request.error)
				}
				open.onerror = () => reject(open.error)
			}),
	)
}

test('Test A: network loss during recording, recovery after reconnect', async ({ page, context }) => {
	const fixture = seed()
	await startRecording(page, fixture.token)

	// record online long enough for a few chunks to upload
	await page.waitForTimeout(CHUNK_MS * 3)

	// network dies mid-recording
	await context.setOffline(true)
	await expect(page.getByText('Network unavailable', { exact: false })).toBeVisible({
		timeout: 20_000,
	})

	// recording continues locally while offline
	const before = await localChunkCount(page)
	await page.waitForTimeout(CHUNK_MS * 4)
	const after = await localChunkCount(page)
	expect(after).toBeGreaterThan(before)

	// network returns; pending chunks drain
	await context.setOffline(false)

	// finish and synchronize
	await page.getByRole('button', { name: 'Finish recording' }).click()
	await page.getByRole('button', { name: 'Yes, finish and synchronize' }).click()
	await expect(page.getByText('Recording synchronized')).toBeVisible({ timeout: 90_000 })

	// server-side verification: complete, no missing chunks, audio validated
	const recording = await latestRecordingState(page)
	expect(recording.state).toBe('AUDIO_READY')
	expect(recording.received_chunks).toBe(recording.total_chunks)
})

test('Test C: browser reload mid-recording; chunks recovered and synchronized', async ({ page }) => {
	const fixture = seed()
	await startRecording(page, fixture.token)

	// persist several chunks, then simulate a crash/reload
	await page.waitForTimeout(CHUNK_MS * 4)
	await page.reload()

	// recovery screen appears with the persisted chunks
	await expect(page.getByText('Recovered recording')).toBeVisible({ timeout: 20_000 })
	await expect(page.getByText('Recovered recording fully synchronized', { exact: false })).toBeVisible({
		timeout: 90_000,
	})
	await page.getByRole('button', { name: 'Continue' }).click()
	await expect(page.getByText('Microphone test')).toBeVisible()

	const recording = await latestRecordingState(page)
	expect(recording.state).toBe('AUDIO_READY')
	expect(recording.received_chunks).toBe(recording.total_chunks)
})

async function latestRecordingState(
	page: Page,
): Promise<{ state: string; received_chunks: number; total_chunks: number }> {
	// the recorder session token survives in localStorage; reuse it for the status API
	return page.evaluate(async () => {
		const stored = JSON.parse(localStorage.getItem('citizens-recorder-session') ?? '{}')
		const recordings: Array<{ recordingId: string }> = await new Promise((resolve, reject) => {
			const open = indexedDB.open('citizens-recorder')
			open.onsuccess = () => {
				const request = open.result
					.transaction('recordings', 'readonly')
					.objectStore('recordings')
					.getAll()
				request.onsuccess = () => resolve(request.result)
				request.onerror = () => reject(request.error)
			}
		})
		const real = recordings.filter((r) => r.recordingId !== '__selftest__')
		const latest = real[real.length - 1]
		const response = await fetch(`/api/v1/public/recorder/recordings/${latest.recordingId}`, {
			headers: { Authorization: `Bearer ${stored.session_token}` },
		})
		return response.json()
	})
}
