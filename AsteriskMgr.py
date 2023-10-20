import psycopg2


class AsteriskManager:
    def __init__(self, config):
        self.config = config['asterisk']
        with open(self.config['token_file'], 'r') as tk_file:
            postgresql_user, postgresql_password = tk_file.read().split('\n')
            print(repr(postgresql_user), repr(postgresql_password))

        self.ps_aors = psycopg2.connect(
            database="info@lucalutz.org",
            host=self.config['host'],
            port=self.config['port'],
            user=postgresql_user,
            password=postgresql_password,
        )