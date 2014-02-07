#!/usr/bin/env python
"""This script is to set up various things for our projects. It can be used by:

* developers - setting up their own environment
* jenkins - setting up the environment and running tests
* fabric - it will call a copy on the remote server when deploying

Usage:
    tasks.py [-d DEPLOYDIR] [options] <tasks>...
    tasks.py [-d DEPLOYDIR] -h | --help

Options:
    -t, --task-description     Describe the tasks instead of running them.
                               This will show the task docstring and a basic
                               description of the arguments it takes.
    -d, --deploydir DEPLOYDIR  Set the deploy dir (where to find
                               project_settings.py and, optionally,
                               localtasks.py)  Defaults to the directory that
                               contains tasks.py
    -n, --noinput              Never ask for input from the user (for scripts)
    -q, --quiet                Print less output while executing (note: not
                               none)
    -v, --verbose              Print extra output while executing
    --log-to-file              Log all output to a file called deploy.log in
                               the current directory.
    -h, --help                 Print this help text

You can pass arguments to the tasks listed below, by adding the argument after
a colon. So to call deploy and set the environment to staging you could do:

$ ./tasks.py deploy:staging

or you could name the argument and set the value after an equals sign:

$ ./tasks.py deploy:environment=staging

Multiple arguments are separated by commas:

$ ./tasks.py deploy:environment=staging,arg2=somevalue
"""

import os
import sys
import docopt
import inspect
import logging

from dye import tasklib
from dye.tasklib.exceptions import TasksError

localtasks = None


def invalid_command(cmd):
    print "Tasks.py:"
    print
    print "%s is not a valid command" % cmd
    print
    print "For help use --help"


def get_application_manager_class(project_type):
    if hasattr(localtasks, 'get_application_manager_class'):
        get_class = getattr(localtasks, 'get_application_manager_class')
    else:
        get_class = tasklib.get_application_manager_class
    return get_class(project_type)


def get_application_manager(project_type, **kwargs):
    return get_application_manager_class(project_type)(**kwargs)


def print_help_text():
    print __doc__
    try:
        import project_settings
    except ImportError:
        print "Cannot import project_settings so cannot give list of tasks"
        return
    tasks = sorted(get_application_manager_class(
        project_settings.project_type).tasks)
    print "The tasks you can use are:"
    print
    for task in tasks:
        print task
    print


def print_description(task_name, task_function):
    print "%s:" % task_name
    print
    if task_function.func_doc is not None:
        print task_function.func_doc
    else:
        print "No description found for %s" % task_name
    print
    argspec = inspect.getargspec(task_function)
    if len(argspec.args) == 0:
        if argspec.varargs is None:
            print "%s takes no arguments." % task_name
        else:
            print "%s takes no named arguments, but instead takes a variable " % task_name
            print "number of arguments."
    else:
        print "Arguments taken by %s:" % task_name
        for arg in argspec.args:
            print "* %s" % arg
        if argspec.varargs is not None:
            print
            print "You can also add a variable number of arguments."
    print


def describe_task(args):
    for arg in args:
        task = arg.split(':', 1)[0]
        if hasattr(localtasks, task):
            taskf = getattr(localtasks, task)
            print_description(task, taskf)
        elif hasattr(tasklib, task):
            taskf = getattr(tasklib, task)
            print_description(task, taskf)
        else:
            print "%s: no such task found" % task
            print


def setup_logging(quiet, verbose, log_to_file):
    if verbose:
        console_level = logging.DEBUG
    elif quiet:
        console_level = logging.WARNING
    else:
        console_level = logging.INFO

    if not log_to_file:
        logging.basicConfig(level=console_level)
    else:
        # log everything to file, and less to the console
        logging.basicConfig(level=logging.DEBUG, filename='deploy.log',
                            filemode='w')
        console = logging.StreamHandler()
        console.setLevel(console_level)
        logging.getLogger('').addHandler(console)


def convert_argument(value):
    if value.lower() == 'true':
        return True
    elif value.lower() == 'false':
        return False
    elif value.isdigit():
        return int(value)
    else:
        return value


def convert_task_bits(task_bits):
    """
    Take something like:

        my_task:val1,true,arg1=hello,arg2=3

    and convert it into the name, args and kwargs, so:

        (my_task, ('val1', True), {'arg1': 'hello', 'arg2': 3})

    Note that the 3 is converted into a number and 'true' is converted to boolean True
    """
    if ':' not in task_bits:
        return task_bits, (), {}
    task, args = task_bits.split(':', 1)
    args_list = args.split(',')

    pos_args = [convert_argument(arg) for arg in args_list if arg.find('=') == -1]

    kwargs = [arg for arg in args_list if arg.find('=') >= 0]
    kwargs_dict = {}
    for kwarg in kwargs:
        kw, value = kwarg.split('=', 1)
        kwargs_dict[kw] = convert_argument(value)

    return task, pos_args, kwargs_dict


def main(argv):
    global localtasks

    options = docopt.docopt(__doc__, argv, help=False)

    # need to set this before doing task-description or help
    if options['--deploydir']:
        deploy_dir = options['--deploydir']
    else:
        deploy_dir = os.path.dirname(__file__)
    # first we need to find and load the project settings
    sys.path.append(deploy_dir)
    # now see if we can find localtasks
    # We deliberately don't surround the import by try/except. If there
    # is an error in localfab, you want it to blow up immediately, rather
    # than silently fail.
    if os.path.isfile(os.path.join(deploy_dir, 'localtasks.py')):
        import localtasks

    if options['--help']:
        print_help_text()
        return 0
    if options['--task-description']:
        describe_task(options['<tasks>'])
        return 0
    quiet = options['--quiet']
    verbose = options['--verbose']
    noinput = options['--noinput']
    if verbose and quiet:
        print >>sys.stderr, "Cannot set both verbose and quiet"
        return 2
    setup_logging(quiet, verbose, options['--log-to-file'])

    try:
        import project_settings
    except ImportError:
        logging.critical(
            "Could not import project_settings - check your --deploydir argument")
        return 1

    # now set up the various paths required
    app_manager = get_application_manager(
        project_settings.project_type,
        project_settings, localtasks,
        quiet, verbose, noinput
    )
    # process arguments - just call the function with that name
    for arg in options['<tasks>']:
        fname, pos_args, kwargs = convert_task_bits(arg)
        # work out which method to call - localtasks will have overridden
        # the class if necessary
        f = None
        if fname in app_manager.tasks:
            f = getattr(app_manager, fname)
        else:
            invalid_command(fname)
            return 2

        # call the function
        try:
            f(*pos_args, **kwargs)
        except TasksError as e:
            print >>sys.stderr, e.msg
            return e.exit_code


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
