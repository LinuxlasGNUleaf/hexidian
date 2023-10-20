import asyncio
import logging

from Guru3Mgr import Guru3Mgr
from OMMMgr import OMMMgr
from AsteriskMgr import AsteriskManager


class EventHandler:
    def __init__(self, config):
        self.own_config = config['event_handler']
        self.guru3_input_queue = asyncio.Queue()
        self.guru3_mgr = Guru3Mgr(config, input_queue=self.guru3_input_queue)
        self.omm_mgr = OMMMgr(config)
        self.asterisk_mgr = AsteriskManager(config)
        self.logger = logging.getLogger(__name__)
        self.tasks = []

    def start(self):
        try:
            asyncio.run(self.run_tasks())
        except KeyboardInterrupt:
            self.logger.info("Cancelling tasks...")
            for task in self.tasks:
                task.cancel()

    async def run_tasks(self):
        self.tasks = []

        # Guru3 task, responsible for pulling events from frontend and marking them as done
        self.tasks.append(asyncio.create_task(self.guru3_mgr.run()))

        # EventHandler task, responsible for distributing incoming messages from Guru3
        # to the responsible backend manager (OMM or Asterisk DB)
        self.tasks.append(asyncio.create_task(self.distribute_guru3_messages()))

        # OMM task, responsible for establishing connection to Open Mobility Manager (DECT Manager)
        self.tasks.append(asyncio.create_task(self.omm_mgr.start_communication()))
        await asyncio.gather(*self.tasks)

    async def distribute_guru3_messages(self):
        try:
            while True:
                # wait for new event in queue
                event = await self.guru3_input_queue.get()
                event_id = event['id']
                event_type = event['type']

                # sync start and end can be safely ignored and reported back to Guru3 as done
                if event_type in self.own_config['ignored_msgtypes']:
                    self.guru3_mgr.mark_event_complete(event_id)
                    self.logger.info(f'{event_type} ignored internally and reported as processed to Guru3.')
                    continue

                processed = False
                # if relevant for OMM, let OMM Mgr process the event
                if event_type in self.own_config['omm_msgtypes']:
                    self.logger.info(f'Sending event {event_id} ({event_type}) to OMM Manager to process...')
                    ok = self.omm_mgr.handle_event(event)
                    processed = True
                    if not ok:
                        self.logger.error(f'Event could not be processed! ' + str(event))
                        raise RuntimeError(f'Error while OMM Manager was processing event {event_id} ({event_type})')

                # if relevant for Asterisk, let Asterisk Mgr process the event
                if event_type in self.own_config['asterisk_msgtypes']:
                    self.logger.info(f'Sending event {event_id} ({event_type}) to Asterisk Manager to process...')
                    # ok = await self.asterisk_mgr.handle_event(event)
                    processed = True
                    # if not ok:
                    #     self.logger.error(f'Event could not be processed! ' + str(event))
                    #     raise RuntimeError(f'Error while Asterisk Manager was processing event {event["id"]} ({event_type})')

                if not processed:
                    raise KeyError(f"Event was not processed! Event type: {event_type}")

                # UNCOMMENT WHEN EVERYTHING ACTUALLY WORKS
                self.guru3_mgr.mark_event_complete(event_id)

        except asyncio.CancelledError:
            self.logger.info('Received termination signal, GURU3_DISTRIBUTOR closed.')
