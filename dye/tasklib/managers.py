import os
from os import path
import sys
import logging
import random
import subprocess

from .exceptions import TasksError
from .database import get_db_manager
from .exceptions import InvalidProjectError, ShellCommandError
from .util import call_wrapper, check_call_wrapper, rm_all_pyc


class AppManager(object):

    tasks = (
        'deploy', 'create_private_settings', 'link_local_settings',
        'update_git_submodules',
        'create_test_db', 'clean_db', 'update_db',
        'quick_test', 'run_tests', 'run_jenkins',
        'dump_db', 'restore_db',
        'setup_db_dumps', 'create_dbdump_cron_file',
    )

    def __init__(self, project_settings, localtasks=None,
                 quiet=False, verbose=False, noinput=False, **kwargs):
        self.environment = None
        self.quiet = quiet
        self.verbose = verbose
        self.noinput = noinput
        self.localtasks_module = localtasks

        # first merge in variables from project_settings - but ignore __doc__ etc
        for setting in vars(project_settings).keys():
            if not setting.startswith('__'):
                setattr(self, setting, vars(project_settings)[setting])

        # what is the root of the project - one up from this directory
        if hasattr(self, 'local_vcs_root'):
            self.vcs_root_dir = self.local_vcs_root
        else:
            self.vcs_root_dir = path.abspath(path.join(self.local_deploy_dir, os.pardir))

    # TODO: put code for other apps in here
    # create db objects
    # update db
    # ...

    def deploy(self, environment=None):
        """Do all the required steps in order"""
        if environment:
            self.environment = environment
        else:
            self.environment = self.infer_environment()
            logging.debug("Inferred environment as %s" % self.environment)

        self.update_git_submodules()
        self.create_private_settings()
        self.link_local_settings(self.environment)
        self.update_db()

        if hasattr(self.localtasks_module, 'post_deploy'):
            self.localtasks_module.post_deploy(self.environment)

        logging.warning("*** Finished deploying %s for %s." %
                        (self.project_name, self.environment))

    def infer_environment(self):
        raise NotImplementedError()

    def create_private_settings(self):
        raise NotImplementedError()

    def link_local_settings(self):
        raise NotImplementedError()

    def update_git_submodules(self):
        """If this is a git project then check for submodules and update"""
        git_modules_file = path.join(self.vcs_root_dir, '.gitmodules')
        if path.exists(git_modules_file):
            logging.warning("### updating git submodules")
            if not self.quiet:
                git_submodule_cmd = 'git submodule update --init'
            else:
                git_submodule_cmd = 'git submodule --quiet update --init'
            check_call_wrapper(git_submodule_cmd, cwd=self.vcs_root_dir, shell=True)

    def clean_db(self):
        raise NotImplementedError()

    def update_db(self):
        raise NotImplementedError()

    def create_db_objects(self, **kwargs):
        """ not in tasks but used by other methods """
        pass

    def dump_db(self, dump_filename='db_dump.sql', for_rsync=False, database='default'):
        self.create_db_objects(database=database)
        self.db.dump_db(dump_filename, for_rsync)

    def restore_db(self, dump_filename='db_dump.sql', database='default'):
        self.create_db_objects(database=database)
        self.db.restore_db(dump_filename)

    def create_dbdump_cron_file(self, cron_file, dump_file_stub, database='default'):
        self.create_db_objects(database=database)
        self.db.create_dbdump_cron_file(cron_file, dump_file_stub)

    def setup_db_dumps(self, dump_dir, database='default'):
        self.create_db_objects(database=database)
        self.db.setup_db_dumps(dump_dir, self.project_name)

    def quick_test(self, *extra_args):
        """Run the django tests with local_settings.py.dev_fasttests

        local_settings.py.dev_fasttests (should) use port 3307 so it will work
        with a mysqld running with a ramdisk, which should be a lot faster. The
        original environment will be reset afterwards.

        With no arguments it will run all the tests for you apps (as listed in
        project_settings.py), but you can also pass in multiple arguments to run
        the tests for just one app, or just a subset of tests. Examples include:

        ./tasks.py quick_test:myapp
        ./tasks.py quick_test:myapp.ModelTests,myapp.ViewTests.my_view_test
        """
        original_environment = self.infer_environment()

        try:
            self.link_local_settings('dev_fasttests')
            self.update_db()
            self.run_tests(*extra_args)
        finally:
            self.link_local_settings(original_environment)

    def run_tests(self):
        raise NotImplementedError('run_jenkins not implemented for this AppManager')

    def run_jenkins(self):
        raise NotImplementedError('run_jenkins not implemented for this AppManager')


