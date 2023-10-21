import asyncio
import logging
import nest_asyncio

import aiohttp.web_request
from aiohttp import web

nest_asyncio.apply()


class RegistrationMgr:
    def __init__(self, config, queue: asyncio.Queue):
        self.config = config['registration']
        self.queue = queue
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.WARNING)
        self.app = web.Application()
        self.app.add_routes([web.post('/', self.handle_post), web.get('/', self.handle_get)])
        self.port = self.config['port']

    async def run_server(self):
        runner = aiohttp.web.AppRunner(self.app)
        await runner.setup()
        site = aiohttp.web.TCPSite(runner, port=self.config['port'])
        await site.start()

    async def handle_post(self, request: aiohttp.web_request.Request):
        if not request.content_type == 'application/json':
            return web.Response(text='NAK', status=400)
        json_payload = await request.json()
        if 'number' not in json_payload or 'token' not in json_payload:
            return web.Response(text='NAK', status=417)
        number = json_payload['number']
        token = json_payload['token']
        self.logger.info(f'Got new registration from Asterisk: number {number} called token {token}.')
        await self.queue.put(json_payload)
        return web.Response(text='ACK', status=200)

    async def handle_get(self, _):
        return web.Response(text='Use POST to send a JSON with the token number called.', status=400)
