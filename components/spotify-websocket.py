import asyncio
import websockets
import requests
import json
from collections import Counter


def get_spotify_ws_url():
    try:
        response = requests.get("http://localhost:9222/json", timeout=2)
        targets = response.json()
        for target in targets:
            if "spotify" in target.get("title", "").lower() or target.get("type") == "page":
                if "webSocketDebuggerUrl" in target:
                    return target.get("webSocketDebuggerUrl")
        return None
    except Exception as e:
        print(
            f"Error: Ensure Spotify is running with --remote-debugging-port=9222. {e}")
        return None


async def get_enhanced_info():
    ws_url = get_spotify_ws_url()
    if not ws_url:
        return

    async with websockets.connect(ws_url) as websocket:
        await websocket.send(json.dumps({"id": 1, "method": "Runtime.enable"}))

        js_code = '''
        (() => {
            // 1. Basic Meta
            const track = document.querySelector('[data-testid="context-item-info-title"]')?.innerText;
            const artist = document.querySelector('[data-testid="context-item-info-subtitles"]')?.innerText;

            // 2. Playback Timing
            const elapsed = document.querySelector('[data-testid="playback-position"]')?.innerText;
            const duration = document.querySelector('[data-testid="playback-duration"]')?.innerText;

            // 3. Progress Percentage (for a progress bar)
            const progressBar = document.querySelector('.playback-bar .progress-bar__fg');
            const progressPct = progressBar ? progressBar.style.width : "0%";

            // 4. Active Lyric Tracking
            // Note: This only works if the Lyrics view is active in the Spotify UI
            const activeLine = document.querySelector('[data-testid="lyrics-line"][data-active="true"]')
                            || document.querySelector('[class*="lyrics-line-active"]');

            return {
                track, artist,
                playback: { elapsed, duration, progress: progressPct },
                active_lyric: activeLine ? activeLine.innerText : "Lyrics panel not visible"
            };
        })()
        '''

        while True:
            await websocket.send(json.dumps({
                "id": 2, "method": "Runtime.evaluate",
                "params": {"expression": js_code, "returnByValue": True}
            }))

            resp = json.loads(await websocket.recv())
            if "result" in resp and "result" in resp["result"]:
                val = resp["result"]["result"]["value"]
                print(
                    f"[{val['playback']['elapsed']} / {val['playback']['duration']}] {val['track']}")
                print(f"Lyric: {val['active_lyric']}")
                print("-" * 20)

            await asyncio.sleep(0.1)  # lower sleep for better "live" tracking


def get_active_lyric(lines):
    if not lines or len(lines) < 3:
        return "† [open panel] †"

    # blank lines have 3 terms
    counter = Counter(l['className']
                      for l in lines if l['className'].count(' ') != 2)
    # TODO: second last line doesn't work aaaaaaabc (?)
    uniques = [d for d in lines if counter[d['className']] == 1]
    print(uniques)
    if uniques:
        # we don't want to do this when it's the second last line
        result = uniques[-1]
        return result['text']
    else:
        return '†††'  # start/end of song


async def get_track_info():
    ws_url = get_spotify_ws_url()
    if not ws_url:
        return

    async with websockets.connect(ws_url) as websocket:
        await websocket.send(json.dumps({"id": 1, "method": "Runtime.enable"}))

        js_code = '''
        (() => {
            const lines = Array.from(document.querySelectorAll('[data-testid="lyrics-line"]'));

            if (lines.length === 0) {
                return { error: "No lyric lines found. Is the lyrics panel open?" };
            }

            // Map every line to its text and its full class attribute
            const debugInfo = lines.map((line, index) => {
                return {
                    index: index,
                    text: line.innerText.trim(),
                    className: line.className
                };
            });

            return debugInfo;
        })()
        '''

        print("Press Ctrl+C to stop.\n")
        last = ''

        while True:
            payload = {
                "id": 2,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": js_code,
                    "returnByValue": True
                }
            }
            await websocket.send(json.dumps(payload))

            response = await websocket.recv()
            data = json.loads(response)

            if "result" in data and "result" in data["result"]:
                # can't seem to get the changed value out in the injected JS so handle it here instead
                lines = data["result"]["result"]["value"]
                if last != (active := get_active_lyric(lines)):
                    last = active
                    print(active)

            await asyncio.sleep(1)  # 0.005 for "realtime"

if __name__ == "__main__":
    try:
        asyncio.run(get_track_info())
        # asyncio.run(get_enhanced_info())
    except KeyboardInterrupt:
        pass
