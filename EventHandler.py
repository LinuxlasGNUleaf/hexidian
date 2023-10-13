import asyncio
import logging

from Guru3Mgr import Guru3Mgr


class EventHandler:
    def __init__(self, config):
        self.config = config
        self.guru3_input_queue = asyncio.Queue()
        self.guru3_input_queue_lock = asyncio.Lock()
        self.guru3_mgr = Guru3Mgr(self.config, event_queue=self.guru3_input_queue,
                                  queue_lock=self.guru3_input_queue_lock)
        self.logger = logging.getLogger(__name__)
        self.tasks = []

    def start(self):
        try:
            asyncio.run(self.run_tasks())
        except KeyboardInterrupt:
            for task in self.tasks:
                task.cancel()
        finally:
            self.logger.info("Cancelling tasks...")

    async def run_tasks(self):
        self.tasks = []
        self.tasks.append(asyncio.create_task(self.guru3_mgr.run()))
        self.tasks.append(asyncio.create_task(self.distribute_guru3_messages()))
        await asyncio.gather(*self.tasks)

    async def distribute_guru3_messages(self):
        try:
            while True:
                event = await self.guru3_input_queue.get()
                event_type = event['type']
                if event_type == 'SYNC_STARTED' or event_type == 'SYNC_ENDED':
                    self.guru3_mgr.mark_event_complete(event['id'])
                    self.logger.info(f'{event_type} ignored internally and reported as processed to Guru3.')
                elif event_type == 'UPDATE_EXTENSION':
                    pass
                elif event_type == 'DELETE_EXTENSION':
                    pass
                elif event_type == 'UPDATE_CALLGROUP':
                    pass
                elif event_type == 'RENAME_EXTENSION':
                    pass
                elif event_type == 'UNSUBSCRIBE_DEVICE':
                    pass
                else:
                    raise KeyError(f"Invalid event type: {event_type}")

        except asyncio.CancelledError:
            self.logger.info('Received termination signal, GURU3_DISTRIBUTOR closed.')
