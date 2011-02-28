# -*- coding: utf-8 -*-
"""
Plugin for the Holland backup framework
to backup Postgres databases using pg_dump
and pg_dumpall
"""

import os
import sys
import logging
from tempfile import NamedTemporaryFile
from holland.core import BackupError, BackupPlugin, Configspec
from holland.backup.pgdump.base import backup_pgsql, dry_run, \
                                       PgError, \
                                       dbapi, \
                                       pg_databases, \
                                       get_connection, get_db_size

LOG = logging.getLogger(__name__)

# This is a specification of what our configuration must include
# values are validate.py functions.  See:
# http://www.voidspace.org.uk/python/validate.html

# NOTE: this configuration isn't actually obeyed by the implementation
#       These are just various options that *might* be useful for pg_dump
#       to support (namely database/schema/table inclusion/exclusion).
# Anyone who picks up this plugin will likely want to trim or add to this
# as it makes sense
CONFIGSPEC = """
[pgdump]
format = option('plain','tar','custom', default='custom')
role = string(default=None)
additional-options = string(default=None)

[compression]
method = option('gzip', 'bzip2', 'lzop', 'lzma', 'pigz', 'none', default='gzip')
level = integer(min=0, default=1)

[pgauth]
username = string(default=None)
password = string(default=None)
hostname = string(default=None)
port = integer(default=None)
""".splitlines()

class PgDump(BackupPlugin):
    """
    Postgres pg_dump backups
    """

    def __init__(self, name):
        """Create a new PgDump instance

        :param name: name this plugin was loaded by
        """
        self.name = name
        self.dry_run = False


    def pre(self):
        self.connection = get_connection(self.config)
        self.databases = pg_databases(self.config, self.connection)
        LOG.info("Found databases: %s", ','.join(self.databases))

    def estimate(self):
        """Estimate the size (in bytes) of the backup this plugin would
        produce, if run.


        :returns: int. size in bytes
        """

        totalestimate = 0
        for db in self.databases:
            try:
                totalestimate += get_db_size(db, self.connection)
            except dbapi.DatabaseError, exc:
                if exc.pgcode != '42883': # 'missing function'
                    raise BackupError("Failed to estimate database size for "
                                      "%s: %s" % (db, exc))
                totalestimate += self._estimate_legacy_size(db)

        return totalestimate

    def _estimate_legacy_size(self, db):
        try:
            connection = get_connection(self.config, db)
            size = legacy_get_db_size(db, connection)
            connection.close()
            return size
        except dbapi.DatabaseError, exc:
            raise BackupError("Failed to estimate database size for %s: %s" %
                              (db, exc))

    def backup(self):
        """
        Start a backup.
        """

        # First run a pg_dumpall -g and save the globals
        # Then run a pg_dump for each database we find
        backup_dir = os.path.join(self.store.path, 'data')

        # put everything in data/
        try:
            os.mkdir(backup_dir)
        except OSError, exc:
            raise BackupError("Failed to create backup directory %s" % backup_dir)

        try:
            backup_pgsql(backup_dir, self.config, self.databases)
        except (OSError, PgError), exc:
            LOG.debug("Failed to backup Postgres. %s",
                          str(exc), exc_info=True)
            raise BackupError(str(exc))

    def dry_run(self):
        # Very simply dry run information
        # enough to know that:
        # 1) We can connect to Postgres using pgpass data
        # 2) The exact databases we would dump
        dry_run(self.databases, self.config)

    def configspec(self):
        """Provide a specification for the configuration dictionary this
        plugin accepts.
        """
        return Configspec.parse(CONFIGSPEC)