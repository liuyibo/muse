import os
import time
from threading import Thread
from multiprocessing import Process, Event
from pathlib import Path

from loguru import logger
from pymongo import ReturnDocument

from muse.server_settings import LOG_DIR, INPUT_ARCHIVE_DIR, OUTPUT_ARCHIVE_DIR
from muse.device_manager import DeviceManager
from muse.task import TaskStatus, TaskFailReason
from muse.db import get_colle


class TaskProcess(Process):
    def __init__(self, task, device_id):
        Process.__init__(self)

        self.task = task
        self.device_id = device_id
        self.terminate_flag = Event()
        self.device_manager = DeviceManager()

    def get_task_id(self):
        return self.task['_id']

    def get_device_id(self):
        return self.device_id

    def prepare_log(self, task):
        task_id = task['_id']
        time_ms = int(task['start_time'] * 1000)

        logger.info(f'Task {task_id}: preparing local logs file')
        stdout_path = os.path.join(LOG_DIR, f'{task_id}_{time_ms}_out.log')
        stderr_path = os.path.join(LOG_DIR, f'{task_id}_{time_ms}_err.log')

        Path(stdout_path).touch()
        Path(stderr_path).touch()

        return stdout_path, stderr_path

    def run_task(self, task, device_id):
        task_id = task['_id']
        logger.info(f'Task {task_id}: preparing')

        stdout_path, stderr_path = self.prepare_log(task)

        push_data_failed = False
        local_input_tar = os.path.join(INPUT_ARCHIVE_DIR, f'{task_id}.tar')
        local_output_tar = os.path.join(OUTPUT_ARCHIVE_DIR, f'{task_id}.tar')

        return_code = self.device_manager.push_data(device_id, local_input_tar, self.terminate_flag)
        if return_code:
            logger.error(f'Task {task_id}: push data failed')
            push_data_failed = True

        if push_data_failed:
            self.colle_tasks.find_one_and_update(
                {'_id': task_id, 'status': TaskStatus.PREPARING.name},
                {'$set': {
                    'status': TaskStatus.FAILED.name,
                    'fail_reason': TaskFailReason.PUSH_DATA_FAILED.name,
                }})
            return

        self.colle_tasks.find_one_and_update(
            {'_id': task_id, 'status': TaskStatus.PREPARING.name},
            {'$set': {
                'status': TaskStatus.RUNNING.name,
                'stdout': stdout_path,
                'stderr': stderr_path}})

        logger.warning(f'Task {task_id}: running')
        command_return_code = self.device_manager.run_device_command(
                device_id, stdout_path, stderr_path, task['cmd']['shell'], self.terminate_flag)
        logger.info(f'Task {task_id}: command completed with return code {command_return_code}')

        pull_data_failed = False
        logger.info(f'Task {task_id}: pulling data from {local_output_tar}')
        return_code = self.device_manager.pull_data(
                device_id, task['output']['files'], local_output_tar, self.terminate_flag)
        logger.info(f'Task {task_id}: pulled data from {local_output_tar} with return code {return_code}')

        if return_code:
            logger.error(f'Task {task_id}: pull data failed')
            pull_data_failed = True

        if pull_data_failed:
            self.colle_tasks.find_one_and_update(
                {'_id': task_id, 'status': TaskStatus.RUNNING.name},
                {'$set': {
                    'status': TaskStatus.FAILED.name,
                    'fail_reason': TaskFailReason.PULL_DATA_FAILED.name}})
            return

        if command_return_code == 0:
            self.colle_tasks.find_one_and_update(
                {'_id': task_id, 'status': TaskStatus.RUNNING.name},
                {'$set': {
                    'status': TaskStatus.COMPLETED.name,
                    'finish_time': time.time()}})
        else:
            self.colle_tasks.find_one_and_update(
                {'_id': task_id, 'status': TaskStatus.RUNNING.name},
                {'$set': {
                    'status': TaskStatus.FAILED.name,
                    'fail_reason': TaskFailReason.NONZERO_RETURN_CODE.name,
                    'finish_time': time.time()}})

        logger.warning(f'Task {task_id}: finished')

    def run(self):
        self.colle_tasks = get_colle('tasks')

        self.run_task(self.task, self.device_id)


