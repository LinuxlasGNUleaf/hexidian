import logging

import aiohttp.web_request
from aiohttp import web


class RegistrationMgr:
    def __init__(self, config, registration_callback):
        self.config = config['registration']
        self.logger = logging.getLogger(__name__)
        self.registration_callback = registration_callback

        # create web app, configure routes
        self.app = web.Application()
        self.app.add_routes([web.post('/', self.handle_post), web.get('/', self.handle_get)])
        self.port = self.config['port']

    async def run_server(self):
        # wrap app in AppRunner
        runner = aiohttp.web.AppRunner(self.app)
        await runner.setup()

        # create site on configured port
        site = aiohttp.web.TCPSite(runner, port=self.config['port'])
        await site.start()
        self.logger.info('Startup complete.')

    async def handle_post(self, request: aiohttp.web_request.Request):
        # check request content type
        if not request.content_type == 'application/json':
            return web.Response(text='NAK', status=400)

        # retrieve and check json
        json_payload = await request.json()
        if 'callerid' not in json_payload or 'token' not in json_payload:
            return web.Response(text='NAK', status=417)

        # put json into queue and return 200 (OK)
        ok = self.registration_callback(json_payload['callerid'], json_payload['token'])
        if ok:
            return web.Response(text='extension added', status=200)
        else:
            return web.Response(text='NAK', status=404)

    async def handle_get(self, _):
        return web.Response(text='Use POST to send a JSON file with the token number called.', status=400)
