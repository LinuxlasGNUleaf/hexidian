import asyncio
import logging
import os

import requests
import websockets
import json


class Guru3Mgr:
    def __init__(self, config: dict, input_queue: asyncio.Queue):
        self.config = config['guru3']
        self.logger = logging.getLogger(__name__)
        self.ws = None
        if not os.path.exists(self.config['token_file']):
            raise FileNotFoundError("Token File for Guru3 manager not found!")
        with open(self.config['token_file'], 'r') as file:
            self.api_header = {'ApiKey': file.read().strip()}
        # URI  building
        port = self.config.get('port', '')
        port = ':' + str(port) if port else port
        tls = 's' if self.config['tls'] else ''
        self.rest_url = f'http{tls}://{self.config["host"]}{port}/api/event/1/messages'
        self.ws_url = f'ws{tls}://{self.config["host"]}{port}/status/stream/'

        self.events = input_queue
        self.active_event_ids = set()

    async def run(self):
        try:
            self.ws = await websockets.connect(uri=self.ws_url, extra_headers=self.api_header)
        except asyncio.TimeoutError:
            raise ConnectionError("Guru3 host invalid!")
        # pull events waiting in queue
        await self.request_events()
        # start listening for events on websocket
        await self.handle_incoming_messages()

    async def handle_incoming_messages(self):
        try:
            while True:
                message = await self.ws.recv()
                js = json.loads(message)
                action = js['action']
                if action != 'messagecount':
                    self.logger.error(f"UNKNOWN ACTION! '{action}'")
                    raise KeyError(f"UNKNOWN ACTION! '{action}'")

                self.logger.info(f'Guru3 queue has {js["queuelength"]} events.')

                # query events from Guru3 via REST api
                await self.request_events()
        except asyncio.CancelledError:
            self.logger.info('Received termination signal, closing GURU3 WEBSOCKET...')
        finally:
            await self.ws.close()
            self.logger.info('GURU3 WEBSOCKET closed.')

    async def request_events(self):
        self.logger.info("Retrieving events from Guru3...")
        received_events = json.loads(requests.get(self.rest_url, headers=self.api_header).content)
        for event in received_events:
            if event['id'] in self.active_event_ids:
                continue
            await self.events.put(event)
            self.active_event_ids.add(event['id'])
        self.logger.info("Request of events complete.")

    def mark_event_complete(self, event_ids: int | list):
        if isinstance(event_ids, int):
            event_ids = [event_ids]
        id_string = f"[{','.join([str(ev_id) for ev_id in event_ids])}]"
        resp = requests.post(self.rest_url,
                             headers={**self.api_header, "Content-Type": "multipart/form-data; boundary=-"},
                             data=f"Content-Disposition: form-data; name=\"acklist\"\r\n\r\n{id_string}\r\n---")
        if resp.status_code != 200:
            self.logger.error(f'Marking of {id_string} as done failed: {resp} {resp.content}')
        else:
            self.logger.info(f'Marked {id_string} as complete.')
            for ev_id in event_ids:
                if ev_id in self.active_event_ids:
                    self.active_event_ids.remove(ev_id)
