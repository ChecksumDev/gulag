#!/usr/bin/env python3.9

# if you're interested in development, my test server is usually
# up at https://c.cmyui.xyz. just use the same `-devserver cmyui.xyz`
# connection method you would with any other modern server and you
# should have no problems connecting. registration is done in-game
# with osu!'s built-in registration (if you're worried about not being
# properly connected while registering, the server should send back
# https://i.cmyui.xyz/8-Vzy9NllPBp5K7L.png if you use a random login).

# you can also test gulag's rest api using my test server,
# e.g https://osu.cmyui.xyz/api/get_player_scores?id=3&scope=best

import os

from objects.collections import initialize_ram_caches
os.environ['PYTHONASYNCIODEBUG'] = '1'
import asyncio
import signal
import socket
from datetime import datetime
from pathlib import Path


import cmyui
from cmyui.logging import RGB, Ansi, log

import bg_loops
import misc.context
import misc.utils
from objects import glob  # (includes config)

# set the current working directory to /gulag
os.chdir(os.path.dirname(os.path.realpath(__file__)))

if not os.path.exists('config.py'):
    misc.utils.create_config_from_default()
    raise SystemExit(1)

GEOLOC_DB_FILE = Path.cwd() / 'ext/GeoLite2-City.mmdb'


async def run_server() -> None:
    """Begin listening for and handling connections on all endpoints."""

    # we'll be working on top of transport layer posix sockets.
    # these implement tcp/ip over ethernet for us, and osu!stable
    # uses http/1.0 ontop of this. we'll need to parse the http data,
    # find the appropriate handler, and dispatch the connection.

    # i'll be using my light web framework to handle parsing & dispatching
    # of connections to their respective handlers; here, we'll just worry
    # about the socket-level details, like receiving the data from the clients.

    # if you're interested in more details, you can see the implementation at
    # https://github.com/cmyui/cmyui_pkg/blob/master/cmyui/web.py

    # fetch our server's endpoints; gulag supports
    # osu!'s handlers across multiple domains.
    glob.app = cmyui.Server(
        name=f'circles v1.0.0',
        gzip=4, debug=glob.config.debug
    )

    from domains.cho import domain as c_ppy_sh  # /c[e4-6]?.ppy.sh/
    from domains.osu import domain as osu_ppy_sh
    from domains.ava import domain as a_ppy_sh
    from domains.map import domain as b_ppy_sh
    glob.app.add_domains({c_ppy_sh, osu_ppy_sh,
                          a_ppy_sh, b_ppy_sh})
    
    # support both INET and UNIX sockets
    if misc.utils.is_inet_address(glob.config.server_addr):
        sock_family = socket.AF_INET
    elif isinstance(glob.config.server_addr, str):
        sock_family = socket.AF_UNIX
    else:
        raise ValueError('Invalid socket address.')

    if sock_family == socket.AF_UNIX:
        # using unix socket - remove from filesystem if it exists
        if os.path.exists(glob.config.server_addr):
            os.remove(glob.config.server_addr)

    # create our transport layer socket; osu! uses tcp/ip
    with socket.socket(sock_family, socket.SOCK_STREAM) as listening_sock:
        listening_sock.setblocking(False)  # asynchronous
        #listening_sock.bind(glob.config.server_addr)
        #port = 1234
        print(sock_family, socket.SOCK_STREAM)
        listening_sock.bind(glob.config.server_addr)
        log(loop.get_debug(), Ansi.GREEN)

        if sock_family == socket.AF_UNIX:
            # using unix socket - give the socket file
            # appropriate (read, write) permissions
            os.chmod(glob.config.server_addr, 0o666)

        listening_sock.listen(glob.config.max_conns)
        log(f'-> Listening @ {glob.config.server_addr}', RGB(0x00ff7f))
        log(f'-> Total users: {glob.db.users.estimated_document_count()}', RGB(0x00ff7f))
        log(f'-> Max connections: {glob.config.max_conns}', RGB(0x00ff7f))
        log(f'-> Debug mode: {glob.config.debug}', RGB(0x00ff7f))

        glob.ongoing_conns = []
        glob.shutting_down = False

        while not glob.shutting_down:
            # TODO: this timeout based-solution can be heavily
            #       improved and refactored out.
            try:
                conn, _ = await asyncio.wait_for(
                    fut=loop.sock_accept(listening_sock),
                    timeout=0.25
                )
            except asyncio.TimeoutError:
                pass
            else:
                task = loop.create_task(glob.app.handle(conn))
                task.add_done_callback(misc.utils._conn_finished_cb)
                glob.ongoing_conns.append(task)

    if sock_family == socket.AF_UNIX:
        # using unix socket - remove from filesystem
        os.remove(glob.config.server_addr)

