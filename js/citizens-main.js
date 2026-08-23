/*
 * Milestone 0 application shell for the Citizens top-menu page.
 * Injected by AppAPI into the embedded template (<div id="content"></div>).
 * Replaced by the Vue organizer SPA in Milestone 1.
 */
(function () {
	'use strict'

	// Derive the ExApp base URL from this script's own src, so it works both
	// via /apps/app_api/proxy/citizens/... (no rewrite configured) and via a
	// /exapps/citizens/... web-server rewrite where one exists.
	var script = document.currentScript
	var BASE = (script && script.src)
		? script.src.replace(/\/js\/citizens-main\.js.*$/, '')
		: '/exapps/citizens'

	function el(tag, style, text) {
		var node = document.createElement(tag)
		if (style) node.setAttribute('style', style)
		if (text) node.textContent = text
		return node
	}

	function render() {
		var content = document.getElementById('content') || document.body
		content.innerHTML = ''

		var wrap = el('div', 'max-width: 640px; margin: 40px auto; padding: 0 20px; font-family: var(--font-face, sans-serif); color: var(--color-main-text, #222);')
		wrap.appendChild(el('h2', 'margin-bottom: 4px;', 'Nextcloud Citizens'))
		wrap.appendChild(el('p', 'color: var(--color-text-maxcontrast, #666); margin-top: 0;', 'Citizens’ assemblies: offline-first table recording, transcription and reviewed analysis.'))

		var card = el('div', 'margin-top: 24px; padding: 16px 20px; border: 1px solid var(--color-border, #ddd); border-radius: var(--border-radius-large, 10px); background: var(--color-main-background, #fff);')
		card.appendChild(el('h3', 'margin-top: 0;', 'System health'))
		var status = el('div', '', 'Checking…')
		card.appendChild(status)
		wrap.appendChild(card)
		content.appendChild(wrap)

		fetch(BASE + '/api/v1/health', { headers: { requesttoken: (window.OC && OC.requestToken) || '' } })
			.then(function (res) {
				if (!res.ok) throw new Error('HTTP ' + res.status)
				return res.json()
			})
			.then(function (health) {
				status.innerHTML = ''
				var rows = [
					['Application', health.app + ' ' + health.version],
					['Status', health.status],
					['Database', health.database],
					['Storage', health.storage],
					['Free disk', health.disk_free_gb != null ? health.disk_free_gb + ' GB' : 'unknown'],
				]
				rows.forEach(function (row) {
					var line = el('div', 'display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid var(--color-border, #eee);')
					line.appendChild(el('span', 'color: var(--color-text-maxcontrast, #666);', row[0]))
					line.appendChild(el('strong', '', String(row[1])))
					status.appendChild(line)
				})
			})
			.catch(function (err) {
				status.textContent = 'Health check failed: ' + err.message
			})
	}

	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', render)
	} else {
		render()
	}
})()
