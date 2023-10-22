import logging
import random

import psycopg2
import string


class AsteriskManager:
    def __init__(self, config):
        self.config = config['asterisk']
        self.logger = logging.getLogger(__name__)
        with open(self.config['token_file'], 'r') as tk_file:
            self.user, self.password = tk_file.read().split('\n')

        try:
            self.connection = psycopg2.connect(
                database="asterisk",
                host=self.config['host'],
                port=self.config['port'],
                user=self.user,
                password=self.password
            )
        except psycopg2.OperationalError as exc:
            self.logger.exception('Can\'t reach PostgreSQL database!')
            raise exc
        self.logger.info('PostGreSQL database connection established.')

    def close(self):
        self.connection.close()
        self.logger.info('PostGreSQL database connection closed.')

    def create_password(self):
        chars = string.ascii_letters + string.digits
        return ''.join([random.choice(chars) for _ in range(self.config['password_length'])])

    def create_user(self, number, sip_password=None, temporary=False):
        if not sip_password:
            sip_password = self.create_password()
        router = 'call-router-temp' if temporary else 'call-router'
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"insert into ps_aors (id, max_contacts) values ('{number}', 1);")
            cursor.execute(
                f"insert into ps_auths (id, auth_type, password, username) values ('{number}', 'userpass', '{sip_password}', '{number}');")
            cursor.execute(
                f"insert into ps_endpoints (id, aors, auth, context, allow, direct_media, dtls_auto_generate_cert) values ('{number}', '{number}', '{number}', '{router}', 'ulaw|alaw|g722|gsm|opus', 'no', 'yes');")
        self.connection.commit()
        self.logger.info(f'Created new SIP user via PostgreSQL with id {number} and password {sip_password}.')
        return sip_password

    def delete_user(self, number):
        with self.connection.cursor() as cursor:
            cursor.execute(f"delete from ps_aors where id='{number}';")
            cursor.execute(f"delete from ps_auths where id='{number}';")
            cursor.execute(f"delete from ps_endpoints where id='{number}';")
        self.connection.commit()
        self.logger.info(f'Deleted SIP user with id {number} via PostgreSQL.')

    def check_for_user(self, number):
        with self.connection.cursor() as cursor:
            cursor.execute(f"select id from ps_aors where id='{number}'")
            return cursor.fetchone() is not None

    def move_user(self, old_number, new_number):
        with self.connection.cursor() as cursor:
            cursor.execute(f"update ps_aors set id='{new_number}' where id='{old_number}'")
            cursor.execute(f"update ps_auths set id='{new_number}', username='{new_number}' where id='{old_number}'")
            cursor.execute(f"update ps_endpoints set id='{new_number}', aors='{new_number}', auth='{new_number}' where id='{old_number}'")
        self.connection.commit()

    def update_password(self, number, new_password):
        with self.connection.cursor() as cursor:
            cursor.execute(f"update ps_auths set password='{new_password}' where id='{number}'")
        self.connection.commit()
