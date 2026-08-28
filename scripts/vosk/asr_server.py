#!/usr/bin/env python3
# Patched copy of vosk-server's websocket/asr_server.py.
# Upstream: https://github.com/alphacep/vosk-server (Apache-2.0)
#
# Two changes, both about serving SEVERAL models from ONE server so a session
# can choose its language. Upstream assumes one model per process:
#
#   1. `{"config": {"model": ...}}` assigned the module-level `model`, so one
#      connection switching language changed it for every other connection.
#      Two assemblies running in different languages could take each other's
#      model. The chosen model is now a local, per-connection.
#   2. Every switch called Model(path), re-reading the model from disk. Twenty
#      tables opening caption sockets for one round meant twenty loads. Models
#      are now cached by path and loaded once, off the event loop.
#
# Everything else is upstream, unmodified. Drop the mount in scripts/vosk-up.sh
# to fall back to stock behaviour.

import asyncio
import concurrent.futures
import json
import logging
import os
import sys
import time
from collections import OrderedDict

import websockets
from vosk import KaldiRecognizer, Model, SpkModel

# path -> loaded Model. Kaldi models are read-only once built and safe to share
# across recognizers, so one load serves every connection using that language.
#
# Bounded and idle-evicted: an assembly uses one language, and the next one may
# be days later in another. Without this a model loaded once sat in memory
# forever — ~300 MB for a small model, on a host that does not have it spare.
_MODEL_CACHE = OrderedDict()
_MODEL_USERS = {}  # path -> live connection count; never evict one in use

# Created inside the running loop, never at import. On this image's Python 3.9
# asyncio.Lock() binds to whatever loop exists at construction, and an
# import-time lock belongs to the wrong one — which only fails when two
# connections actually contend for it, i.e. exactly when two tables record at
# the same time. Uncontended acquires never await, so it looks fine until it
# matters.
_MODEL_LOCK = None


def _model_lock():
    global _MODEL_LOCK
    if _MODEL_LOCK is None:
        _MODEL_LOCK = asyncio.Lock()
    return _MODEL_LOCK

# how many languages can be live at once, not a memory budget: idle
# eviction is what reclaims memory. Too small and an overlap makes the
# next table in the evicted language load a SECOND copy of it.
CACHE_SIZE = int(os.environ.get("VOSK_MODEL_CACHE", 2))
IDLE_SECONDS = float(os.environ.get("VOSK_MODEL_IDLE_SECONDS", 1800))
SWEEP_SECONDS = 60.0
_IDLE_SINCE = {}  # path -> when its last connection closed


async def load_model(path, loop):
    """Load a model once, without blocking the event loop.

    Model() is seconds of blocking C. Holding the lock across the executor call
    means concurrent connections for the same new language wait for one load
    instead of starting several.
    """
    async with _model_lock():
        if path in _MODEL_CACHE:
            _MODEL_CACHE.move_to_end(path)
        else:
            logging.info("Loading model %s", path)
            _MODEL_CACHE[path] = await loop.run_in_executor(None, Model, path)
            logging.info("Loaded model %s", path)
            _evict_locked(keep=path)
        _MODEL_USERS[path] = _MODEL_USERS.get(path, 0) + 1
        _IDLE_SINCE.pop(path, None)
        return _MODEL_CACHE[path]


async def release_model(path):
    """One connection finished with this model."""
    if not path:
        return
    async with _model_lock():
        remaining = _MODEL_USERS.get(path, 1) - 1
        if remaining > 0:
            _MODEL_USERS[path] = remaining
        else:
            _MODEL_USERS.pop(path, None)
            _IDLE_SINCE[path] = time.monotonic()


def _evict_locked(keep=None):
    """Drop least-recently-used models above the cap. Call with the lock held.

    Only models with no live connection are dropped, so a long round cannot
    have its model pulled while it is still recording — that would reload it
    into a SECOND copy and double memory instead of saving any. Dropping the
    reference is safe regardless: a recognizer holds its own, so Python frees
    the memory when the last connection using it closes.
    """
    for path in list(_MODEL_CACHE):
        if len(_MODEL_CACHE) <= max(CACHE_SIZE, 1):
            return
        if path == keep or _MODEL_USERS.get(path):
            continue
        _MODEL_CACHE.pop(path, None)
        _IDLE_SINCE.pop(path, None)
        logging.info("Unloaded model %s (cache limit %d)", path, CACHE_SIZE)


