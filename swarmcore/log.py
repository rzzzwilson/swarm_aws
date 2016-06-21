#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
A simple logger.

Based on the 'borg' recipe from [http://code.activestate.com/recipes/66531/].
"""

import os
import shutil
import time
import datetime
import traceback


# default maximum length of filename
MaxNameLength = 15


################################################################################
# A simple logger.
# 
# Simple usage:
#     import log
#     log = log.Log('my_log.txt', Log.DEBUG)
#     log('A line in the log at the default level (DEBUG)')
#     log('A log line at WARN level', Log.WARN)
#     log.debug('log line issued at DEBUG level')
# 
# Log levels styled on the Python 'logging' module.
################################################################################

class Log(object):

    __shared_state = {}                # this __dict__ shared by ALL instances

    # the predefined logging levels
    CRITICAL = 50
    ERROR = 40
    WARN = 30
    INFO = 20
    DEBUG = 10
    NOTSET = 0

    _level_num_to_name = {NOTSET: 'NOTSET',
                          DEBUG: 'DEBUG',
                          INFO: 'INFO',
                          WARN: 'WARN',
                          ERROR: 'ERROR',
                          CRITICAL: 'CRITICAL'}

    def __init__(self, logfile=None, level=NOTSET, append=False,
                 name_length=MaxNameLength):
        """Initialise the logging object.

        logfile      the path to the log file
        level        logging level - don't log below this level
        append       True if log file is appended to
        name_length  max length of module name in log output
        """

        # make sure we have same state as all other log objects
        self.__dict__ = Log.__shared_state

        # don't allow logfile to change after initially set
        if hasattr(self, 'logfile'):
            self.critical('Ignore attempt to reconfigure logging')
            return

        # OK, configure logging
        if logfile is None:
            logfile = '%s.log' % __name__

        # get correct open option
        opt = 'w'
        if append:
            opt = 'a'

        try:
            self.logfd = open(logfile, opt)
        except IOError:
            # assume we have readonly filesystem, create elsewhere
            basefile = os.path.basename(logfile)
            if os.name == 'nt':
                # TODO: should use user-specific directory?
                logfile = os.path.join('C:\\', basefile)
            elif os.name == 'posix':
                logfile = os.path.join('~', basefile)
            else:
                raise Exception('Unrecognized platform: %s' % os.name)

        # try to open logfile again
        self.logfd = open(logfile, opt)
        self.logfile = logfile

        # convert 'level' param to a number if it was a string
        if isinstance(level, basestring):
            new_level = Log.NOTSET
            for (l, n) in Log._level_num_to_name.items():
                if str(level) == n:
                    new_level = l
                    break
            level = new_level
        self.level = level
        self.name_length = name_length

        self.critical('='*65)
        self.critical('Log started on %s, log level=%s'
                      % (datetime.datetime.now().ctime(), self.level2string()))
        self.critical('-'*65)

    def __call__(self, msg=None, level=None):
        """Call on the logging object.

        msg    message string to log
        level  level to log 'msg' at (if not given, assume self.level)
        """

        # get level to log at
        if level is None:
            level = self.level

        # are we going to log?
        if level < self.level:
            return

        if msg is None:         # if user just wants a blank line
            msg = ''

        # get time
        to = datetime.datetime.now()
        hr = to.hour
        min = to.minute
        sec = to.second
        msec = to.microsecond

        # caller information - look back for first module != <this module name>
        frames = traceback.extract_stack()
        frames.reverse()
        try:
            (_, mod_name) = __name__.rsplit('.', 1)
        except ValueError:
            mod_name = __name__
        for (fpath, lnum, mname, _) in frames:
            fname = os.path.basename(fpath).rsplit('.', 1)
            if len(fname) > 1:
                fname = fname[0]
            if fname != mod_name:
                break

        # get string for log level
        loglevel = (self.level2string() + '       ')[:8]

        fname = fname[:self.name_length]
        self.logfd.write('%02d:%02d:%02d.%06d|%8s|%*s:%-4d|%s\n'
                         % (hr, min, sec, msec, loglevel, self.name_length,
                            fname, lnum, msg))
        self.logfd.flush()

    def critical(self, msg):
        """Log a message at CRITICAL level."""

        self(msg, Log.CRITICAL)

    def error(self, msg):
        """Log a message at ERROR level."""

        self(msg, Log.ERROR)

    def warn(self, msg):
        """Log a message at WARN level."""

        self(msg, Log.WARN)

    def info(self, msg):
        """Log a message at INFO level."""

        self(msg, Log.INFO)

    def debug(self, msg):
        """Log a message at DEBUG level."""

        self(msg, Log.DEBUG)

    def __del__(self):
        self.logfd.close()

    def set_level(self, level):
        self.level = level
        self('Set logging level to %d' % level, Log.CRITICAL)

    def bump_level(self):
        if self.level > Log.DEBUG:
            self.level -= 10
        if self.level < Log.DEBUG:
            self.level = Log.DEBUG
        self('Set logging level to %s' % self.level2string(), Log.CRITICAL)

    def level2string(self):
        """Convert a logging level to a string."""

        base_level = int(self.level / 10) * 10
        rem_level = self.level % 10
        base_level_str = Log._level_num_to_name[base_level]
        if rem_level == 0:
            return base_level_str
        else:
            return '%s+%d' % (base_level_str, rem_level)


