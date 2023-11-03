import asyncio
import logging
import signal
from datetime import datetime
import string

import utils
from Guru3Mgr import Guru3Mgr
from OMMMgr import OMMMgr
from AsteriskMgr import AsteriskManager
from RegistrationMgr import RegistrationMgr

allowed_chars = string.punctuation + string.ascii_letters + string.digits + ' '


class EventHandler:
    def __init__(self, config):
        self.all_config = config
        self.own_config = config['event_handler']
        self.event_queue = asyncio.Queue()

        self.guru3_mgr = Guru3Mgr(config, event_queue=self.event_queue)
        self.omm_mgr = OMMMgr(config)
        self.asterisk_mgr = AsteriskManager(config)
        self.registration_mgr = RegistrationMgr(config, self.try_device_registration)

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

        # SIGTERM handler
        try:
            asyncio.get_event_loop().add_signal_handler(signal.SIGTERM, self.handle_sigterm)
        except NotImplementedError:
            self.logger.warning('SIGTERM handler could not be registered, since your system does not support it.')

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
                event_time = int(event['timestamp'])

                self.logger.info(f'//== Now processing event {event_id} ({event_type}).')

                # some events can be safely ignored and reported back to Guru3 as done
                if event_type in self.own_config['ignored_msgtypes']:
                    self.logger.info(f'Ignoring event of type {event_type} as per config.')
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
                elif event_type == 'UPDATE_CALLGROUP':
                    self.do_update_callgroup(event_data)
                else:
                    raise RuntimeError(
                        f'Unknown event type occurred while EventHandler was processing event {event_id}.')
                delta_time = datetime.now() - datetime.fromtimestamp(event_time)
                delta_time = delta_time.seconds + delta_time.microseconds / 1000000
                # mark event done in Guru3
                self.guru3_mgr.mark_event_complete(event_id)
                self.logger.info(f'\\\\== Event processed {round(delta_time, 2)} seconds after creation in Guru3.')

        except asyncio.CancelledError:
            pass

    def try_device_registration(self, temp_number, token):
        token = token[4:]
        # find OMM user with the temporary number
        from_user = self.omm_mgr.omm.find_user({'num': temp_number})
        # find OMM user with the corresponding token
        to_user = self.omm_mgr.omm.find_user({'hierarchy2': token})
        if not from_user:
            self.logger.warning(
                f'Failed to fetch temp user (temp_num:{temp_number}) on registration! Can\'t transfer PP!')
            return False
        if not to_user:
            self.logger.warning(f'Failed to fetch OMM user (token:{token}) on registration! Can\'t transfer PP!')
            return False
        self.logger.info(
            f'Transferring PP (ppn:{from_user.ppn}) to OMM user (uid: {to_user.uid}, number: {to_user.num}).')
        # transfer PP to real user
        self.omm_mgr.transfer_pp(int(from_user.uid), int(to_user.uid), int(from_user.ppn))
        # delete temporary user, both in OMM and Asterisk
        self.omm_mgr.delete_user(temp_number)
        self.asterisk_mgr.delete_user(temp_number)
        return True

    def do_update_extension(self, event_data):
        # extract event info
        ext_type = event_data['type']
        number = event_data['number']

        # if new extension type is not DECT or SIP, determine whether the old user needs to be deleted
        if ext_type not in ['DECT', 'SIP', 'GROUP']:
            self.logger.warning(
                f'Non-SIP/DECT extension update (type:{ext_type}), ignoring event and deleting old SIP and DECT entries for this number.')
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

        # handle GROUP (callgroup) extension update
        elif ext_type == 'GROUP':
            self.do_group_extension_update(event_data)

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
        # trim name to length acceptable by OMM
        name = ''.join([char if char in allowed_chars else '?' for char in event_data['name']])[:19]
        number = event_data['number']
        token = event_data['token']
        self.logger.info(f'Processing DECT extension update for number {number}.')

        # if user already exists, update user entry
        if number in self.omm_mgr.users:
            self.logger.info(f'Updating existing OMM user {number}.')
            self.omm_mgr.update_user_info(number=number, name=name, token=token)

        # else, create a new user
        else:
            self.logger.info(f'Creating new Asterisk and OMM user for number {number}.')
            # make sure that any existing SIP user is being deleted beforehand
            if self.asterisk_mgr.check_for_user(number=number):
                self.logger.info('Deleting existing Asterisk user that would clash with the newly created one.')
                self.asterisk_mgr.delete_user(number=number)

            sip_password = utils.create_password('alphanum', self.all_config['asterisk']['password_length'])
            self.asterisk_mgr.create_user(number=number, sip_password=sip_password)
            self.omm_mgr.create_user(name=name, number=number, token=token, sip_user=number, sip_password=sip_password)

    def do_group_extension_update(self, event_data):
        number = event_data['number']
        name = event_data['name']

        # delete DECT extension, if present
        if number in self.omm_mgr.users:
            self.omm_mgr.delete_user(number=number)

        # delete Asterisk user, if present
        if self.asterisk_mgr.check_for_user(number):
            self.asterisk_mgr.delete_user(number)

        # if callgroup already exists, update entry
        if self.asterisk_mgr.check_for_callgroup(number):
            self.asterisk_mgr.update_callgroup(number, name)
        # else, create new callgroup
        else:
            self.asterisk_mgr.create_callgroup(number)

    def do_delete_extension(self, event_data):
        number = event_data['number']
        if self.asterisk_mgr.check_for_user(number):
            self.asterisk_mgr.delete_user(number=number)
        if number in self.omm_mgr.users:
            self.omm_mgr.delete_user(number=number)
        if self.asterisk_mgr.check_for_callgroup(number=number):
            self.asterisk_mgr.delete_callgroup(number)

    def do_rename_extension(self, event_data):
        old_number = event_data['old_extension']
        new_number = event_data['new_extension']
        if self.asterisk_mgr.check_for_user(number=old_number):
            self.asterisk_mgr.move_user(old_number=old_number, new_number=new_number)

        if old_number in self.omm_mgr.users:
            self.omm_mgr.move_user(old_number, new_number)

        if self.asterisk_mgr.check_for_callgroup(old_number):
            self.asterisk_mgr.move_callgroup(old_number, new_number)

    def do_unsubscribe_device(self, event_data):
        number = event_data['extension']
        user = self.omm_mgr.users[number]
        ppn = int(user.ppn)
        if ppn == 0:
            self.logger.info(
                'Discarding UNSUBSCRIBE_DEVICE since the user has no PP. (Get your mind out of the gutter!)')
            return
        self.logger.info(f'Unsubscribing PP (PPN:{ppn}) from user {user.num}.')
        self.omm_mgr.omm.delete_device(ppn)

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

    def do_update_callgroup(self, event_data):
        callgroup_number = event_data['number']
        self.logger.info('Updating callgroup in Asterisk\'s DB to reflect list of active members from Guru3.')
        active_extensions = [ext['extension'] for ext in event_data['extensions'] if ext['active']]
        current_extensions = self.asterisk_mgr.fetch_callgroup_members(callgroup_number)
        self.logger.info(active_extensions+['/']+current_extensions)
        for ext in active_extensions + current_extensions:
            if ext in active_extensions and current_extensions:
                continue
            if ext in active_extensions and ext not in current_extensions:
                self.asterisk_mgr.add_user_to_callgroup(ext, callgroup_number)
            elif ext not in active_extensions and ext in current_extensions:
                self.asterisk_mgr.remove_user_from_callgroup(ext, callgroup_number)