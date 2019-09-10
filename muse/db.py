from functools import lru_cache

from pymongo import MongoClient

from muse.server_settings import MONGODB_URI


@lru_cache()
def get_db():
    mongo_client = MongoClient(MONGODB_URI)
    db = mongo_client['muse']
    return db


@lru_cache()
def get_colle(colle_name):
    return get_db()[colle_name]
