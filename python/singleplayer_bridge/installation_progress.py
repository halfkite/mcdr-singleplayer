"""Installer/controller feedback belongs to one client launch, never a shared world."""
import logging
import re
from pathlib import Path

from .profiles import write_json


class InstallationProgress:
    def __init__(self, common, client_id):
        self.client_id = client_id
        root = Path(common) / 'runtime'
        if client_id is not None:
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', client_id):
                raise ValueError('Invalid client launch identifier')
            root = root / 'clients' / client_id
        self.path = root / 'install-progress.json'

    def report(self, stage, attempt=0):
        try:
            write_json(self.path, dict(protocol=1, client_id=self.client_id, stage=stage, attempt=attempt))
        except OSError:
            logging.warning('Could not publish installation progress', exc_info=True)
