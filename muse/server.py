import time
import os

from loguru import logger
from bson import ObjectId
from flask import Flask, request, jsonify, Response, send_file
from flask_cors import CORS

from muse.db import get_colle
from muse.server_settings import INPUT_ARCHIVE_DIR, OUTPUT_ARCHIVE_DIR, MUSE_SERVER_HOST, MUSE_SERVER_PORT
from muse.task import TaskStatus

app = Flask(__name__)
CORS(app)


@app.route('/device/list', methods=['GET'])
def list_devices():
    colle_devices = get_colle('devices')

    info = colle_devices.find_one({'key': 'info'})
    if info is None:
        device_infos = []
        update_time = 0
    else:
        device_infos = info['device_infos']
        update_time = info['update_time']
    return jsonify({'device_infos': device_infos, 'update_time': update_time})


@app.route('/task/create', methods=['POST'])
def create_task():
    colle_tasks = get_colle('tasks')
    j = request.json
    result = colle_tasks.insert_one({
        'status': TaskStatus.QUEUEING.name,
        'cmd': {
            'shell': j['cmd']['shell'],
        },
        'output': {
            'files': j['output']['files'],
        },
        'hint_device_id': j['hint_device_id'],
        'create_user': j['create_user'],
        'create_time': time.time(),
        'active_time': time.time(),
    })
    return jsonify({'_id': str(result.inserted_id)})


@app.route('/task/upload/<string:_id>', methods=['POST'])
def upload_input_archive(_id):
    colle_tasks = get_colle('tasks')
    f = request.files['file']
    f.save(os.path.join(INPUT_ARCHIVE_DIR, f'{_id}.tar'))
    colle_tasks.find_one_and_update(
        {'_id': ObjectId(_id)},
        {'$set': {'input_archive_ready': 1}})
    return '', 200


@app.route('/task/download/<string:_id>', methods=['GET'])
def download_output_archive(_id):
    return send_file(os.path.join(OUTPUT_ARCHIVE_DIR, f'{_id}.tar'), as_attachment=True)


@app.route('/task/query/<string:_id>', methods=['GET'])
def query_task(_id):
    colle_tasks = get_colle('tasks')
    d = colle_tasks.find_one_and_update(
        {'_id': ObjectId(_id)},
        {'$set': {'active_time': time.time()}})
    d['_id'] = str(d['_id'])
    return jsonify(d)


@app.route('/task/log/<string:_id>/<string:log>', methods=['GET'])
def stream_task_log(_id, log):
    assert log in ('stdout', 'stderr')
    colle_tasks = get_colle('tasks')
    task_log = colle_tasks.find_one(
        {'_id': ObjectId(_id)},
        {'stderr': 1, 'stdout': 1})
    if task_log is None or log not in task_log:
        log_file_path = None
    else:
        log_file_path = task_log[log]
    logger.info(f'{log}: {log_file_path}')

    def get_log():
        if log_file_path is None or not os.path.exists(log_file_path):
            return

        last_check_time = 0

        with open(log_file_path, 'r') as log_file:
            is_finished = False
            os.set_blocking(log_file.fileno(), False)
            while True:
                data = log_file.read(4096)
                if len(data):
                    yield data
                else:
                    if is_finished:
                        break
                    if time.time() - last_check_time > 0.1:
                        d = colle_tasks.find_one({'_id': ObjectId(_id)}, {'status': 1})
                        if TaskStatus[d['status']] in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                            is_finished = True
                        last_check_time = time.time()

                    time.sleep(0.001)

    return Response(get_log(), mimetype='text/plain')


@app.route('/task/list', methods=['GET'])
def list_tasks():
    colle_tasks = get_colle('tasks')
    doc = colle_tasks.find({'status': {
        '$in': [
            TaskStatus.QUEUEING.name, TaskStatus.PREPARING.name,
            TaskStatus.RUNNING.name, TaskStatus.KILLING.name
        ]
    }})

    tasks = []
    for task in doc:
        t = {key: value for key, value in task.items() if key != '_id'}
        tasks.append(t)

    return jsonify({'tasks': tasks})


@app.route('/task/kill/<string:_id>', methods=['DELETE'])
def kill_task(_id):
    colle_tasks = get_colle('tasks')
    doc = colle_tasks.find_one_and_update(
          {'_id': ObjectId(_id), 'status': {
              '$in': [TaskStatus.QUEUEING.name, TaskStatus.PREPARING.name, TaskStatus.RUNNING.name]}},
          {'$set': {'status': TaskStatus.KILLING.name}})
    if doc:
        return '', 204
    else:
        return '', 409


def run_server():
    app.run(host=MUSE_SERVER_HOST, port=MUSE_SERVER_PORT, debug=True)


if __name__ == '__main__':
    run_server()
