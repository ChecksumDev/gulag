from contextlib import asynccontextmanager
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from typing import AsyncIterator
from typing import Iterator
from typing import Optional

import aiohttp
import cmyui
import datadog
import geoip2.database
import orjson
from pymongo.mongo_client import MongoClient


@asynccontextmanager
async def acquire_http_session(has_internet: bool) -> AsyncIterator[Optional[aiohttp.ClientSession]]:
    if has_internet:
        # TODO: perhaps a config setting to enable optimizations like this?
        def json_encoder(x): return str(orjson.dumps(x))

        http_sess = aiohttp.ClientSession(json_serialize=json_encoder)
        try:
            yield http_sess
        finally:
            await http_sess.close()


@asynccontextmanager
async def acquire_mongo_db(config: dict[str, Any]):
    mongo_client = MongoClient(**config)
    try:
        yield mongo_client
    finally:
        await mongo_client.close()


@contextmanager
def acquire_geoloc_db_conn(db_file: Path) -> Iterator[Optional[geoip2.database.Reader]]:
    if db_file.exists():
        geoloc_db = geoip2.database.Reader(str(db_file))
        try:
            yield geoloc_db
        finally:
            geoloc_db.close()
    else:
        yield None


@contextmanager
def acquire_datadog_client(config: dict[str, Any]) -> Iterator[Optional[datadog.ThreadStats]]:
    if all(config.values()):
        datadog.initialize(**config)
        datadog_client = datadog.ThreadStats()
        try:
            datadog_client.start(flush_in_thread=True,
                                 flush_interval=15)
            # wipe any previous stats from the page.
            datadog_client.gauge('gulag.online_players', 0)
            yield datadog_client
        finally:
            datadog_client.stop()
            datadog_client.flush()
    else:
        yield None
