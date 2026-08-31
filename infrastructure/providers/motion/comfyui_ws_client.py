import asyncio
import json
import urllib.request
import urllib.error
import websockets
from typing import Dict, Any, Callable

class ComfyUIWsClient:
    def __init__(self, server_address: str):
        self.server_address = server_address

    async def queue_prompt_and_wait(self, prompt: Dict[str, Any], client_id: str, progress_callback: Callable[[float], None]) -> Dict[str, Any]:
        p = {"prompt": prompt, "client_id": client_id}
        data = json.dumps(p).encode('utf-8')
        req = urllib.request.Request(f"http://{self.server_address}/prompt", data=data)

        try:
            response = urllib.request.urlopen(req)
            response_data = json.loads(response.read())
            prompt_id = response_data['prompt_id']
        except urllib.error.URLError as e:
            raise RuntimeError(f"Failed to queue prompt: {e}")

        async with websockets.connect(f"ws://{self.server_address}/ws?clientId={client_id}") as websocket:
            while True:
                out = await websocket.recv()
                if isinstance(out, str):
                    message = json.loads(out)
                    if message['type'] == 'executing':
                        data = message['data']
                        if data['node'] is None and data['prompt_id'] == prompt_id:
                            break # Execution is done
                    elif message['type'] == 'progress':
                        data = message['data']
                        if data['prompt_id'] == prompt_id and progress_callback:
                            progress_callback(data['value'] / data['max'])

        req = urllib.request.Request(f"http://{self.server_address}/history/{prompt_id}")
        response = urllib.request.urlopen(req)
        history = json.loads(response.read())
        return history[prompt_id]
