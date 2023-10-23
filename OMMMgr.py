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
        with open(self.config['token_file'], 'r') as tk_file:
            self.user, self.password = [line.strip() for line in tk_file.readlines()]

        self.users: dict[str, PPUser] = {}

    async def start_communication(self, request_lock: asyncio.Lock):
        try:
            self.omm.login(user=self.user, password=self.password, ommsync=True)
            self.read_users()
            request_lock.release()

            while True:
                self.omm.set_subscription("configured")
                await asyncio.sleep(15)
        except asyncio.CancelledError:
            pass
        finally:
            self.omm.logout()

    def read_users(self):
        self.users = {}
        for user in self.omm.get_users():
            # check if user is managed by guru-manager
            if user.hierarchy1 != 'GURU_MGR':
                continue
            self.users[user.num] = user

    def delete_user(self, number):
        user = self.users[number]
        del self.users[number]
        self.omm.delete_user(user.uid)
        return user

    def update_user_info(self, number, name, token):
        user = self.users[number]
        user.name = name
        user.hierarchy2 = token
        self.users[number] = user
        self.omm.update_user(user)
        return user

    def create_user(self, name, number, sip_user, sip_password, token=None):
        user_data = self.omm.create_user(name=name,
                                         number=number,
                                         desc1='GURU_MGR',
                                         desc2=token,
                                         sip_user=sip_user,
                                         sip_password=sip_password)
        self.users[number] = self.omm.get_user(user_data['uid'])
        return self.users[number]

    def move_user(self, old_number, new_number):
        user = self.users[old_number]
        del self.users[old_number]
        user.num = new_number
        user.sipAuthId = new_number
        self.users[new_number] = user
        self.omm.update_user(user)
        return user

    def transfer_pp(self, from_uid: int, to_uid: int, ppn: int):
        # transfer pp from one user to the other
        self.omm.detach_user_device(uid=from_uid, ppn=ppn)
        self.omm.attach_user_device(uid=to_uid, ppn=ppn)
