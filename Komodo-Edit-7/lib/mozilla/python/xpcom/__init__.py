# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1/GPL 2.0/LGPL 2.1
#
# The contents of this file are subject to the Mozilla Public License Version
# 1.1 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
# for the specific language governing rights and limitations under the
# License.
#
# The Original Code is the Python XPCOM language bindings.
#
# The Initial Developer of the Original Code is
# Activestate Tool Corp.
# Portions created by the Initial Developer are Copyright (C) 2000
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#   Mark Hammond <MarkH@activestate.com>
#
# Alternatively, the contents of this file may be used under the terms of
# either the GNU General Public License Version 2 or later (the "GPL"), or
# the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
# in which case the provisions of the GPL or the LGPL are applicable instead
# of those above. If you wish to allow use of your version of this file only
# under the terms of either the GPL or the LGPL, and not to allow others to
# use your version of this file under the terms of the MPL, indicate your
# decision by deleting the provisions above and replace them with the notice
# and other provisions required by the GPL or the LGPL. If you do not delete
# the provisions above, a recipient may use your version of this file under
# the terms of any one of the MPL, the GPL or the LGPL.
#
# ***** END LICENSE BLOCK *****
#

# The XPCOM (Cross Platform COM) package.
import exceptions

import os
_location = os.path.dirname(__file__)

# A global "verbose" flag - currently used by the
# server package to print trace messages
verbose = 0
# Map of nsresult -> constant_name.
hr_map = {}

class nsStackFrame:
    language = 0 # what should it be?
    languageName = "Python"

    def __init__(self, tb):
        try:
            # magic to hook up com interface after xpcom is loaded
            if not hasattr(nsStackFrame, "_com_interfaces_"):
                from xpcom import components
                nsStackFrame._com_interfaces_ = [components.interfaces.nsIStackFrame]
        except Exception, e:
            # not initialized yet, cannot make this an xpcom component
            pass

        self.caller = None

        import linecache
    
        f = tb.tb_frame
        self.lineNumber = tb.tb_lineno
        co = f.f_code
        self.filename = co.co_filename
        self.name = co.co_name
        linecache.checkcache(self.filename)
        line = linecache.getline(self.filename, self.lineNumber)
        if line: self.sourceLine = line.strip()
        else: self.sourceLine = None

    def toString(self):
        return 'File "%s", line %d, in %s' % (self.filename,
                                              self.lineNumber,
                                              self.name)

# The standard XPCOM exception object.
# Instances of this class are raised by the XPCOM extension module.
class Exception(exceptions.Exception):
    def __init__(self, errno, message = None):
        assert int(errno) == errno, "The errno param must be an integer"
        exceptions.Exception.__init__(self, errno)
        try:
            # Magic to hook up com interface after xpcom is loaded.
            # The "NS_ERROR_NO_INTERFACE" check is to avoid an infinite
            # loop when XPCOM isn't registered and hence
            # `components.interface.nsIException` results in a
            # COMException.
            if not hasattr(Exception, "_com_interfaces_") \
               and errno != nsError.NS_ERROR_NO_INTERFACE:
                Exception._com_interfaces_ = [components.interfaces.nsIException]
        except exceptions.Exception, e:
            # not initialized yet, cannot make this an xpcom component
            pass

        self.errno = errno
        self.msg = message
        self.result = errno
        self.name = hr_map.get(self.errno, "")
        self.filename = None
        self.lineNumber = 0
        self.columnNumber = 0
        self.location = None
        self.inner = None
        self.data = None

    # backwards compat when running under python 2.6
    @apply
    def message():
    
        def get(self):
            return self.msg
    
        def set(self, value):
            self.msg = value
    
        return property(get, set)

    def setExcInfo(self, exc_info):
        if exc_info[2]:
            self.setStackFrame(exc_info[2])
        
    def setStackFrame(self, tb):
        caller = None
        while tb.tb_next is not None:
            f = nsStackFrame(tb)
            if not f.filename.startswith(_location):
                prev_caller = caller
                caller = f
                caller.caller = prev_caller
            tb = tb.tb_next

        f = nsStackFrame(tb)
        if caller and f.filename[0] == "<":
            self.location = caller
            self.location.caller = caller.caller
        else:
            self.location = f
            self.location.caller = caller
        self.lineNumber = f.lineNumber
        self.filename = f.filename
        self.name = f.name

    def setData(self, exc_info):
        import traceback
        textObj = components.classes["@mozilla.org/supports-string;1"]\
                .createInstance(components.interfaces.nsISupportsString)
        textObj.data = '\n'.join(traceback.format_tb(exc_info[2]))
        self.data = textObj;

    def __str__(self):
        if self.message is None:
            return self.name
        return str(self.message)
    def toString(self):
        return str(self)

