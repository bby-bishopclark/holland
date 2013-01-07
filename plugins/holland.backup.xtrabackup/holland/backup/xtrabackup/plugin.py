"""
holland.mysql.xtrabackup
~~~~~~~~~~~~~~~~~~~~~~~

Xtrabackup backup strategy plugin
"""

import sys
import logging
from os.path import join
from holland.core.backup import BackupError
from holland.core.util.path import directory_size
from holland.lib.compression import open_stream
from holland.backup.xtrabackup.mysql import MySQL
from holland.backup.xtrabackup import util

LOG = logging.getLogger(__name__)

CONFIGSPEC = """
[xtrabackup]
global-defaults     = string(default='/etc/my.cnf')
innobackupex        = string(default='innobackupex-1.5.1')
ibbackup            = string(default=None)
stream              = option(yes,no,tar,xbstream,default=tar)
apply-logs          = boolean(default=yes)
slave-info          = boolean(default=no)
safe-slave-backup   = boolean(default=no)
no-lock             = boolean(default=no)
tmpdir              = string(default=None)
additional-options  = force_list(default=list())
pre-command         = string(default=None)

[compression]
method              = option('none', 'gzip', 'pigz', 'bzip2', 'pbzip2', 'lzma', 'lzop', default=gzip)
inline              = boolean(default=yes)
level               = integer(min=0, max=9, default=1)

[mysql:client]
defaults-extra-file = force_list(default=list('~/.my.cnf'))
user                = string(default=None)
password            = string(default=None)
socket              = string(default=None)
host                = string(default=None)
port                = integer(min=0, default=None)
""".splitlines()

class XtrabackupPlugin(object):
    #: control connection to mysql server
    mysql = None

    #: path to the my.cnf generated by this plugin
    defaults_path = None

    def __init__(self, name, config, target_directory, dry_run=False):
        self.name = name
        self.config = config
        self.config.validate_config(CONFIGSPEC)
        self.target_directory = target_directory
        self.dry_run = dry_run

        defaults_path = join(self.target_directory, 'my.cnf')
        client_opts = self.config['mysql:client']
        includes = [self.config['xtrabackup']['global-defaults']] + \
                   client_opts['defaults-extra-file']
        util.generate_defaults_file(defaults_path, includes, client_opts)
        self.defaults_path = defaults_path

    def estimate_backup_size(self):
        try:
            client = MySQL.from_defaults(self.defaults_path)
        except MySQL.MySQLError, exc:
            raise BackupError('Failed to connect to MySQL [%d] %s' % exc.args)
        try:
            try:
                datadir = client.var('datadir')
                return directory_size(datadir)
            except MySQL.MySQLError, exc:
                raise BackupError("Failed to find mysql datadir: [%d] %s" %
                                  exc.args)
            except OSError, exc:
                raise BackupError('Failed to calculate directory size: [%d] %s'
                                  % (exc.errno, exc.strerror))
        finally:
            client.close()

    def open_xb_logfile(self):
        """Open a file object to the log output for xtrabackup"""
        path = join(self.target_directory, 'xtrabackup.log')
        try:
            return open(path, 'a')
        except IOError, exc:
            raise BackupError('[%d] %s' % (exc.errno, exc.strerror))

    def open_xb_stdout(self):
        """Open the stdout output for a streaming xtrabackup run"""
        config = self.config['xtrabackup']
        backup_directory = self.target_directory
        if config['stream'] in ('tar', 'tar4ibd', 'xbstream'):
            # XXX: bounce through compression
            if 'tar' in config['stream']:
                archive_path = join(backup_directory, 'backup.tar')
                zconfig = self.config['compression']
                return open_stream(archive_path, 'w',
                                        method=zconfig['method'],
                                        level=zconfig['level'])
            elif 'xbstream' in config['stream']:
                archive_path = join(backup_directory, 'backup.xb')
                return open(archive_path, 'w')
        else:
            return open('/dev/null', 'w')


    def dryrun(self):
        from subprocess import Popen, list2cmdline, PIPE, STDOUT
        xb_cfg = self.config['xtrabackup']
        args = util.build_xb_args(xb_cfg, self.target_directory,
                self.defaults_path)
        LOG.info("* xtrabackup command: %s", list2cmdline(args))
        args = [
            'xtrabackup',
            '--defaults-file=' + self.defaults_path,
            '--help'
        ]
        cmdline = list2cmdline(args)
        LOG.info("* Verifying generated config '%s'", self.defaults_path)
        LOG.debug("* Verifying via command: %s", cmdline)
        try:
            process = Popen(args, stdout=PIPE, stderr=STDOUT, close_fds=True)
        except OSError, exc:
            raise BackupError("Failed to find xtrabackup binary")
        stdout = process.stdout.read()
        process.wait()
        # Note: xtrabackup --help will exit with 1 usually
        if process.returncode != 1:
            LOG.error("! %s failed. Output follows below.", cmdline)
            for line in stdout.splitlines():
                LOG.error("! %s", line)
            raise BackupError("%s exited with failure status [%d]" %
                              (cmdline, process.returncode))

    def backup(self):
        if self.dry_run:
            self.dryrun()
            return
        xb_cfg = self.config['xtrabackup']
        backup_directory = self.target_directory
        args = util.build_xb_args(xb_cfg, backup_directory, self.defaults_path)
        util.execute_pre_command(xb_cfg['pre-command'])
        stderr = self.open_xb_logfile()
        try:
            stdout = self.open_xb_stdout()
            exc = None
            try:
                try:
                    util.run_xtrabackup(args, stdout, stderr)
                except Exception, exc:
                    LOG.info("!! %s", exc)
                    for line in open(join(self.target_directory, 'xtrabackup.log'), 'r'):
                        LOG.error("    ! %s", line.rstrip())
                    raise
            finally:
                try:
                    stdout.close()
                except IOError, e:
                    LOG.error("Error when closing %s: %s", stdout.name, e)
                    if exc is None:
                        raise
        finally:
            stderr.close()
        if xb_cfg['apply-logs']:
            util.apply_xtrabackup_logfile(xb_cfg, args[-1])

