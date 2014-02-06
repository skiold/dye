import os
from os import path
from getpass import getpass
import logging

from .exceptions import InvalidPasswordError

# make sure WindowsError is available
import __builtin__
if not hasattr(__builtin__, 'WindowsError'):
    class WindowsError(OSError):
        pass

try:
    # For testing replacement routines for older python compatibility
    # raise ImportError()
    import subprocess
    from subprocess import call as call_command

    def capture_command(argv):
        return subprocess.Popen(argv, stdout=subprocess.PIPE).communicate()[0]

except ImportError:
    # this section is for python older than 2.4 - basically for CentOS 4
    # when we have to use it
    def capture_command(argv):
        command = ' '.join(argv)
        # logging.debug("(capture_command) Executing: %s" % command)
        fd = os.popen(command)
        output = fd.read()
        fd.close()
        return output

    # older python - shell arg is ignored, but is legal
    def call_command(argv, stdin=None, stdout=None, shell=True):
        argv = [i.replace('"', '\"') for i in argv]
        argv = ['"%s"' % i for i in argv]
        command = " ".join(argv)

        if stdin is not None:
            command += " < " + stdin.name

        if stdout is not None:
            command += " > " + stdout.name

        # logging.debug("(call_command) Executing: %s\n" % command)

        return os.system(command)

try:
    from subprocess import CalledProcessError
except ImportError:
    # the Error does not exist in python 2.4
    class CalledProcessError(Exception):
        """This exception is raised when a process run by check_call() returns
        a non-zero exit status.  The exit status will be stored in the
        returncode attribute."""
        def __init__(self, returncode, cmd):
            self.returncode = returncode
            self.cmd = cmd

        def __str__(self):
            return "Command '%s' returned non-zero exit status %d" % \
                (self.cmd, self.returncode)


def call_wrapper(argv, **kwargs):
    if hasattr(argv, '__iter__'):
        command = ' '.join(argv)
    else:
        command = argv
    logging.debug("Executing command: %s" % command)
    return call_command(argv, **kwargs)


def check_call_wrapper(argv, accepted_returncode_list=[0], **kwargs):
    try:
        returncode = call_wrapper(argv, **kwargs)

        if returncode not in accepted_returncode_list:
            raise CalledProcessError(returncode, argv)
    except WindowsError:
        raise CalledProcessError("Unknown", argv)


def create_dir_if_not_exists(dir_path, world_writeable=False, owner=None):
    if not path.exists(dir_path):
        check_call_wrapper(['mkdir', '-p', dir_path])
    if world_writeable:
        check_call_wrapper(['chmod', '-R', '777', dir_path])
    if owner:
        check_call_wrapper(['chown', '-R', owner, dir_path])


def rm_all_pyc(vcs_root_dir):
    """Remove all pyc files, to be sure"""
    call_wrapper('find . -type f -name \*.pyc -exec rm {} \\;',
                 shell=True, cwd=vcs_root_dir)


def ask_for_password(prompt, test_fn=None, max_attempts=3):
    """Get password from user.

    prompt is the text for the password prompt
    test_fn is a function to test the password.  It should return True if
            the password works, or False otherwise.
    """
    password = None
    attempts = 0
    while password is None:
        if attempts < max_attempts:
            attempts += 1
            password = getpass(prompt)
            if test_fn and not test_fn(password):
                print "Sorry, invalid password"
                password = None
        else:
            raise InvalidPasswordError("None of your passwords worked")
    return password


def get_file_contents(file_path, sudo=False):
    if sudo:
        try:
            # we use this rather than file exists so that the script doesn't
            # have to be run as root
            file_exists = call_wrapper(['sudo', 'test', '-f', file_path])
        except (WindowsError, CalledProcessError):
            return None
        if file_exists != 0:
            return None
        # note this requires sudoers to work with this - jenkins particularly
        contents = capture_command(["sudo", "cat", file_path])
    else:
        if not path.isfile(file_path):
            return None
        contents = open(file_path).read()
    return contents.rstrip()
