import os
import sys
import time
from threading import Thread

import requests
from humanize import naturalsize
from loguru import logger
from requests_toolbelt.multipart.encoder import MultipartEncoder, MultipartEncoderMonitor

from muse.client_settings import SERVER_URL
from muse.task import TaskStatus, TaskFailReason
from muse.exceptions import MuseClientError


class Task:
    def __init__(self, hint_device_id, cmd, output_files, server_url=SERVER_URL):
        self.hint_device_id = hint_device_id
        self.cmd = cmd
        self.output_files = output_files
        self.server_url = server_url
        self.task = None
        self._id = None

    def init(self):
        response = requests.post(f'{self.server_url}task/create', json={
            'cmd': {
                'shell': self.cmd,
            },
            'output': {
                'files': self.output_files,
            },
            'hint_device_id': self.hint_device_id,
            'create_user': os.getenv('USER'),
        })
        self._id = response.json()['_id']

    def run(self):
        try:
            self.wait_until_start()
            self.monitor_task()
            if not self.log_task_status():
                raise MuseClientError('Task failed!')
        except KeyboardInterrupt as exception:
            logger.warning('Killing task...')
            self.kill()
            raise exception

    def upload_input_archive(self, archive_path):
        prev_print_time = 0

        def print_progress(monitor):
            nonlocal prev_print_time
            if time.time() > prev_print_time + 1.0 or monitor.bytes_read == monitor.len:
                logger.info(f'Uploading: {naturalsize(monitor.bytes_read)} / {naturalsize(monitor.len)}')
                prev_print_time = time.time()

        encoder = MultipartEncoder({
            'file': (os.path.basename(archive_path), open(archive_path, 'rb'), 'application/octet-stream')
        })
        monitor = MultipartEncoderMonitor(encoder, callback=print_progress)

        response = requests.post(
                f'{self.server_url}task/upload/{self._id}',
                data=monitor,
                headers={'Content-Type': monitor.content_type})
        return response.text

    def download_output_archive(self, archive_path):
        prev_print_time = 0

        def print_progress(bytes_downloaded, total_len):
            nonlocal prev_print_time
            if time.time() > prev_print_time + 1.0 or bytes_downloaded == total_len:
                logger.info(f'Downloading: {naturalsize(bytes_downloaded)} / {naturalsize(total_len)}')
                prev_print_time = time.time()

        response = requests.get(f'{self.server_url}task/download/{self._id}', stream=True)
        archive_size = int(response.headers.get('content-length'))

        downloaded_size = 0
        with open(archive_path, 'wb') as f:
            for data in response.iter_content(chunk_size=4096):
                f.write(data)
                downloaded_size += len(data)
                print_progress(downloaded_size, archive_size)

    def wait_until_start(self):
        while True:
            response = requests.get(f'{self.server_url}task/query/{self._id}')
            self.task = response.json()
            status = TaskStatus[self.task['status']]
            logger.info(f'Task status: {status}')
            if status in (TaskStatus.QUEUEING, TaskStatus.PREPARING):
                time.sleep(1)
            elif status in (TaskStatus.COMPLETED, TaskStatus.KILLING, TaskStatus.FAILED):
                return
            elif status in (TaskStatus.RUNNING,):
                break
            else:
                assert False

    def monitor_task(self):
        stdout_t = Thread(target=self.get_log, args=('stdout',), daemon=True)
        stderr_t = Thread(target=self.get_log, args=('stderr',), daemon=True)
        keep_alive_t = Thread(target=self.keep_alive, daemon=True)

        stdout_t.start()
        stderr_t.start()
        keep_alive_t.start()

        stdout_t.join()
        stderr_t.join()
        keep_alive_t.join()

    def get_log(self, log):
        log_r = requests.get(f'{self.server_url}task/log/{self._id}/{log}', stream=True)
        stdout_io = sys.stdout.buffer
        stderr_io = sys.stderr.buffer
        for data in log_r.iter_content(chunk_size=4096):
            if log == 'stdout':
                stdout_io.write(data)
                stdout_io.flush()
            else:
                stderr_io.write(data)
                stderr_io.flush()

    def kill(self):
        if self._id is None:
            return
        response = requests.delete(f'{self.server_url}task/kill/{self._id}')
        if response.status_code == '204':
            logger.warning('Killed')

    def keep_alive(self):
        while True:
            response = requests.get(f'{self.server_url}task/query/{self._id}')
            self.task = response.json()
            status = TaskStatus[self.task['status']]
            if status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                return
            time.sleep(1)

    def log_task_status(self):
        if self.task is not None:
            if 'fail_reason' in self.task:
                fail_reason = TaskFailReason[self.task['fail_reason']]
                if fail_reason == TaskFailReason.DEVICE_UNAVAILABLE:
                    logger.error('Device unavailable')
                elif fail_reason == TaskFailReason.PUSH_DATA_FAILED:
                    logger.error('Push data failed')
                elif fail_reason == TaskFailReason.PULL_DATA_FAILED:
                    logger.error('Pull data failed')
                elif fail_reason == TaskFailReason.NONZERO_RETURN_CODE:
                    logger.error('Non-zero return code')
                elif fail_reason == TaskFailReason.KILLED:
                    logger.error('Killed')
                else:
                    assert False
            elif TaskStatus[self.task['status']] == TaskStatus.COMPLETED:
                logger.info('Task completed successfully')
                return True
        return False


class MuseClient:
    def __init__(self, server_url=SERVER_URL):
        self.server_url = server_url

    def create_task(self, hint_device_id, cmd, output_files):
        task = Task(hint_device_id, cmd, output_files)
        task.init()
        return task

    def list_tasks(self):
        response = requests.get(f'{self.server_url}task/list')
        return response.json()['tasks']

    def list_devices(self):
        response = requests.get(f'{self.server_url}device/list')
        return response.json()['device_infos']
