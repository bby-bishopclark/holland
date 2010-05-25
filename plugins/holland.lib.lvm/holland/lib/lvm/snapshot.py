"""LVM Snapshot state machine"""

import sys
import signal
import logging
from holland.lib.lvm import LogicalVolume
from holland.lib.lvm.errors import LVMCommandError
from holland.lib.lvm.util import SignalManager

LOG = logging.getLogger(__name__)

__all__ = [
    'Snapshot',
    'CallbackFailuresError',
]

class Snapshot(object):
    """Snapshot state machine"""
    def __init__(self, name, size, mountpoint):
        self.name = name
        self.size = size
        self.mountpoint = mountpoint
        self.callbacks = {}
        self.sigmgr = SignalManager()

    def start(self, volume):
        """Start the snapshot process to snapshot the logical volume
        that ``path`` exists on.

        """
        self.sigmgr.trap(signal.SIGINT)
        self._apply_callbacks('initialize', self)
        return self.create_snapshot(volume)

    def create_snapshot(self, logical_volume):
        """Create a snapshot for the given logical volume

        """

        try:
            self._apply_callbacks('pre-snapshot', self)
            snapshot = logical_volume.snapshot(self.name, self.size)
        except (LVMCommandError, CallbackFailuresError), exc:
            return self.error(None, exc)

        try:
            self._apply_callbacks('post-snapshot', self, snapshot)
        except CallbackFailuresError, exc:
            return self.error(snapshot, exc)

        return self.mount_snapshot(snapshot)

    def mount_snapshot(self, snapshot):
        """Mount the snapshot"""

        try:
            self._apply_callbacks('pre-mount', self, snapshot)
            options = None
            if snapshot.filesystem == 'xfs':
                options = 'nouuid'
            snapshot.mount(self.mountpoint, options)
            self._apply_callbacks('post-mount', self, snapshot)
        except (CallbackFailuresError, LVMCommandError), exc:
            return self.error(snapshot, exc)

        return self.unmount_snapshot(snapshot)

    def unmount_snapshot(self, snapshot):
        """Unmount the snapshot"""
        try:
            self._apply_callbacks('pre-unmount', snapshot)
            snapshot.unmount()
        except (CallbackFailuresError, LVMCommandError), exc:
            return self.error(snapshot, exc)

        try:
            self._apply_callbacks('post-unmount', snapshot)
        except CallbackFailuresError, exc:
            return self.error(snapshot, exc)

        return self.remove_snapshot(snapshot)

    def remove_snapshot(self, snapshot):
        """Remove the snapshot"""
        try:
            self._apply_callbacks('pre-remove', snapshot)
            snapshot.remove()
        except (CallbackFailuresError, LVMCommandError), exc:
            return self.error(snapshot, exc)

        try:
            self._apply_callbacks('post-remove', snapshot)
        except (CallbackFailuresError), exc:
            return self.error(snapshot, exc)

        return self.finish()

    def finish(self):
        """Finish the snapshotting process"""
        self.sigmgr.restore()
        self._apply_callbacks('finish', self)

    def error(self, snapshot, exc):
        """Handle an error during the snapshot process"""
        LOG.error("Error encountered during snapshot processing: %s", exc)

        if snapshot and snapshot.exists():
            try:
                if snapshot.is_mounted():
                    snapshot.unmount()
                if snapshot.exists():
                    snapshot.remove()
            except LVMCommandError, exc:
                LOG.error("Failed to remove snapshot %s", exc)

        self._apply_callbacks('error', self)
        return self.finish()

    def register(self, event, callback, priority=100):
        """Register a callback for ``event`` with ``priority``

        """
        self.callbacks.setdefault(event, []).append((priority, callback))

    def _apply_callbacks(self, event, *args, **kwargs):
        """Apply callbacks for event"""
        callback_list = list(self.callbacks.get(event, []))
        callback_list.sort(reverse=True)
        callback_list = [callback[1] for callback in callback_list]
        errors = []
        for callback in callback_list:
            try:
                callback(event, *args, **kwargs)
            except:
                exc = sys.exc_info()[1]
                errors.append((callback, exc))

        if errors:
            raise CallbackFailuresError(errors)

class CallbackFailuresError(Exception):
    """Error running callbacks"""

    def __init__(self, errors):
        Exception.__init__(self, errors)
        self.errors = errors

