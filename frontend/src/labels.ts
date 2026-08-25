// SPDX-FileCopyrightText: 2026 Philip <philip@decentsoftwa.re>
// SPDX-License-Identifier: AGPL-3.0-or-later
/* Deliberation-report vocabulary for finding types — shared by the organizer
 * app and the recorder report screen. DB type values never change; only how
 * they are presented. Mirrors citizens/services/report.py. */

export const TYPE_ORDER = [
	'proposal',
	'agreement',
	'disagreement',
	'concern',
	'question',
	'minority_position',
	'new_idea',
] as const

export const TYPE_LABELS: Record<string, string> = {
	proposal: 'Proposal',
	agreement: 'Point of consensus',
	disagreement: 'Point of divergence',
	concern: 'Concern',
	question: 'Open question',
	minority_position: 'Minority position',
	new_idea: 'Emerging idea',
}

export const TYPE_LABELS_PLURAL: Record<string, string> = {
	proposal: 'Proposals',
	agreement: 'Points of consensus',
	disagreement: 'Points of divergence',
	concern: 'Concerns raised',
	question: 'Open questions',
	minority_position: 'Minority positions',
	new_idea: 'Emerging ideas',
}

export function groupByType<T extends { type: string }>(
	findings: T[],
): Array<{ type: string; label: string; findings: T[] }> {
	const groups: Array<{ type: string; label: string; findings: T[] }> = []
	for (const type of TYPE_ORDER) {
		const matching = findings.filter((f) => f.type === type)
		if (matching.length) groups.push({ type, label: TYPE_LABELS_PLURAL[type], findings: matching })
	}
	const leftover = findings.filter((f) => !TYPE_ORDER.includes(f.type as (typeof TYPE_ORDER)[number]))
	if (leftover.length) groups.push({ type: 'other', label: 'Other findings', findings: leftover })
	return groups
}
