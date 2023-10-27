import logging
import os
import pathlib

import yaml
import argparse

from EventHandler import EventHandler

parser = argparse.ArgumentParser(description='Hexidian is a backend tool to process GURU3 events and send them to the OMM and Asterisk DB.')
parser.add_argument('--config', type=pathlib.Path, help='config file location')
args = parser.parse_args()

print(os.environ['OMM_PW'], os.environ['ASTERISK_PW'], os.environ['GURU_PW'])

with open('logo.txt', 'r', encoding='utf8') as logo_file:
    print(f'\033[91m{logo_file.read()}\033[0m')

with open(args.config.absolute(), 'r') as cfg_stream:
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
