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

import websockets
from vosk import KaldiRecognizer, Model, SpkModel

# path -> loaded Model. Kaldi models are read-only once built and safe to share
# across recognizers, so one load serves every connection using that language.
_MODEL_CACHE = {}
_MODEL_LOCK = asyncio.Lock()


async def load_model(path, loop):
    """Load a model once, without blocking the event loop.

    Model() is seconds of blocking C. Holding the lock across the executor call
    means concurrent connections for the same new language wait for one load
    instead of starting several.
    """
    async with _MODEL_LOCK:
        if path not in _MODEL_CACHE:
            logging.info("Loading model %s", path)
            _MODEL_CACHE[path] = await loop.run_in_executor(None, Model, path)
            logging.info("Loaded model %s", path)
        return _MODEL_CACHE[path]


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
    conn_model = model
    model_changed = False

    logging.info('Connection from %s', websocket.remote_address)

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
                conn_model = await load_model(jobj['model'], loop)
                model_changed = True
            if 'words' in jobj:
                show_words = bool(jobj['words'])
            if 'max_alternatives' in jobj:
                max_alternatives = int(jobj['max_alternatives'])
            continue

        # Create the recognizer, word list is temporary disabled since not every model supports it
        if not rec or model_changed:
            model_changed = False
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

    loop = asyncio.get_running_loop()
    # the default, used by any session that does not name a model
    model = await load_model(args.model_path, loop)
    spk_model = SpkModel(args.spk_model_path) if args.spk_model_path else None

    pool = concurrent.futures.ThreadPoolExecutor((os.cpu_count() or 1))

    async with websockets.serve(recognize, args.interface, args.port):
        logging.info("Listening on %s:%d", args.interface, args.port)
        await asyncio.Future()


if __name__ == '__main__':
    asyncio.run(start())
