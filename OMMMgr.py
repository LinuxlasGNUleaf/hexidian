import asyncio
import logging
from python_mitel.OMMClient import OMMClient


class OMMMgr:
    def __init__(self, config: dict):
        self.config = config['omm']
        self.logger = logging.getLogger(__name__)
        self.omm = OMMClient(host=self.config['host'], port=self.config['port'])
        with open(self.config['token_file'], 'r') as token_file:
            self.user, self.password = token_file.read().split('\n')

    async def start_communication(self):
        try:
            self.omm.login(user=self.user, password=self.password)
            self.logger.info('Successfully logged into OMM')
            self.logger.info("OMM: " + self.omm.get_systemname())
            self.logger.info('Allowing wildcard subscription...')
            while True:
                self.logger.debug(
                    f'Result of wildcard subscription action: {self.omm.set_subscription("wildcard", 120)}')
                await asyncio.sleep(110)
        except asyncio.CancelledError:
            pass
        finally:
            self.omm.logout()
            self.logger.info('Successfully logged out of OMM.')

    async def handle_event(self, event):
        return True
