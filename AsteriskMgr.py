import logging
import psycopg2


class AsteriskManager:
    def __init__(self, config):
        self.database = None
        self.config = config['asterisk']
        self.logger = logging.getLogger(__name__)
        with open(self.config['token_file'], 'r') as tk_file:
            self.user, self.password = tk_file.read().split('\n')

    def establish_connection(self):
        self.database = psycopg2.connect(
            database="asterisk",
            host=self.config['host'],
            port=self.config['port'],
            user=self.user,
            password=self.password
        )
        self.logger.info('PostGreSQL database connection established.')

    def close(self):
        self.database.close()
        self.logger.info('PostGreSQL database connection closed.')