# An alias for Exception - allows code to say "from xpcom import COMException"
# rather than "Exception", preventing clashes with the builtin Exception
COMException = Exception

# Exceptions thrown by servers.  It can be good for diagnostics to
# differentiate between a ServerException (which was presumably explicitly thrown)
# and a normal exception which may simply be propagating down.
# (When ServerException objects are thrown across the XPConnect
# gateway they will be converted back to normal client exceptions if
# subsequently re-caught by Python)
class ServerException(Exception):
    def __init__(self, errno=None, *args, **kw):
        if errno is None:
            import nsError
            errno = nsError.NS_ERROR_FAILURE
        Exception.__init__(self, errno, *args, **kw)

# Logging support - setup the 'xpcom' logger to write to the Mozilla
# console service, and also to sys.stderr, or optionally a file.
# Environment variables supports:
# PYXPCOM_LOG_FILE=filename - if set, used instead of sys.stderr.
# PYXPCOM_LOG_LEVEL=level - level may be a number or a logging level
#                           constant (eg, 'debug', 'error')
# Later it may make sense to allow a different log level to be set for
# the file than for the console service.
import logging
class ConsoleServiceStream:
    # enough of a stream to keep logging happy
    def flush(self):
        pass
    def write(self, msg):
        import _xpcom
        _xpcom.LogConsoleMessage(msg)
    def close(self):
        pass

def setupLogging():
    import sys, os, threading, thread
    hdlr = logging.StreamHandler(ConsoleServiceStream())
    fmt = logging.Formatter(logging.BASIC_FORMAT)
    hdlr.setFormatter(fmt)
    # There is a bug in 2.3 and 2.4.x logging module in that it doesn't
    # use an RLock, leading to deadlocks in some cases (specifically,
    # logger.warning("ob is %r", ob), and where repr(ob) itself tries to log)
    # Later versions of logging use an RLock, so we detect an "old" style
    # handler and update its lock
    if type(hdlr.lock) == thread.LockType:
        hdlr.lock = threading.RLock()

    logger.addHandler(hdlr)
    # The console handler in mozilla does not go to the console!?
    # Add a handler to print to stderr, or optionally a file
    # PYXPCOM_LOG_FILE can specify a filename
    filename = os.environ.get("PYXPCOM_LOG_FILE")
    stream = sys.stderr # this is what logging uses as default
    if filename:
        try:
            # open without buffering so never pending output
            stream = open(filename, "wU", 0)
        except IOError, why:
            print >> sys.stderr, "pyxpcom failed to open log file '%s': %s" \
                                 % (filename, why)
            # stream remains default

    hdlr = logging.StreamHandler(stream)
    # see above - fix a deadlock problem on this handler too.
    if type(hdlr.lock) == thread.LockType:
        hdlr.lock = threading.RLock()

    fmt = logging.Formatter(logging.BASIC_FORMAT)
    hdlr.setFormatter(fmt)
    logger.addHandler(hdlr)
    # Allow PYXPCOM_LOG_LEVEL to set the level
    level = os.environ.get("PYXPCOM_LOG_LEVEL")
    if level:
        try:
            level = int(level)
        except ValueError:
            try:
                # might be a symbolic name - all are upper-case
                level = int(getattr(logging, level.upper()))
            except (AttributeError, ValueError):
                logger.warning("The PYXPCOM_LOG_LEVEL variable specifies an "
                               "invalid level")
                level = None
        if level:
            logger.setLevel(level)

logger = logging.getLogger('xpcom')
# If someone else has already setup this logger, leave things alone.
if len(logger.handlers) == 0:
    setupLogging()

# Cleanup namespace - but leave 'logger' there for people to use, so they
# don't need to know the exact name of the logger.
del ConsoleServiceStream, logging, setupLogging
