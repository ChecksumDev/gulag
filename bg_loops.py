import asyncio
import time
from typing import Awaitable

from cmyui.logging import Ansi
from cmyui.logging import log

import packets
from constants.privileges import Privileges
from objects import glob

__all__ = ('initialize_housekeeping_tasks',)

OSU_CLIENT_MIN_PING_INTERVAL = 300000 // 1000  # defined by osu!


async def initialize_housekeeping_tasks() -> None:
    """Create tasks for each housekeeping tasks."""
    glob.housekeeping_tasks = [
        glob.loop.create_task(task) for task in (
            _remove_expired_donation_privileges(interval=30 * 60),
            _reroll_bot_status(interval=5 * 60),
            _disconnect_ghosts(interval=OSU_CLIENT_MIN_PING_INTERVAL // 3),
        )
    ]


async def _remove_expired_donation_privileges(interval: int) -> None:
    """Remove donation privileges from users with expired sessions."""
    while True:
        log('Removing expired donation privileges.', Ansi.LMAGENTA)

        glob.db.users.find_and_modify(
            {'privileges.donor': True, 'privileges.expire': {'$lt': time.time()}},
            {'$unset': {'privileges.donor': True}},
        )

        await asyncio.sleep(interval)


async def _disconnect_ghosts(interval: int) -> None:
    """Actively disconnect users above the
       disconnection time threshold on the osu! server."""
    while True:
        await asyncio.sleep(interval)
        current_time = time.time()
        
        if len(glob.players) > 0:
            for p in glob.players:
                if current_time - p.last_recv_time > OSU_CLIENT_MIN_PING_INTERVAL:
                    log(f'Auto-dced {p}.', Ansi.LMAGENTA)
                    p.logout()
        else:
            log('No players online to disconnect.', Ansi.LMAGENTA)


async def _reroll_bot_status(interval: int) -> None:
    """Reroll the bot's status, every `interval`."""
    while True:
        await asyncio.sleep(interval)
        packets.botStats.cache_clear()
