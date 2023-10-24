import asyncio
import logging
import signal

import utils
from Guru3Mgr import Guru3Mgr
from OMMMgr import OMMMgr
from AsteriskMgr import AsteriskManager
from RegistrationMgr import RegistrationMgr


class EventHandler:
    def __init__(self, config):
        self.all_config = config
        self.own_config = config['event_handler']
        self.event_queue = asyncio.Queue()
        self.registration_queue = asyncio.Queue()

        self.guru3_mgr = Guru3Mgr(config, event_queue=self.event_queue)
        self.omm_mgr = OMMMgr(config)
        self.asterisk_mgr = AsteriskManager(config)
        self.registration_mgr = RegistrationMgr(config, self.registration_queue)

        self.logger = logging.getLogger(__name__)
        self.tasks = []

    def start(self):
        try:
            asyncio.run(self.run_tasks())
        except KeyboardInterrupt:
            for task in self.tasks:
                task.cancel()

    async def run_tasks(self):
        self.tasks = []
        request_lock = asyncio.Lock()
        await request_lock.acquire()

        # Registration Webserver task, starts a webserver to receive info from Asterisk
        self.tasks.append(asyncio.create_task(self.registration_mgr.run_server()))

        # Guru3 task, responsible for pulling events from frontend and marking them as done
        self.tasks.append(asyncio.create_task(self.guru3_mgr.run(request_lock=request_lock)))

        # EventHandler task, responsible for distributing incoming messages from Guru3
        # to the responsible backend manager (OMM or Asterisk DB)
        self.tasks.append(asyncio.create_task(self.distribute_guru3_messages()))

        # OMM task, responsible for establishing connection to Open Mobility Manager (DECT Manager)
        self.tasks.append(asyncio.create_task(self.omm_mgr.start_communication(request_lock=request_lock)))

        # Collect unbound PPNs task, collects unbound devices in OMM and assigns them temp accounts
        self.tasks.append(asyncio.create_task(self.find_unbound_pps()))

        # Handle Device Registrations
        self.tasks.append(asyncio.create_task(self.handle_device_registrations()))

        # SIGTERM handler
        asyncio.get_event_loop().add_signal_handler(signal.SIGTERM, self.handle_sigterm)

        self.logger.info('Running all configured tasks...')
        try:
            # gather all tasks
            await asyncio.gather(*self.tasks)

        except asyncio.CancelledError:
            self.asterisk_mgr.close()

    async def distribute_guru3_messages(self):
        try:
            self.logger.info('Listening for inbound Guru3 messages.')
            while True:
                # wait for new event in queue
                event = await self.event_queue.get()
                event_id = event['id']
                event_type = event['type']
                event_data = event['data']

                # some events can be safely ignored and reported back to Guru3 as done
                if event_type in self.own_config['ignored_msgtypes']:
                    self.guru3_mgr.mark_event_complete(event_id)
                    continue

                # =====> CALL EVENT PROCESSORS
                if event_type == 'UPDATE_EXTENSION':
                    self.do_update_extension(event_data)
                elif event_type == 'DELETE_EXTENSION':
                    self.do_delete_extension(event_data)
                elif event_type == 'RENAME_EXTENSION':
                    self.do_rename_extension(event_data)
                elif event_type == 'UNSUBSCRIBE_DEVICE':
                    self.do_unsubscribe_device(event_data)
                else:
                    raise RuntimeError(
                        f'Unknown event type occurred while EventHandler was processing event {event_id}')

                # mark event done in Guru3
                self.guru3_mgr.mark_event_complete(event_id)

        except asyncio.CancelledError:
            pass

    async def handle_device_registrations(self):
        try:
            self.logger.info('Now listening for device registrations.')
            while True:
                msg = await self.registration_queue.get()
                temp_number = msg['callerid']
                token = msg['token'][4:]
                # find OMM user with the temporary number
                from_user = self.omm_mgr.omm.find_user({'num': temp_number})
                # find OMM user with the corresponding token
                to_user = self.omm_mgr.omm.find_user({'hierarchy2': token})
                if not from_user:
                    self.logger.warning(f'Failed to fetch temp user (temp_num:{temp_number}) on registration! Can\'t transfer PP!')
                    continue
                if not to_user:
                    self.logger.warning(f'Failed to fetch OMM user (token:{token}) on registration! Can\'t transfer PP!')
                    continue
                self.logger.info(f'Transferring PP (ppn:{from_user.ppn}) to OMM user (uid: {to_user.uid}, number: {to_user.num}.)')
                # transfer PP to real user
                self.omm_mgr.transfer_pp(int(from_user.uid), int(to_user.uid), int(from_user.ppn))
                # delete temporary user, both in OMM and Asterisk
                self.omm_mgr.delete_user(temp_number)
                self.asterisk_mgr.delete_user(temp_number)
        except asyncio.CancelledError:
            pass

    def do_update_extension(self, event_data):
        # extract event info
        ext_type = event_data['type']
        number = event_data['number']
        # trim name to length acceptable by OMM
        event_data['name'] = event_data['name'][:19]

        # if new extension type is not DECT or SIP, determine whether the old user needs to be deleted
        if ext_type not in ['DECT', 'SIP']:
            if number in self.omm_mgr.users:
                self.omm_mgr.delete_user(number)
            if self.asterisk_mgr.check_for_user(number):
                self.asterisk_mgr.delete_user(number)
            return

        # handle SIP extension update
        if ext_type == 'SIP':
            self.do_sip_extension_update(event_data)

        # handle DECT extension update
        elif ext_type == 'DECT':
            self.do_dect_extension_update(event_data)

    def do_sip_extension_update(self, event_data):
        number = event_data['number']
        sip_password = event_data['password']
        self.logger.info(f'Processing SIP extension update for number {number}.')

        # delete DECT extension, if present
        if number in self.omm_mgr.users:
            self.omm_mgr.delete_user(number=number)

        # SIP extension already exists, only a password update is required
        if self.asterisk_mgr.check_for_user(number=number):
            self.asterisk_mgr.update_password(number=number, new_password=sip_password)

        # new SIP extension
        else:
            self.asterisk_mgr.create_user(number=number, sip_password=sip_password)

    def do_dect_extension_update(self, event_data):
        name = event_data['name']
        number = event_data['number']
        token = event_data['token']
        self.logger.info(f'Processing DECT extension update for number {number}.')

        # if user already exists, update user entry
        if number in self.omm_mgr.users:
            self.logger.info(f'Updating OMM user {number}.')
            self.omm_mgr.update_user_info(number=number, name=name, token=token)

        # else, create a new user
        else:
            self.logger.info(f'Creating new Asterisk and OMM user for number {number}.')
            # make sure that any existing SIP user is being deleted beforehand
            if self.asterisk_mgr.check_for_user(number=number):
                self.logger.warning('Deleting existing Asterisk user that would clash with the newly created one!')
                self.asterisk_mgr.delete_user(number=number)

            sip_password = utils.create_password('alphanum', self.all_config['asterisk']['password_length'])
            self.asterisk_mgr.create_user(number=number, sip_password=sip_password)
            self.omm_mgr.create_user(name=name, number=number, token=token, sip_user=number, sip_password=sip_password)

    def do_delete_extension(self, event_data):
        number = event_data['number']
        if self.asterisk_mgr.check_for_user(number):
            self.logger.info(f'Deleting Asterisk user {number}.')
            self.asterisk_mgr.delete_user(number=number)
        if number in self.omm_mgr.users:
            self.logger.info(f'Deleting OMM user {number}.')
            self.omm_mgr.delete_user(number=number)

    def do_rename_extension(self, event_data):
        old_number = event_data['old_extension']
        new_number = event_data['new_extension']
        if self.asterisk_mgr.check_for_user(old_number):
            self.logger.info(f'Renaming extension from {old_number} to {new_number} in Asterisk.')
            self.asterisk_mgr.move_user(old_number, new_number)

        if old_number in self.omm_mgr.users:
            self.logger.info(f'Renaming extension from {old_number} to {new_number} in OMM.')
            self.omm_mgr.move_user(old_number, new_number)

    def do_unsubscribe_device(self, event_data):
        # TODO: SIP MAGIC!
        # TODO: OMM MAGIC!
        return

    async def find_unbound_pps(self):
        try:
            self.logger.info('Now looking for unbound PPs.')
            while True:
                for device in self.omm_mgr.omm.get_devices():
                    if device.relType != 'Unbound':
                        continue
                    temp_number = f'010' + utils.create_password('num', self.all_config['asterisk']['temp_num_length'])
                    temp_password = utils.create_password('alphanum', self.all_config['asterisk']['password_length'])
                    while self.asterisk_mgr.check_for_user(temp_number):
                        temp_number = f'010' + utils.create_password('num',
                                                                     self.all_config['asterisk']['temp_num_length'])
                    self.logger.info(f'Assigning unbound device ({device.ppn}) to a temporary user ({temp_number})')
                    omm_user = self.omm_mgr.create_user(name='Unbound Handset', number=temp_number,
                                                        sip_user=temp_number,
                                                        sip_password=temp_password)
                    self.omm_mgr.omm.attach_user_device(uid=int(omm_user.uid), ppn=int(device.ppn))
                    self.asterisk_mgr.create_user(number=temp_number, sip_password=temp_password, temporary=True)

                await asyncio.sleep(self.own_config['collect_ppns_interval'])
        except asyncio.CancelledError:
            pass

    def handle_sigterm(self):
        self.logger.info('Received SIGTERM, trying graceful shutdown...')
        for task in self.tasks:
            task.cancel()
        self.asterisk_mgr.close()
        self.logger.info('Shutdown complete, goodbye.')

