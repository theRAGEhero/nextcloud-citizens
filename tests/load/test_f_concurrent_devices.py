"""Test F: ~10 concurrent table devices (brief §56)."""
import concurrent.futures, hashlib, json, subprocess, time, urllib.request

BASE = "http://127.0.0.1:23100"

def api(method, path, data=None, token=None, raw=None, sha=None):
    headers = {}
    if token: headers["Authorization"] = f"Bearer {token}"
    if raw is not None:
        headers["Content-Type"] = "application/octet-stream"
        headers["X-Chunk-SHA256"] = sha
        body = raw
    elif data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode()
    else:
        body = None
    req = urllib.request.Request(BASE + path, data=body, method=method, headers=headers)
    return json.load(urllib.request.urlopen(req))

# seed 10 invites: use devtools seed 10 times (each creates its own assembly+table1)
seeds = []
for _ in range(10):
    out = subprocess.run(["sh", "/root/NextCloud-Citizen/scripts/browser-test-env.sh", "seed"],
                         capture_output=True, text=True, check=True)
    seeds.append(json.loads(out.stdout.strip()))

audio = subprocess.run(
    ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
     "-c:a", "libopus", "-b:a", "24k", "-f", "webm", "pipe:1"],
    capture_output=True, check=True).stdout
size = len(audio) // 5 + 1
chunks = [audio[i*size:(i+1)*size] for i in range(5) if audio[i*size:(i+1)*size]]

def device(seed):
    joined = api("POST", "/api/v1/public/join", {"token": seed["token"]})
    tok = joined["session_token"]
    rec = api("POST", "/api/v1/public/recorder/start",
              {"round_id": seed["round_id"], "mime_type": "audio/webm"}, token=tok)["recording_id"]
    for seq, blob in enumerate(chunks):
        api("POST", f"/api/v1/public/recorder/recordings/{rec}/chunks/{seq}",
            token=tok, raw=blob, sha=hashlib.sha256(blob).hexdigest())
        api("POST", "/api/v1/public/recorder/heartbeat",
            {"recording_active": True, "local_chunks": seq+1, "acked_chunks": seq+1, "storage_ok": True},
            token=tok)
    result = api("POST", f"/api/v1/public/recorder/recordings/{rec}/complete",
                 {"total_chunks": len(chunks)}, token=tok)
    assert result["missing_sequences"] == [], result
    for _ in range(60):
        status = api("GET", f"/api/v1/public/recorder/recordings/{rec}", token=tok)
        if status["state"] in ("AUDIO_READY", "AUDIO_INVALID"):
            return status
        time.sleep(1)
    return status

start = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
    results = list(pool.map(device, seeds))
elapsed = time.time() - start
states = [r["state"] for r in results]
ok = all(s == "AUDIO_READY" for s in states)
complete = all(r["received_chunks"] == r["total_chunks"] == len(chunks) for r in results)
print(f"devices=10 states={set(states)} all_chunks_complete={complete} elapsed={elapsed:.1f}s")
print("PASS" if ok and complete else "FAIL")
