import logging
import yaml

from EventHandler import EventHandler

with open('logo.txt', 'r') as logo_file:
    print(f'\033[91m{logo_file.read()}\033[0m')

with open('config.yaml', 'r') as cfg_stream:
    try:
        print('parsing config file...')
        config = yaml.safe_load(cfg_stream)
    except yaml.YAMLError as exc:
        print(f'While parsing the config file, the following exception occurred:')
        raise exc

logging.basicConfig(format='[%(asctime)s] [%(levelname)-8s] --- [%(module)-15s]: %(message)s',
                    level=logging.INFO,
                    handlers=[logging.FileHandler(config['log_file']), logging.StreamHandler()])
logger = logging.getLogger(__name__)
logger.info(f'starting to log to \'{config["log_file"]}\' and stdout.')
event_handler = EventHandler(config)
event_handler.start()
