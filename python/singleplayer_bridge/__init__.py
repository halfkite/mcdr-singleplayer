"""MCDR entrypoint. The standalone proxy needs only Python's standard library."""

__version__ = '0.4.1'


def on_load(server, prev_module):
    from . import plugin
    plugin.load(server, prev_module)


def on_server_start(server):
    server.set_exit_after_stop_flag(False)


def on_info(server, info):
    from . import plugin
    plugin.observe(info, server)


def on_server_stop(server, return_code):
    from . import plugin
    plugin.reset()


def on_unload(server):
    from . import plugin
    plugin.unload()