class PythonAppManager(AppManager):

    def __init__(self, **kwargs):
        super(PythonAppManager, self).__init__(**kwargs)
        self.python_bin = self.get_python_bin()

    def get_python_bin(self):
        python26 = path.join('/', 'usr', 'bin', 'python2.6')
        python27 = path.join('/', 'usr', 'bin', 'python2.7')
        generic_python = path.join('/', 'usr', 'bin', 'python')
        paths_to_try = (python26, python27, generic_python, sys.executable)
        chosen_python = None
        for python in paths_to_try:
            if path.exists(python):
                chosen_python = python
        if chosen_python is None:
            raise Exception("Failed to find a valid Python executable " +
                    "in any of these locations: %s" % paths_to_try)
        logging.debug("Using Python from %s" % chosen_python)
        return chosen_python


class DjangoManager(PythonAppManager):

    tasks = AppManager.tasks + (
        # definite django only things
        'collect_static',
        'create_uploads_dir',
        'patch_south',
    )

    def __init__(self, **kwargs):
        super(DjangoManager, self).__init__(**kwargs)
        # the django settings will be in the django_dir for old school projects
        # otherwise it should be defined in the project_settings
        if not hasattr(self, 'relative_django_settings_dir'):
            self.relative_django_settings_dir = self.relative_django_dir
        if not hasattr(self, 'relative_ve_dir'):
            self.relative_ve_dir = path.join(self.relative_django_dir, '.ve')

        # now create the absolute paths of everything else
        if not hasattr(self, 'django_dir'):
            self.django_dir = path.join(self.vcs_root_dir, self.relative_django_dir)
        if not hasattr(self, 'django_settings_dir'):
            self.django_settings_dir = path.join(self.vcs_root_dir, self.relative_django_settings_dir)
        if not hasattr(self, 've_dir'):
            self.ve_dir = path.join(self.vcs_root_dir, self.relative_ve_dir)
        if not hasattr(self, 'manage_py'):
            self.manage_py = path.join(self.django_dir, 'manage.py')
        if not hasattr(self, 'manage_py_settings'):
            self.manage_py_settings = None

    def manage_py(self, args, cwd=None):
        # for manage.py, always use the system python
        # otherwise the update_ve will fail badly, as it deletes
        # the virtualenv part way through the process ...
        manage_cmd = [self.python_bin, self.manage_py]
        if self.quiet:
            manage_cmd.append('--verbosity=0')
        if isinstance(args, str):
            manage_cmd.append(args)
        else:
            manage_cmd.extend(args)

        # Allow manual specification of settings file
        if self.manage_py_settings is not None:
            manage_cmd.append('--settings=%s' % self.manage_py_settings)

        if cwd is None:
            cwd = self.django_dir

        logging.debug('Executing manage command: %s' % ' '.join(manage_cmd))
        output_lines = []
        try:
            # TODO: make compatible with python 2.3
            popen = subprocess.Popen(manage_cmd, cwd=cwd, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT)
        except OSError, e:
            logging.error("Failed to execute command: %s: %s" % (manage_cmd, e))
            raise e
        for line in iter(popen.stdout.readline, ""):
            logging.debug(line)
            output_lines.append(line)
        returncode = popen.wait()
        if returncode != 0:
            error_msg = "Failed to execute command: %s: returned %s\n%s" % \
                (manage_cmd, returncode, "\n".join(output_lines))
            raise ShellCommandError(error_msg, popen.returncode)
        return output_lines

    def infer_environment(self):
        local_settings = path.join(self.django_settings_dir, 'local_settings.py')
        if path.exists(local_settings):
            self.environment = os.readlink(local_settings).split('.')[-1]
            return self.environment
        else:
            raise TasksError('no environment set, or pre-existing')

    def get_db_details_from_local_settings(self, local_settings, database='default'):
        """ Args:
                local_settings (module): the module with the database settings

                database (string): The database key to use in the 'DATABASES'
                    configuration. Override from the default to use a different
                    database.
        """
        default_host = '127.0.0.1'
        db_details = {'noinput': self.noinput}
        # there are two ways of having the settings:
        # either as DATABASE_NAME = 'x', DATABASE_USER ...
        # or as DATABASES = { 'default': { 'NAME': 'xyz' ... } }
        try:
            db = local_settings.DATABASES[database]
            db_details['engine'] = db['ENGINE']
            db_details['name'] = db['NAME']
            test_name = getattr(local_settings, 'TEST_NAME', None)
            if db_details['engine'].endswith('sqlite3'):
                db_details['root_dir'] = self.django_dir
            else:
                db_details['user'] = db['USER']
                db_details['password'] = db['PASSWORD']
                db_details['port'] = db.get('PORT', None)
                db_details['host'] = db.get('HOST', default_host)

        except (AttributeError, KeyError):
            try:
                db_details['engine'] = local_settings.DATABASE_ENGINE
                db_details['name'] = local_settings.DATABASE_NAME
                test_name = getattr(local_settings, 'DATABASE_TEST_NAME', None)
                if db_details['engine'].endswith('sqlite3'):
                    db_details['root_dir'] = self.django_dir
                else:
                    db_details['user'] = local_settings.DATABASE_USER
                    db_details['password'] = local_settings.DATABASE_PASSWORD
                    db_details['port'] = getattr(local_settings, 'DATABASE_PORT', None)
                    db_details['host'] = getattr(local_settings, 'DATABASE_HOST', default_host)
            except AttributeError:
                # we've failed to find the details we need - give up
                raise InvalidProjectError("Failed to find database settings")
        # sort out the engine part - discard everything before the last .
        db_details['engine'] = db_details['engine'].split('.')[-1]
        if self.environment == 'dev_fasttests':
            db_details['grant_enabled'] = False
        return db_details, test_name

    def create_db_objects(self, database='default'):
        """ Args:
                database (string): The database key to use in the 'DATABASES'
                    configuration. Override from the default to use a different
                    database.
        """
        if self.db is not None:
            return
        # work out what the environment is if necessary
        if self.environment is None:
            self.infer_environment()

        # import local_settings from the django dir. Here we are adding the
        # django project directory to the path. Note that self.django_dir may
        # be more than one directory (eg. 'django/project') which is why we
        # use django_module
        sys.path.append(self.django_settings_dir)
        import local_settings
        db_details, test_name = self.get_db_details_from_local_settings(local_settings, database)

        # and create the objects that hold the db details
        self.db = get_db_manager(**db_details)

        # and the test db object
        if test_name is None:
            db_details['name'] = 'test_' + db_details['name']
        else:
            db_details['name'] = test_name
        self.test_db = get_db_manager(**db_details)

    def clean_db(self, database='default'):
        """Delete the database for a clean start"""
        self.create_db_objects(database=database)
        self.db.drop_db()
        self.test_db.drop_db()

    def get_cache_table(self):
        # import settings from the django dir
        sys.path.append(self.django_settings_dir)
        import settings
        if not hasattr(settings, 'CACHES'):
            return None
        if not settings.CACHES['default']['BACKEND'].endswith('DatabaseCache'):
            return None
        return settings.CACHES['default']['LOCATION']

    def update_db(self, syncdb=True, drop_test_db=True, force_use_migrations=True, database='default'):
        """ create the database, and do syncdb and migrations
        Note that if syncdb is true, then migrations will always be done if one of
        the Django apps has a directory called 'migrations/'
        Args:
            syncdb (bool): whether to run syncdb (aswell as creating database)
            drop_test_db (bool): whether to drop the test database after creation
            force_use_migrations (bool): always True now
            database (string): The database value passed to _get_django_db_settings.
        """
        logging.warning("### Creating and updating the databases")

        self.create_db_objects(database=database)

        # then see if the database exists
        self.db.ensure_user_and_db_exist()
        if not drop_test_db:
            self.test_db.create_db_if_not_exists()
        self.test_db.grant_all_privileges_for_database()

        if syncdb:
            # if we are using the database cache we need to create the table
            # and we need to do it before syncdb
            cache_table = self.get_cache_table()
            if cache_table and not self.db.test_db_table_exists(cache_table):
                self.manage_py(['createcachetable', cache_table])
            self.manage_py(['syncdb', '--noinput', '--no-initial-data'])
            # always call migrate - shouldn't fail (I think)
            # first without initial data:
            self.manage_py(['migrate', '--noinput', '--no-initial-data'])
            # then with initial data, AFTER tables have been created:
            self.manage_py(['syncdb', '--noinput'])
            self.manage_py(['migrate', '--noinput'])

    def check_settings_imports_local_settings(self):
        # check that settings imports local_settings, as it always should,
        # and if we forget to add that to our project, it could cause mysterious
        # failures
        settings_file_path = path.join(self.django_settings_dir, 'settings.py')
        if not(path.isfile(settings_file_path)):
            raise InvalidProjectError("Fatal error: settings.py doesn't seem to exist")
        with open(settings_file_path) as settings_file:
            matching_lines = [line for line in settings_file if 'local_settings' in line]
        if not matching_lines:
            raise InvalidProjectError("Fatal error: settings.py doesn't seem to import "
                "local_settings.*: %s" % settings_file_path)

    def link_local_settings(self, environment):
        """ link local_settings.py.environment as local_settings.py """
        logging.warning("### creating link to local_settings.py")

        self.check_settings_imports_local_settings()
        source = path.join(self.django_settings_dir, 'local_settings.py.%s' %
                           environment)
        target = path.join(self.django_settings_dir, 'local_settings.py')
        # die if the correct local settings does not exist
        if not path.exists(source):
            raise InvalidProjectError("Could not find file to link to: %s" % source)
        # remove any old versions, plus the pyc copy
        for old_file in (target, target + 'c'):
            if path.exists(old_file):
                os.remove(old_file)

        if os.name == 'posix':
            os.symlink('local_settings.py.%s' % environment, target)
        elif os.name == 'nt':
            try:
                import win32file
            except ImportError:
                raise Exception(
                    "It looks like the PyWin32 extensions are not installed")
            try:
                win32file.CreateSymbolicLink(target, source)
            except NotImplementedError:
                win32file.CreateHardLink(target, source)
        else:
            import shutil
            shutil.copy2(source, target)
        self.environment = environment

    def create_private_settings(self):
        """ create private settings file
        - contains generated DB password and secret key"""
        private_settings_file = path.join(self.django_settings_dir,
                                          'private_settings.py')
        if not path.exists(private_settings_file):
            logging.warning("### creating private_settings.py")
            # don't use "with" for compatibility with python 2.3 on whov2hinari
            f = open(private_settings_file, 'w')
            try:
                secret_key = "".join([random.choice("abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)") for i in range(50)])
                db_password = "".join([random.choice("abcdefghijklmnopqrstuvwxyz0123456789") for i in range(12)])

                f.write("SECRET_KEY = '%s'\n" % secret_key)
                f.write("DB_PASSWORD = '%s'\n" % db_password)
            finally:
                f.close()
            # need to think about how to ensure this is owned by apache
            # despite having been created by root
            #os.chmod(private_settings_file, 0400)

    def collect_static(self):
        return self.manage_py(["collectstatic", "--noinput"])

    def install_django_jenkins(self):
        """ ensure that pip has installed the django-jenkins thing """
        logging.warning("### Installing Jenkins packages")
        pip_bin = path.join(self.ve_dir, 'bin', 'pip')
        if hasattr(self, 'django_jenkins_version'):
            packages = ['django-jenkins==%s' % self.django_jenkins_version]
        else:
            packages = ['django-jenkins']
        packages += ['pylint', 'coverage']
        for package in packages:
            check_call_wrapper([pip_bin, 'install', package])

    def manage_py_jenkins(self):
        """ run the jenkins command """
        args = ['jenkins', ]
        args += ['--pylint-rcfile', path.join(self.vcs_root_dir, 'jenkins', 'pylint.rc')]
        coveragerc_filepath = path.join(self.vcs_root_dir, 'jenkins', 'coverage.rc')
        if path.exists(coveragerc_filepath):
            args += ['--coverage-rcfile', coveragerc_filepath]
        args += self.django_apps
        logging.warning("### Running django-jenkins, with args; %s" % args)
        self.manage_py(args, cwd=self.vcs_root_dir)

    def create_test_db(self, drop_after_create=True, database='default'):
        self.create_db_objects(database=database)
        self.test_db.create_db_if_not_exists(drop_after_create=drop_after_create)

    def run_tests(self, *extra_args):
        """Run the django tests.

        With no arguments it will run all the tests for you apps (as listed in
        project_settings.py), but you can also pass in multiple arguments to run
        the tests for just one app, or just a subset of tests. Examples include:

        ./tasks.py run_tests:myapp
        ./tasks.py run_tests:myapp.ModelTests,myapp.ViewTests.my_view_test
        """
        logging.warning("### Running tests")

        args = ['test', '--noinput', '-v0']
        if extra_args:
            args += extra_args
        else:
            # default to running all tests
            args += self.django_apps

        self.manage_py(args)

    def run_jenkins(self):
        """ make sure the local settings is correct and the database exists """
        self.verbose = True
        # TODO: also set logging levels
        # don't want any stray pyc files causing trouble
        rm_all_pyc(self.vcs_root_dir)
        self.install_django_jenkins()
        self.create_private_settings()
        self.link_local_settings('jenkins')
        self.clean_db()
        self.update_db()
        self.manage_py_jenkins()

    def patch_south(self):
        """ patch south to fix pydev errors """
        python = 'python2.6'
        if '2.7' in self.python_bin:
            python = 'python2.7'
        south_db_init = path.join(self.ve_dir,
                    'lib/%s/site-packages/south/db/__init__.py' % python)
        patch_file = path.join(
            path.dirname(__file__), os.pardir, 'patch', 'south.patch')
        # check if patch already applied - patch will fail if it is
        patch_applied = call_wrapper(['grep', '-q', 'pydev', south_db_init])
        if patch_applied != 0:
            cmd = ['patch', '-N', '-p0', south_db_init, patch_file]
            check_call_wrapper(cmd)


class WordpressManager(AppManager):
    pass


class DjangoWordpressManager(object):

    def __init__(self, **kwargs):
        self.django = DjangoManager(**kwargs)
        self.wordpress = WordpressManager(**kwargs)

    def infer_environment(self):
        self.django.infer_environment()
        self.wordpress.infer_environment()

    def create_private_settings(self):
        self.django.create_private_settings()
        self.wordpress.create_private_settings()

    def link_local_settings(self):
        self.django.link_local_settings()
        self.wordpress.link_local_settings()

    def update_git_submodules(self):
        self.django.update_git_submodules()
        self.wordpress.update_git_submodules()

    def update_db(self):
        self.django.update_db()
        self.wordpress.update_db()


def get_application_manager_class(project_type):
    """ This is the only function exported by tasklib - then we
    just instantiate the returned class and carry on from there.
    """
    project_type_to_manager = {
        'django': DjangoManager,
        'wordpress': WordpressManager,
    }
    if project_type in project_type_to_manager:
        return project_type_to_manager[project_type]
    else:
        raise InvalidProjectError('project_type %s not supported' % project_type)
