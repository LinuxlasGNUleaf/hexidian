import logging
import time

import requests
import websocket
import json
import threading


class Guru3Mgr:
    def __init__(self, domain, token_file):
        with open(token_file, 'r') as file:
            self.api_header = {'ApiKey': file.read().strip()}
        self.rest_url = f'https://{domain}/api/event/1/messages'
        ws_url = f'wss://{domain}/status/stream/'
        self.logger = logging.getLogger(__name__)
        self.socket = websocket.WebSocketApp(url=ws_url, header=self.api_header,
                                             on_message=self.on_message)
        self.queue_len = 0
        self.events = {}

    def run(self):
        poke_thread = threading.Thread(target=self.poke_server)
        try:
            poke_thread.start()
            self.socket.run_forever()
        except KeyboardInterrupt:
            self.logger.info('Exiting.')
        poke_thread.join()

    def on_message(self, _, message):
        js = json.loads(message)
        action = js['action']
        if action != 'messagecount':
            self.logger.error(f"UNKNOWN ACTION! '{action}'")
            raise KeyError(f"UNKNOWN ACTION! '{action}'")

        self.queue_len = js['queuelength']
        self.logger.info(f'Guru3 queue has {self.queue_len} events.')

        # query events from Guru3 via REST api
        self.request_events()

    def poke_server(self):
        time.sleep(5)
        self.logger.info("Poking server with stick...")
        self.mark_event_complete(-1)

    def request_events(self):
        self.logger.info("Retrieving events from Guru3...")
        received_events = json.loads(requests.get(self.rest_url, headers=self.api_header).content)
        for event in received_events:
            if not event:
                self.logger.info(f"Skipping {event}...")
                continue
            self.events[event['id']] = event
        self.logger.info("Request of events complete.")

    def mark_event_complete(self, event_id):
        event_id = f"[{','.join(event_id)}]" if isinstance(event_id, list) else event_id
        resp = requests.post(self.rest_url,
                             headers={**self.api_header, "Content-Type": "multipart/form-data; boundary=-"},
                             data=f"Content-Disposition: form-data; name=\"acklist\"\r\n\r\n[{event_id}]\r\n---")
        if resp.status_code != 200:
            self.logger.error(f'Marking of {event_id} as done failed: {resp} {resp.content}')
        else:
            self.logger.info(f'Marked {event_id} as complete.')