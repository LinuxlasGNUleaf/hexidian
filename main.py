import logging
import sys
import yaml

from EventHandler import EventHandler

with open('config.yaml', 'r') as cfg_stream:
    try:
        print('parsing config file...')
        config = yaml.safe_load(cfg_stream)
    except yaml.YAMLError as exc:
        print(f'While parsing the config file, the following error occurred:\n{exc}')
        sys.exit()

logging.basicConfig(format='[%(asctime)s] [%(levelname)-8s] --- [%(module)-10s]: %(message)s',
                    level=logging.DEBUG,
                    handlers=[logging.FileHandler(config['log_file']), logging.StreamHandler()])
logger = logging.getLogger(__name__)

event_handler = EventHandler(config)
event_handler.start()
