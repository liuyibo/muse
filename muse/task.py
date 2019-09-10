from enum import Enum


class TaskStatus(Enum):
    QUEUEING = 0
    PREPARING = 1
    RUNNING = 2
    KILLING = 3
    FAILED = 4
    COMPLETED = 5


class TaskFailReason(Enum):
    DEVICE_UNAVAILABLE = 0
    PUSH_DATA_FAILED = 1
    PULL_DATA_FAILED = 2
    NONZERO_RETURN_CODE = 3
    KILLED = 4
