"""
A set of classifier functions that take a VM console log
and try to classify the VM state.

All classifiers have the signature:

    class_????(log)

where 'log' is a list of lines from the console log.

The classify() function will try all classifiers in this module.

The classifiers will return a string containing the classification
or None if the log can't be classified.
"""


def class_no_log(log):
    """An error classifier.

    log    the console log text

    Return None if not recognized, else the error type string.
    """

    if len(log) == 1 and log[0] == '':
        return "Can't retrieve log"
    if len(log) == 1 and log[0] == '?':
        return "Log was just '?'"
    return None


def class_fsck_manual(log):
    """An error classifier.

    log    the console log text

    Return None if not recognized, else the error type string.
    """

    if 'UNEXPECTED INCONSISTENCY; RUN fsck MANUALLY' in log:
        return 'FSCK_manual'
    return None


def class_ldap(log):
    """An error classifier.

    log    the console log text

    Return None if not recognized, else the error type string.
    """

    if 'failed to bind to LDAP server' in log:
        return 'LDAP failure'
    return None


def class_rofs(log):
    """An error classifier.

    log    the console log text

    Return None if not recognized, else the error type string.
    """

    if ('Read-only file system' in log or
            'Remounting filesystem read-only' in log):
        return 'ROFS'
    return None


def class_ioerror(log):
    """An error classifier.

    log    the console log text

    Return None if not recognized, else the error type string.
    """

    if ('ext3_abort called' in log and
            'Read-only file system' not in log and
            'Remounting filesystem read-only' not in log):
        return 'IOERROR'
    return None


def class_nologin(log):
    """An error classifier.

    log    the console log text

    Return None if not recognized, else the error type string.
    """
    import tempfile
    (f, fname) = tempfile.mkstemp(prefix='vm_health_')
    with open(fname, 'wb') as fd:
        fd.write(log)

    # if runaway loop, we can't continue
    if 'request_module: runaway loop' in log:
        return None

    #if '.org.au login: ' not in log:
    if ' login: ' not in log:
        return 'HUNG, no login prompt'

    return None


def class_runaway_loop(log):
    """An error classifier.

    log    the console log text

    Return None if not recognized, else the error type string.
    """

    if 'request_module: runaway loop' in log:
        return 'RUNAWAY_LOOP'
    return None


def class_network_unreachable(log):
    """An error classifier.

    log    the console log text

    Return None if not recognized, else the error type string.
    """

    if 'Network is unreachable' in log:
        return 'NETWORK_UNREACHABLE'
    return None


# classifier functions, in the order they are applied
classifiers = [class_fsck_manual, class_ldap,
               class_rofs, class_ioerror, class_nologin,
               class_runaway_loop, class_network_unreachable,
               class_no_log,
              ]

def classify(console):
    """Classify the contents of a server console log."""

    # run through all the classifier functions
    for c in classifiers:
        result = c(console)
        if result is not None:
            return result
    return 'OK'
