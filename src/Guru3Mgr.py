import asyncio
import logging

import requests
import websockets
import json

import utils


class Guru3Mgr:
    def __init__(self, config: dict, event_queue: asyncio.Queue):
        self.config = config['guru3']
        self.logger = logging.getLogger(__name__)
        self.event_queue = event_queue
        self.event_queue_ids = set()

        # prepare URI and port for websocket and REST connection
        self.api_header = {'ApiKey': utils.read_password_env(self.config['password_env'])}
        port = self.config.get('port', '')
        port = ':' + str(port) if port else port
        tls = 's' if self.config['tls'] else ''
        self.rest_url = f'http{tls}://{self.config["host"]}{port}/api/event/1/messages'
        self.ws_url = f'ws{tls}://{self.config["host"]}{port}/status/stream/'
        self.ws = None

    async def run(self, request_lock: asyncio.Lock):
        # wait for other relevant managers to start
        await request_lock.acquire()
        self.logger.info('Requesting Guru3 events now.')
        # get events waiting in queue BEFORE websocket is live, so as not to trigger tons of requests
        await self.request_events()

        # start websocket
        try:
            self.ws = await websockets.connect(uri=self.ws_url, extra_headers=self.api_header)
            self.logger.info('Websocket connection established.')
        except asyncio.TimeoutError as exc:
            raise exc

        # start listening for events on websocket
        try:
            while True:
                # wait for new message and decode the JSON object
                message = await self.ws.recv()
                payload = json.loads(message)
                action = payload['action']
                if action != 'messagecount':
                    raise KeyError(f"UNKNOWN ACTION! '{action}'")

                # get message_count, and initiate get request if count > 0
                queue_length = payload['queuelength']
                if queue_length:
                    await self.request_events()
        except asyncio.CancelledError:
            pass
        finally:
            await self.ws.close()

    async def request_events(self):
        # GET request events from guru an decode them
        events = json.loads(requests.get(self.rest_url, headers=self.api_header).content)
        for event in events:
            if event['id'] in self.event_queue_ids:
                continue
            await self.event_queue.put(event)
            self.event_queue_ids.add(event['id'])

    def mark_event_complete(self, event_id: int):
        id_string = f'[{event_id}]'
        response = requests.post(self.rest_url,
                                 headers={**self.api_header, 'Content-Type': 'multipart/form-data; boundary=-'},
                                 data=f'Content-Disposition: form-data; name="acklist"\r\n\r\n{id_string}\r\n---')
        if response.status_code == 200:
            self.logger.info(f'Successfully marked event {event_id} as done in Guru3.')
            self.event_queue_ids.remove(event_id)
