// SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
// SPDX-License-Identifier: AGPL-3.0-or-later
import { reactive } from 'vue'

export interface ToastItem {
	id: number
	text: string
	tone: 'success' | 'error'
}

let nextId = 1

export const toasts = reactive<ToastItem[]>([])

export function toast(text: string, tone: 'success' | 'error' = 'success'): void {
	const item: ToastItem = { id: nextId++, text, tone }
	toasts.push(item)
	setTimeout(() => {
		const index = toasts.findIndex((t) => t.id === item.id)
		if (index !== -1) toasts.splice(index, 1)
	}, 3500)
}
