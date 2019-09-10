import argparse
import subprocess
import tempfile
import time

from loguru import logger

from muse.client_settings import EMPTY_FILENAME, EMPTY_FILEPATH, INPUT_ARCHIVE_DIR, OUTPUT_ARCHIVE_DIR
from muse.client import MuseClient, TaskStatus


def setup_parser():
    parser = argparse.ArgumentParser()
    subparser = parser.add_subparsers(dest='action')
    subparser.required = True

    subparser.add_parser('devices')

    run_parser = subparser.add_parser('run')
    run_parser.add_argument('--in', type=str, nargs='+', default=[], help='input files')
    run_parser.add_argument('--cmd', type=str, required=True, nargs='+', help='command')
    run_parser.add_argument('--out', type=str, nargs='+', default=[], help='output files')
    run_parser.add_argument('--dev', type=str, required=True, help='device id')

    args = parser.parse_args()
    return args


def device_info_to_text(info):
    return {
        'device_id': info['device_id'],
        'power_on': 'unknown' if info['power_on'] is None else ('on' if info['power_on'] else 'off'),
        'battery': 'unknown' if info['battery'] is None else str(info['battery']) + '%',
        'hostname': 'unknown' if info['hostname'] is None else info['hostname'],
    }


def main_devices(args):
    client = MuseClient()
    device_infos = client.list_devices()
    tasks = client.list_tasks()

    device_id_to_task = {}
    for task in tasks:
        if TaskStatus[task['status']] in (TaskStatus.PREPARING, TaskStatus.RUNNING, TaskStatus.KILLING):
            device_id_to_task[task['device_id']] = task

    print(f'{len(device_infos)} devices active')
    for device_info in device_infos:
        print('---------------------')
        device_info = device_info_to_text(device_info)
        if device_info['device_id'] in device_id_to_task:
            device_task = device_id_to_task[device_info['device_id']]
            print('{} , busy: {} - {}s'.format(
                device_info['device_id'],
                device_task['create_user'], int(time.time() - device_task['start_time'])))
        else:
            print(device_info['device_id'])
        print('  Name: ' + device_info['hostname'])
        print('  Battery: ' + device_info['battery'])
        print('  Screen: ' + device_info['power_on'])
    print()
    return device_infos


def main_run(args):
    muse_client = MuseClient()

    logger.info('Starting task')
    task = muse_client.create_task(args.dev, args.cmd, args.out)

    logger.info('Packaging inputs')
    with tempfile.NamedTemporaryFile(dir=INPUT_ARCHIVE_DIR, suffix='.tar') as f:
        subprocess.check_call(['tar', 'cf', f.name, EMPTY_FILEPATH] + getattr(args, 'in'))
        task.upload_input_archive(f.name)

    task.run()

    logger.info('Retriving results')
    with tempfile.NamedTemporaryFile(dir=OUTPUT_ARCHIVE_DIR, suffix='.tar') as f:
        task.download_output_archive(f.name)
        subprocess.check_call(['tar', 'xf', f.name, '--exclude', EMPTY_FILENAME])
    logger.info('Finished')


def main():
    args = setup_parser()

    if args.action == 'devices':
        main_devices(args)
    elif args.action == 'run':
        main_run(args)


if __name__ == '__main__':
    main()
