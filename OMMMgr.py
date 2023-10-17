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
            # professional way of stopping the Mgr from logging out instantly for the time being
            await asyncio.sleep(10000)
        except asyncio.CancelledError:
            pass
        finally:
            self.omm.logout()
            self.logger.info('Successfully logged out of OMM.')
