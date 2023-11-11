import logging
import psycopg2

import utils


class AsteriskManager:
    def __init__(self, config):
        self.config = config['asterisk']
        self.logger = logging.getLogger(__name__)

        try:
            self.connection = psycopg2.connect(
                database='asterisk',
                host=self.config['host'],
                port=self.config['port'],
                user=self.config['username'],
                password=utils.read_password_env(self.config['password_env']),

            )
            self.logger.info(f'PostgreSQL server version: {self.connection.server_version}')
        except psycopg2.OperationalError as exc:
            raise exc

    def close(self):
        self.connection.close()

    def create_user(self, number, sip_password, temporary=False):
        self.logger.info(f'Creating Asterisk user with number: {number}')
        call_router = 'call-router-temp' if temporary else 'call-router'
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"insert into ps_aors (id, max_contacts, remove_existing) values ('{number}', 1, 'yes');")
            cursor.execute(
                f"insert into ps_auths (id, auth_type, password, username) values ('{number}', 'userpass', '{sip_password}', '{number}');")
            cursor.execute(
                f"insert into ps_endpoints (id, aors, auth, context, allow, direct_media) values ('{number}', '{number}', '{number}', '{call_router}', '!all,g722,alaw,ulaw,gsm', 'no');")
        self.connection.commit()

    def delete_user(self, number):
        self.logger.info(f'Deleting Asterisk user {number}.')
        with self.connection.cursor() as cursor:
            cursor.execute(f"delete from ps_aors where id='{number}';")
            cursor.execute(f"delete from ps_auths where id='{number}';")
            cursor.execute(f"delete from ps_endpoints where id='{number}';")
        self.connection.commit()

    def check_for_user(self, number):
        with self.connection.cursor() as cursor:
            cursor.execute(f"select id from ps_aors where id='{number}'")
            return cursor.fetchone() is not None

    def move_user(self, old_number, new_number):
        self.logger.info(f'Moving Asterisk user {old_number} to {new_number}.')
        with self.connection.cursor() as cursor:
            cursor.execute(f"update ps_aors set id='{new_number}' where id='{old_number}'")
            cursor.execute(f"update ps_auths set id='{new_number}', username='{new_number}' where id='{old_number}'")
            cursor.execute(f"update ps_endpoints set id='{new_number}', aors='{new_number}', auth='{new_number}' where id='{old_number}'")
        self.connection.commit()

    def update_password(self, number, new_password):
        self.logger.info(f'Updating password for Asterisk user {number}.')
        with self.connection.cursor() as cursor:
            cursor.execute(f"update ps_auths set password='{new_password}' where id='{number}'")
        self.connection.commit()

    def check_for_callgroup(self, number):
        with self.connection.cursor() as cursor:
            cursor.execute(f"select extension from callgroups where extension='{number}'")
            return cursor.fetchone() is not None

    def update_callgroup(self, number, name):
        with self.connection.cursor() as cursor:
            cursor.execute(f"update callgroups set name='{name}' where extension='{number}'")
        self.connection.commit()

    def create_callgroup(self, number, name):
        with self.connection.cursor() as cursor:
            cursor.execute(f"insert into callgroups (extension, name) values ('{number}', '{name}')")
        self.connection.commit()

    def delete_callgroup(self, number):
        with self.connection.cursor() as cursor:
            cursor.execute(f"delete from callgroups where extension='{number}'")
            cursor.execute(f"delete from callgroup_members where extension='{number}'")
        self.connection.commit()

    def move_callgroup(self, old_number, new_number):
        with self.connection.cursor() as cursor:
            cursor.execute(f"update callgroups set extension='{new_number}' where extension='{old_number}'")
            cursor.execute(f"update callgroup_members set callgroup='{new_number}' where callgroup='{old_number}'")
        self.connection.commit()

    def fetch_callgroup_members(self, number):
        with self.connection.cursor() as cursor:
            cursor.execute(f"select extension from callgroup_members where callgroup='{number}'")
            return [ext[0] for ext in cursor.fetchall()]

    def add_user_to_callgroup(self, extension, callgroup):
        with self.connection.cursor() as cursor:
            cursor.execute(f"insert into callgroup_members (extension, callgroup) values ('{extension}', '{callgroup}')")
        self.connection.commit()

    def remove_user_from_callgroup(self, extension, callgroup):
        with self.connection.cursor() as cursor:
            cursor.execute(f"delete from callgroup_members where extension='{extension}' AND callgroup='{callgroup}'")
        self.connection.commit()