class Scheduler:
    def __init__(self):
        self.device_manager = DeviceManager()
        self.colle_tasks = get_colle('tasks')
        self.colle_devices = get_colle('devices')
        self.task_processes = []

    def loop(self):
        update_device_info_thread = Thread(target=self.loop_update_device_info)
        update_device_info_thread.daemon = True
        update_device_info_thread.start()

        while True:
            try:
                self.find_task_to_run()
                self.find_task_to_kill()
                self.clean_dead_task()
            except Exception as e:
                logger.exception(f'Unexpected exception: {e}')
            time.sleep(0.1)

    def find_task_to_run(self):
        available_devices = self.device_manager.get_all_device_ids()
        task = self.colle_tasks.find_one({'status': TaskStatus.QUEUEING.name, 'input_archive_ready': 1})
        if task is None:
            return False
        task_id = task['_id']

        selected_device = None
        busy_devices = set()
        working_tasks = self.colle_tasks.find({
            'status': {'$in': [TaskStatus.PREPARING.name, TaskStatus.RUNNING.name, TaskStatus.KILLING.name]}})
        for exist_task in working_tasks:
            if 'device_id' in exist_task:
                busy_devices.add(exist_task['device_id'])
        for device_candidate in available_devices:
            if device_candidate not in busy_devices and task['hint_device_id'] == device_candidate:
                selected_device = task['hint_device_id']

        if selected_device is None:
            logger.warning(f'Task {task_id}: device unavailable')
            self.colle_tasks.find_one_and_update(
                {'_id': task_id},
                {'$set': {
                    'status': TaskStatus.FAILED.name,
                    'fail_reason': TaskFailReason.DEVICE_UNAVAILABLE.name,
                    'finish_time': time.time()}})
            return False

        task = self.colle_tasks.find_one_and_update(
            {'_id': task_id},
            {'$set': {
                'status': TaskStatus.PREPARING.name,
                'device_id': selected_device,
                'start_time': time.time(),
                'active_time': time.time(),
            }}, return_document=ReturnDocument.AFTER)

        if task:
            logger.warning(f'Task {task_id}: assigned to device {selected_device}')
            p = TaskProcess(task, selected_device)
            p.start()
            self.task_processes.append(p)
            return True
        return False

    def find_task_to_kill(self):
        now = time.time()

        alive_tasks = self.colle_tasks.find({
            'status': {'$in': [TaskStatus.QUEUEING.name, TaskStatus.PREPARING.name, TaskStatus.RUNNING.name]}})
        for task in alive_tasks:
            if now - task['active_time'] > 10.0:
                self.colle_tasks.find_one_and_update(
                    {'_id': task['_id'], 'status': task['status']},
                    {'$set': {'status': TaskStatus.KILLING.name}})

        for task in self.colle_tasks.find({'status': TaskStatus.KILLING.name}):
            task_id = task['_id']
            logger.warning(f'Task {task_id}: is being killed')
            for p in self.task_processes:
                if p.get_task_id() == task_id:
                    p.terminate_flag.set()
                    p.join()

            self.colle_tasks.find_one_and_update(
                {'_id': task_id},
                {'$set': {'status': TaskStatus.FAILED.name, 'fail_reason': TaskFailReason.KILLED.name}})
            logger.warning(f'Task {task_id}: is killed')

    def clean_dead_task(self):
        alive_processes = []
        for p in self.task_processes:
            if p.is_alive():
                alive_processes.append(p)
            else:
                p.join()
        self.task_processes = alive_processes

    def loop_update_device_info(self):
        while True:
            self.update_device_info()
            time.sleep(30)

    def update_device_info(self):
        device_ids = self.device_manager.get_all_device_ids()
        device_infos = []
        for device_id in device_ids:
            device_infos.append(self.device_manager.get_device_info(device_id))

        num_devices = len(device_infos)
        logger.info(f'Update device info, found {num_devices} devices')
        self.colle_devices.update_one(
            {'key': 'info'},
            {'$set': {'device_infos': device_infos, 'update_time': time.time()}}, upsert=True)


def run_scheduler():
    scheduler = Scheduler()
    scheduler.loop()


if __name__ == '__main__':
    run_scheduler()
