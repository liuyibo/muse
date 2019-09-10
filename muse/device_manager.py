import subprocess
import time
from shlex import quote

from loguru import logger

from muse.server_settings import DEVICE_WORKSPACE


class DeviceManager:
    def __init__(self):
        pass

    def get_all_device_ids(self):
        try:
            devices = []
            cmd = ['adb', 'devices']
            for line in subprocess.check_output(cmd, universal_newlines=True, timeout=10).splitlines():
                if '\tdevice' in line:
                    devices.append(line.split()[0])
            devices = sorted(devices)
            return devices
        except subprocess.CalledProcessError:
            return []

    def get_device_info(self, device_id):
        power_on = None
        if power_on is None:
            try:
                cmd = ['adb', '-s', device_id, 'shell', 'dumpsys', 'input_method']
                for line in subprocess.check_output(cmd, universal_newlines=True, timeout=10).splitlines():
                    if 'mSystemReady' in line:
                        if 'mScreenOn' in line:
                            power_on = 'mScreenOn=true' in line
                        elif 'mInteractive' in line:
                            power_on = 'mInteractive=true' in line
            except subprocess.SubprocessError:
                pass

        if power_on is None:
            try:
                cmd = ['adb', '-s', device_id, 'shell', 'dumpsys', 'power']
                for line in subprocess.check_output(cmd, universal_newlines=True, timeout=10).splitlines():
                    if 'Display Power' in line:
                        power_on = 'ON' in line
            except subprocess.SubprocessError:
                pass

        battery = None
        try:
            cmd = ['adb', '-s', device_id, 'shell', 'dumpsys', 'battery']
            for line in subprocess.check_output(cmd, universal_newlines=True, timeout=10).splitlines():
                if 'level' in line:
                    battery = float(line.strip().split()[-1])
        except subprocess.SubprocessError:
            pass

        hostname = None
        try:
            cmd = ['adb', '-s', device_id, 'shell', 'getprop', 'persist.project_name']
            hostname = subprocess.check_output(cmd, universal_newlines=True, timeout=10).strip()
            if not hostname:
                cmd = ['adb', '-s', device_id, 'shell', 'getprop', 'ro.product.model']
                hostname = subprocess.check_output(cmd, universal_newlines=True, timeout=10).strip()
        except subprocess.SubprocessError:
            pass

        return {
            'device_id': device_id,
            'power_on': power_on,
            'battery': battery,
            'hostname': hostname,
        }

    def push_data(self, device_id, tar_path, terminate_flag):
        cmd = ['adb', '-s', device_id, 'shell', 'rm', '-rf', DEVICE_WORKSPACE]
        logger.info(' '.join(cmd))
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        while not terminate_flag.is_set():
            try:
                process.wait(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                pass
        if terminate_flag.is_set():
            process.terminate()
        process.wait()

        cmd = ['adb', '-s', device_id, 'push', '--sync', tar_path, f'{DEVICE_WORKSPACE}/__input.tar']
        logger.info(' '.join(cmd))
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        while not terminate_flag.is_set():
            try:
                process.wait(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                pass
        if terminate_flag.is_set():
            process.terminate()
        process.wait()
        if process.returncode:
            return process.returncode

        cmd = [
            'adb', '-s', device_id, 'shell',
            f'cd {DEVICE_WORKSPACE} && tar xvf __input.tar --no-same-owner --exclude */__empty.txt'
        ]
        logger.info(' '.join(cmd))
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        while not terminate_flag.is_set():
            try:
                process.wait(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                pass
        if terminate_flag.is_set():
            process.terminate()
        process.wait()
        if process.returncode:
            return process.returncode
        return 0

    def pull_data(self, device_id, src_path, dst_path, terminate_flag):
        src_path_str = ' '.join([f"'{p}'" for p in src_path])
        remote_cmd = '; '.join([
            f'cd {DEVICE_WORKSPACE}',
            'touch __empty.txt',
            'paths=()',
            f'for p in {src_path_str} __empty.txt',
            'do if [ -f "$p" -o -d "$p" ]',
            'then paths+=($p)',
            'fi',
            'done',
            'tar cvf __output.tar ${paths[@]}',
        ])

        cmd = ['adb', '-s', device_id, 'shell', remote_cmd]
        logger.info(' '.join(cmd))
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        while not terminate_flag.is_set():
            try:
                process.wait(0.1)
                break
            except subprocess.TimeoutExpired:
                pass
        if terminate_flag.is_set():
            process.terminate()
        process.wait()
        if process.returncode:
            return process.returncode

        cmd = ['adb', '-s', device_id, 'pull', f'{DEVICE_WORKSPACE}/__output.tar', dst_path]
        logger.info(' '.join(cmd))
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        while not terminate_flag.is_set():
            try:
                process.wait(0.1)
                break
            except subprocess.TimeoutExpired:
                pass
        if terminate_flag.is_set():
            process.terminate()
        process.wait()
        if process.returncode:
            return process.returncode

        return 0

    def run_device_command(self, device_id, stdout_file, stderr_file, remote_cmd, terminate_flag):
        out_writer = open(stdout_file, 'wb')
        err_writer = open(stderr_file, 'wb')

        start_time = time.time()
        last_print_time = time.time()
        remote_cmd_str = ' '.join(remote_cmd)
        local_cmd = [
            'adb', '-s', device_id, 'shell', '-n',
            f'cd {quote(DEVICE_WORKSPACE)} && {remote_cmd_str}'
        ]
        logger.info(' '.join(local_cmd))
        process = subprocess.Popen(
                local_cmd, stdin=subprocess.DEVNULL,
                stdout=out_writer, stderr=err_writer)

        def print_offset():
            stdout_offset = out_writer.tell()
            stderr_offset = err_writer.tell()

            time_cost = time.time() - start_time
            logger.info(
                f'Task lasts for {time_cost:.2f} seconds'
                f', wrote {stdout_offset} bytes to stdout'
                f', {stderr_offset} bytes to stderr'
            )

        while not terminate_flag.is_set():
            if time.time() > last_print_time + 1.0:
                print_offset()
                last_print_time = time.time()
            try:
                process.wait(0.1)
                break
            except subprocess.TimeoutExpired:
                continue
        if terminate_flag.is_set():
            process.terminate()
        process.wait()
        print_offset()

        out_writer.close()
        err_writer.close()

        return process.returncode
