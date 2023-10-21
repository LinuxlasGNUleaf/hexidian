import asyncio
import logging

from Guru3Mgr import Guru3Mgr
from OMMMgr import OMMMgr
from AsteriskMgr import AsteriskManager


class EventHandler:
    def __init__(self, config):
        self.own_config = config['event_handler']
        self.guru3_input_queue = asyncio.Queue()
        self.guru3_mgr = Guru3Mgr(config, input_queue=self.guru3_input_queue)
        self.omm_mgr = OMMMgr(config)
        self.asterisk_mgr = AsteriskManager(config)
        self.logger = logging.getLogger(__name__)
        self.tasks = []

    def start(self):
        try:
            asyncio.run(self.run_tasks())
        except KeyboardInterrupt:
            self.logger.info("Cancelling tasks...")
            for task in self.tasks:
                task.cancel()

    async def run_tasks(self):
        self.tasks = []

        # Guru3 task, responsible for pulling events from frontend and marking them as done
        self.tasks.append(asyncio.create_task(self.guru3_mgr.run()))

        # EventHandler task, responsible for distributing incoming messages from Guru3
        # to the responsible backend manager (OMM or Asterisk DB)
        self.tasks.append(asyncio.create_task(self.distribute_guru3_messages()))

        # OMM task, responsible for establishing connection to Open Mobility Manager (DECT Manager)
        self.tasks.append(asyncio.create_task(self.omm_mgr.start_communication()))

        try:
            # gather all tasks
            await asyncio.gather(*self.tasks)
        except asyncio.CancelledError:
            self.asterisk_mgr.close()

    async def distribute_guru3_messages(self):
        try:
            while True:
                # wait for new event in queue
                event = await self.guru3_input_queue.get()
                event_id = event['id']
                event_type = event['type']
                event_data = event['data']

                # some events can be safely ignored and reported back to Guru3 as done
                if event_type in self.own_config['ignored_msgtypes']:
                    self.guru3_mgr.mark_event_complete(event_id)
                    self.logger.info(f'{event_type} ignored internally and reported as processed to Guru3.')
                    continue

                # =====> CALL EVENT PROCESSORS
                if event_type == 'UPDATE_EXTENSION':
                    ok = self.do_update_extension(event_data)
                elif event_type == 'DELETE_EXTENSION':
                    ok = self.do_delete_extension(event_data)
                elif event_type == 'RENAME_EXTENSION':
                    ok = self.do_rename_extension(event_data)
                elif event_type == 'UNSUBSCRIBE_DEVICE':
                    ok = self.do_unsubscribe_device(event_data)
                else:
                    ok = False

                if not ok:
                    self.logger.error(f'Event could not be processed! ' + str(event))
                    raise RuntimeError(f'Error while EventHandler was processing event {event_id} ({event_type})')

                # mark event done in Guru3
                self.guru3_mgr.mark_event_complete(event_id)

        except asyncio.CancelledError:
            self.logger.info('Received termination signal, GURU3_DISTRIBUTOR closed.')

    def do_update_extension(self, event_data):
        # extract event info
        ext_type = event_data['type']
        number = event_data['number']
        name = event_data['name'][:19]

        # if new extension type is not DECT or SIP, determine whether the old corresponding DECT extension needs to be deleted
        if ext_type not in ['DECT', 'SIP']:
            self.logger.warning('Extension is neither DECT nor SIP, ignoring!')
            return True

        # handle SIP extension update
        if ext_type == 'SIP':
            # delete DECT extension, if present
            if number in self.omm_mgr.users:
                self.logger.info("SIP extension registration while a OMM user with the same number is registered!")
                self.omm_mgr.delete_user(number)
            # TODO: SIP MAGIC!
            return True

        # handle DECT extension update
        elif ext_type == 'DECT':
            # if user already exists, update user entry
            if number in self.omm_mgr.users:
                self.logger.info('User for this number already present, updating user info instead...')
                # TODO: SIP MAGIC!
                # TODO: change SIP password to actual password!
                self.omm_mgr.update_user(name=name, number=number, sip_user=number, sip_password=number)
                return True

            # else, create a new user
            else:
                self.logger.info(f'Attempting to create new user with number {number} in Asterisk and OMM...')
                sip_password = self.asterisk_mgr.create_user(number)
                self.omm_mgr.create_user(name=name, number=number, sip_user=number, sip_password=sip_password)
                return True

    def do_delete_extension(self, event_data):
        number = event_data['number']
        # TODO: SIP MAGIC!
        self.omm_mgr.delete_user(number)
        return True

    def do_rename_extension(self, event_data):
        old_number = event_data['old_extension']
        new_number = event_data['new_extension']
        # TODO: SIP MAGIC!
        self.omm_mgr.move_user(old_number, new_number)
        return True

    def do_unsubscribe_device(self, event_data):
        # TODO: SIP MAGIC!
        # TODO: OMM MAGIC!
        return True
