import asyncio
import logging
import os

from python_mitel.OMMClient import OMMClient
from python_mitel.types import PPUser


class OMMMgr:
    def __init__(self, config: dict):
        self.config = config['omm']
        self.logger = logging.getLogger(__name__)
        self.omm = OMMClient(host=self.config['host'], port=self.config['port'])
        if not os.path.exists(self.config['token_file']):
            raise FileNotFoundError("Token File for OMM manager not found!")
        with open(self.config['token_file'], 'r') as token_file:
            self.user, self.password = token_file.read().split('\n')

        self.users: dict[str, PPUser] = {}

    async def start_communication(self):
        try:
            self.omm.login(user=self.user, password=self.password)
            self.logger.info('Successfully logged into OMM')
            self.logger.info("OMM: " + self.omm.get_systemname())
            self.logger.info("Reading users from OMM...")
            self.read_users()
            self.logger.info('Allowing wildcard subscription...')
            while True:
                self.logger.debug(
                    f'Result of wildcard subscription action: {self.omm.set_subscription("wildcard", 5)}')
                await asyncio.sleep(60 * 5 - 10)
        except asyncio.CancelledError:
            pass
        finally:
            self.omm.logout()
            self.logger.info('Successfully logged out of OMM.')

    def handle_event(self, event):
        if self.config['blind_accept']:
            self.logger.warning("BLIND ACCEPTING THIS EVENT!")
            return True
        event_type = event['type']
        event_data = event['data']
        if event_type == 'UPDATE_EXTENSION':
            # extract extension type and check if DECT handling is necessary
            ext_type = event_data['type']
            if ext_type != 'DECT':
                self.logger.info(f'event concerns non-DECT extension (type: {ext_type}), skipping OMM event handling.')
                return True

            # extract number and other info from event
            number = event_data['number']
            display_name = event_data['name'][:19]
            desc2 = f'L: {event_data["location"][:12]}'

            # if user already exists, update user entry
            if number in self.users:
                self.logger.info('User for this number already present, updating user info instead...')
                user = self.users[number]
                user.name = display_name
                user.hierarchy2 = desc2
                self.users[number] = user
                self.omm.update_user(user)
                self.logger.info(f'Successfully updated user info for user {user.uid} with number {number}.')
                return True
            # else, create a new user
            else:
                self.logger.info(f'Attempting to create new user with number {number}...')
                user_data = self.omm.create_user(name=display_name, number=number, desc1='GURU_MGR', desc2=desc2)
                self.users[number] = self.omm.get_user(user_data['uid'])
                self.logger.info(
                    f'Created new user ({user_data["uid"]}, {number}) in response to event {event["id"]} [{event_type}]')
                return True
        elif event_type == 'DELETE_EXTENSION':
            number = event_data['number']
            user = self.users[number]
            del self.users[number]
            self.omm.delete_user(user.uid)
            return True
        elif event_type == 'RENAME_EXTENSION':
            old_num = event['data']['old_extension']
            new_num = event['data']['new_extension']
            user = self.users[old_num]
            user.num = new_num
            del self.users[old_num]
            self.users[new_num] = user
            self.omm.update_user(user)
            return True
        elif event_type == 'UNSUBSCRIBE_DEVICE':
            return False
        else:
            return False

    def read_users(self):
        self.users = {}
        for user in self.omm.get_users():
            # check if user is managed by guru-manager
            if user.hierarchy1 != 'GURU_MGR':
                continue
            self.users[user.num] = user
        self.logger.info(f'Found {len(self.users.keys()) if self.users else "no"} user(s) managed by guru-manager.')