async def sweep_idle_models():
    """Free a model nobody has used for a while, so memory returns to baseline
    between assemblies instead of holding one overnight."""
    while True:
        await asyncio.sleep(SWEEP_SECONDS)
        now = time.monotonic()
        async with _model_lock():
            for path, since in list(_IDLE_SINCE.items()):
                if _MODEL_USERS.get(path) or now - since < IDLE_SECONDS:
                    continue
                _MODEL_CACHE.pop(path, None)
                _IDLE_SINCE.pop(path, None)
                logging.info("Unloaded idle model %s", path)


def process_chunk(rec, message):
    if message == '{"eof" : 1}':
        return rec.FinalResult(), True
    if message == '{"reset" : 1}':
        return rec.FinalResult(), False
    elif rec.AcceptWaveform(message):
        return rec.Result(), False
    else:
        return rec.PartialResult(), False


async def recognize(websocket, path):
    global spk_model
    global args
    global pool

    loop = asyncio.get_running_loop()
    rec = None
    phrase_list = None
    sample_rate = args.sample_rate
    show_words = args.show_words
    max_alternatives = args.max_alternatives
    # per-connection, so another session cannot change this one's language
    conn_model = None
    conn_model_path = None
    model_changed = False

    logging.info('Connection from %s', websocket.remote_address)

    try:
        while True:

            message = await websocket.recv()

            # Load configuration if provided
            if isinstance(message, str) and 'config' in message:
                jobj = json.loads(message)['config']
                logging.info("Config %s", jobj)
                if 'phrase_list' in jobj:
                    phrase_list = jobj['phrase_list']
                if 'sample_rate' in jobj:
                    sample_rate = float(jobj['sample_rate'])
                if 'model' in jobj:
                    previous = conn_model_path
                    conn_model_path = jobj['model']
                    conn_model = await load_model(conn_model_path, loop)
                    if previous and previous != conn_model_path:
                        await release_model(previous)
                    model_changed = True
                if 'words' in jobj:
                    show_words = bool(jobj['words'])
                if 'max_alternatives' in jobj:
                    max_alternatives = int(jobj['max_alternatives'])
                continue

            # Create the recognizer, word list is temporary disabled since not every model supports it
            if not rec or model_changed:
                model_changed = False
                if conn_model is None:
                    # no model named: fall back to the server's default, loaded
                    # on demand like any other so nothing is pinned at startup
                    conn_model_path = args.model_path
                    conn_model = await load_model(conn_model_path, loop)
                if phrase_list:
                    rec = KaldiRecognizer(
                        conn_model, sample_rate, json.dumps(phrase_list, ensure_ascii=False)
                    )
                else:
                    rec = KaldiRecognizer(conn_model, sample_rate)
                rec.SetWords(show_words)
                rec.SetMaxAlternatives(max_alternatives)
                if spk_model:
                    rec.SetSpkModel(spk_model)

            response, stop = await loop.run_in_executor(pool, process_chunk, rec, message)
            await websocket.send(response)
            if stop:
                break
    finally:
        # must run however the connection ends — a dropped phone must not leave
        # the model pinned in memory forever
        await release_model(conn_model_path)


async def start():

    global model
    global spk_model
    global args
    global pool

    logging.basicConfig(level=logging.INFO)

    args = type('', (), {})()

    args.interface = os.environ.get('VOSK_SERVER_INTERFACE', '0.0.0.0')
    args.port = int(os.environ.get('VOSK_SERVER_PORT', 2700))
    args.model_path = os.environ.get('VOSK_MODEL_PATH', 'model')
    args.spk_model_path = os.environ.get('VOSK_SPK_MODEL_PATH')
    args.sample_rate = float(os.environ.get('VOSK_SAMPLE_RATE', 8000))
    args.max_alternatives = int(os.environ.get('VOSK_ALTERNATIVES', 0))
    args.show_words = bool(os.environ.get('VOSK_SHOW_WORDS', True))

    if len(sys.argv) > 1:
        args.model_path = sys.argv[1]

    # Nothing is loaded at startup: an assembly uses one language, and the next
    # may be days away in another. Models load on first use and are freed when
    # idle, so an idle server costs a few MB rather than a few hundred.
    model = None
    if not os.path.isdir(args.model_path):
        logging.warning(
            "Default model directory %s does not exist — sessions that do not "
            "name a model will fail", args.model_path,
        )
    spk_model = SpkModel(args.spk_model_path) if args.spk_model_path else None

    pool = concurrent.futures.ThreadPoolExecutor((os.cpu_count() or 1))

    async with websockets.serve(recognize, args.interface, args.port):
        logging.info(
            "Listening on %s:%d (models load on demand, cache %d, idle unload %ds)",
            args.interface, args.port, CACHE_SIZE, int(IDLE_SECONDS),
        )
        asyncio.create_task(sweep_idle_models())
        await asyncio.Future()


if __name__ == '__main__':
    asyncio.run(start())