async def main() -> int:
    """Initialize, and start up the server."""
    glob.loop = asyncio.get_running_loop()

    async with (
            misc.context.acquire_http_session(glob.has_internet) as glob.http_session):
        await misc.utils.check_for_dependency_updates()

        with (
            misc.context.acquire_mongodb(f'mongodb+srv://{glob.config.mongo["user"]}:{glob.config.mongo["password"]}@{glob.config.mongo["host"]}/{glob.config.mongo["db"]}?retryWrites=true&w=majority') as glob.db,
            misc.context.acquire_geoloc_db_conn(GEOLOC_DB_FILE) as glob.geoloc_db,
            misc.context.acquire_datadog_client(glob.config.datadog) as glob.datadog
        ):
            await initialize_ram_caches()
            
            # initialize housekeeping tasks to automatically manage
            # and ensure memory on ram & disk are kept up to date.
            await bg_loops.initialize_housekeeping_tasks()

            # handle signals so we can ensure a graceful shutdown
            sig_handler = misc.utils.shutdown_signal_handler
            for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                loop.add_signal_handler(signum, sig_handler, signum)

            # TODO: restart signal handler with SIGUSR1

            # run the server, handling connectionp
            # until a termination signal is received.
            await run_server()

            # we want to attempt to gracefully finish any ongoing connections
            # and shut down any of the housekeeping tasks running in the background.

            if glob.ongoing_conns:
                await misc.utils.await_ongoing_connections(timeout=5.0)

            await misc.utils.cancel_housekeeping_tasks()

    return 0

if __name__ == '__main__':
    """After basic safety checks, start the event loop and call our async entry point."""
    misc.utils.setup_runtime_environment()

    for safety_check in (
        misc.utils.ensure_supported_platform,  # linux only at the moment
        misc.utils.ensure_directory_structure,  # .data/ & achievements/ dir structure
        misc.utils.ensure_dependencies_and_requirements  # submodules & oppai-ng built
    ):
        if (exit_code := safety_check()) != 0:
            raise SystemExit(exit_code)

    """ Server should be safe to start """

    glob.boot_time = datetime.now()

    # install any debugging hooks from
    # _testing/runtime.py, if present
    misc.utils._install_debugging_hooks()

    # check our internet connection status
    glob.has_internet = misc.utils.check_connection(timeout=1.5)

    # show info & any contextual warnings.
    misc.utils.display_startup_dialog()

    try:
        # use uvloop if available
        # https://github.com/MagicStack/uvloop
        import uvloop
        uvloop.install()
    except ModuleNotFoundError:
        pass

    loop = asyncio.new_event_loop()
    
    try:
        asyncio.set_event_loop(loop)
        raise SystemExit(loop.run_until_complete(main()))
    finally:
        try:
            misc.utils._cancel_all_tasks(loop)
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.run_until_complete(loop.shutdown_default_executor())
        finally:
            asyncio.set_event_loop(None)
            loop.close()

elif __name__ == 'main':
    # check specifically for ASGI servers; many related projects use
    # them to run in production, and devs may assume we do as well.
    if misc.utils.running_via_asgi_webserver():
        raise RuntimeError(
            "gulag implements it's own web framework implementation from "
            "transport layer (tcp/ip) posix sockets and does not rely on "
            "an ASGI server to serve connections; run it directy, `./main.py`"
        )
    else:
        raise RuntimeError('gulag should only be run directly, `./main.py`')
