import logging
from Guru3Mgr import Guru3Mgr

logging.basicConfig(format='[%(asctime)s] [%(levelname)-8s] --- [%(module)-10s]: %(message)s',
                    level=logging.INFO,
                    handlers=[logging.FileHandler('log.txt'), logging.StreamHandler()])
logger = logging.getLogger(__name__)

mgr = Guru3Mgr(domain='guru3.hackwerk.fun', token_file='token.tk')
mgr.run()
