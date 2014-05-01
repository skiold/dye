import os
from os import path
import sys
import shutil
import unittest

dye_dir = path.join(path.dirname(__file__), os.pardir)
sys.path.append(dye_dir)
from tasklib.managers import AppManager, PythonAppManager, DjangoManager
from tasklib.exceptions import TasksError, InvalidProjectError

example_dir = path.join(dye_dir, os.pardir, '{{cookiecutter.project_name}}', 'deploy')
sys.path.append(example_dir)
import project_settings


class ManagerTestMixin(object):

    def setup_project_settings(self, testdir, set_local_vcs_root=True):
        project_settings.project_name = 'testproj'
        project_settings.django_apps = ['testapp']
        project_settings.project_type = 'django'
        project_settings.use_virtualenv = False
        project_settings.relative_django_dir = path.join(
            "django", project_settings.project_name)
        project_settings.local_deploy_dir = path.dirname(__file__)
        if set_local_vcs_root:
            project_settings.local_vcs_root = testdir
        else:
            project_settings.local_vcs_root = None
        project_settings.django_dir = path.join(project_settings.local_vcs_root,
            project_settings.relative_django_dir)
        project_settings.relative_django_settings_dir = path.join(
            project_settings.relative_django_dir, project_settings.project_name)
        project_settings.relative_ve_dir = path.join(
            project_settings.relative_django_dir, '.ve')

    def create_manager(self):
        self.manager = DjangoManager(project_settings=project_settings, quiet=True, noinput=True)

    def create_django_dirs(self):
        if not path.exists(self.manager.django_dir):
            os.makedirs(self.manager.django_dir)
            os.makedirs(self.manager.django_settings_dir)

    def remove_django_dirs(self):
        shutil.rmtree(self.testdir)

    def create_local_settings_py_dev(self, local_settings_path=None, env='dev'):
        if local_settings_path is None:
            local_settings_path = path.join(self.manager.django_settings_dir, 'local_settings.py')
        local_settings_dev_path = local_settings_path + '.' + env
        # create local_settings.py.dev, run link_local_settings, confirm it exists
        with open(local_settings_dev_path, 'w') as lsdev:
            lsdev.write('# python file')
        return local_settings_dev_path

    def create_empty_settings_py(self):
        settings_path = path.join(self.manager.django_settings_dir, 'settings.py')
        open(settings_path, 'a').close()

    def create_settings_py(self):
        settings_path = path.join(self.manager.django_settings_dir, 'settings.py')
        with open(settings_path, 'w') as f:
            f.write('import local_settings')

    def sys_path_remove(self, sys_path):
        if sys_path in sys.path:
            sys.path.remove(sys_path)


class TestAppManagerInit(ManagerTestMixin, unittest.TestCase):

    def setUp(self):
        self.testdir = path.join(path.dirname(__file__), 'testdir')
        self.setup_project_settings(self.testdir)
        self.manager = AppManager(project_settings=project_settings, quiet=True, noinput=True)

    def test_project_settings_attributes_become_variables_on_manager(self):
        self.assertEqual(project_settings.project_name, self.manager.project_name)
        self.assertEqual(project_settings.project_type, self.manager.project_type)
        self.assertEqual(project_settings.use_virtualenv, self.manager.use_virtualenv)

    def test_private_project_settings_attributes_do_not_become_variables_on_manager(self):
        self.assertFalse(hasattr(self.manager, '__name__'))
        self.assertFalse(hasattr(self.manager, '__file__'))

    def test_vcs_root_dir_is_set_if_local_vcs_root_present_in_project_settings(self):
        self.assertEqual(project_settings.local_vcs_root, self.manager.vcs_root_dir)

    def test_vcs_root_dir_uses_parent_of_deploy_dir_if_local_vcs_root_not_present_in_project_settings(self):
        del project_settings.local_vcs_root
        deploy_parent_dir = path.abspath(path.join(project_settings.local_deploy_dir, '..'))
        self.manager = AppManager(project_settings=project_settings, quiet=True, noinput=True)
        self.assertEqual(deploy_parent_dir, self.manager.vcs_root_dir)


class TestPythonAppManager(ManagerTestMixin, unittest.TestCase):

    def setUp(self):
        self.testdir = path.join(path.dirname(__file__), 'testdir')
        self.setup_project_settings(self.testdir)
        self.manager = PythonAppManager(project_settings=project_settings, quiet=True, noinput=True)

    # TODO: how to check get_python_bin() checking?  Mock the path.exist() calls?


class TestDjangoAppManagerInit(ManagerTestMixin, unittest.TestCase):

    required_vars = [
        'relative_django_settings_dir', 'relative_ve_dir', 'django_dir',
        'django_settings_dir', 've_dir', 'manage_py', 'manage_py_settings',
    ]

    def setUp(self):
        self.testdir = path.join(path.dirname(__file__), 'testdir')
        self.setup_project_settings(self.testdir)
        for var in self.required_vars:
            if hasattr(project_settings, var):
                delattr(project_settings, var)

    def test_required_variables_are_set_when_not_present_in_project_settings(self):
        self.manager = DjangoManager(project_settings=project_settings, quiet=True, noinput=True)
        for var in self.required_vars:
            self.assertTrue(hasattr(self.manager, var))

    def test_required_variables_can_be_overridden_by_project_settings(self):
        for i, var in enumerate(self.required_vars):
            value = 'silly value %d' % i
            setattr(project_settings, var, value)
            try:
                self.manager = DjangoManager(project_settings=project_settings, quiet=True, noinput=True)
                self.assertEqual(value, getattr(self.manager, var))
            finally:
                delattr(project_settings, var)


class TestInferEnvironment(ManagerTestMixin, unittest.TestCase):

    def setUp(self):
        self.testdir = path.join(path.dirname(__file__), 'testdir')
        self.setup_project_settings(self.testdir)
        self.create_manager()
        self.create_django_dirs()

    def tearDown(self):
        self.remove_django_dirs()

    def test_infer_environment_raises_error_when_local_settings_not_linked(self):
        self.assertRaises(TasksError, self.manager.infer_environment)

    def test_infer_environment_reports_environment_from_link(self):
        self.create_settings_py()
        self.create_local_settings_py_dev()
        self.create_local_settings_py_dev(env='staging')

        self.manager.link_local_settings('dev')
        self.assertEqual('dev', self.manager.infer_environment())

        self.manager.link_local_settings('staging')
        self.assertEqual('staging', self.manager.infer_environment())


class TestLinkLocalSettings(ManagerTestMixin, unittest.TestCase):

    def setUp(self):
        self.testdir = path.join(path.dirname(__file__), 'testdir')
        self.setup_project_settings(self.testdir)
        self.create_manager()
        self.create_django_dirs()
        self.local_settings_path = path.join(self.manager.django_settings_dir, 'local_settings.py')

    def tearDown(self):
        self.remove_django_dirs()

    def test_link_local_settings_raises_error_if_settings_py_not_present(self):
        # We don't create settings.py, just call link_local_settings()
        # and see if it dies with the correct error
        self.create_local_settings_py_dev()
        with self.assertRaises(InvalidProjectError):
            self.manager.link_local_settings('dev')

    def test_link_local_settings_raises_error_if_settings_py_does_not_import_local_settings(self):
        # We don't create settings.py, just call link_local_settings()
        # and see if it dies with the correct error
        self.create_local_settings_py_dev()
        self.create_empty_settings_py()
        with self.assertRaises(InvalidProjectError):
            self.manager.link_local_settings('dev')

    def test_link_local_settings_raises_error_if_local_settings_py_dev_not_present(self):
        # We don't create settings.py, just call link_local_settings()
        # and see if it dies with the correct error
        self.create_settings_py()
        with self.assertRaises(InvalidProjectError):
            self.manager.link_local_settings('dev')

    def test_link_local_settings_creates_correct_link(self):
        self.create_settings_py()
        self.create_local_settings_py_dev(self.local_settings_path)

        self.manager.link_local_settings('dev')

        self.assertTrue(path.islink(self.local_settings_path))
        # assert the link goes to the correct file
        linkto = os.readlink(self.local_settings_path)
        self.assertEqual(linkto, 'local_settings.py.dev')

    def test_link_local_settings_replaces_old_local_settings(self):
        self.create_settings_py()
        self.create_local_settings_py_dev(self.local_settings_path)
        open(self.local_settings_path, 'a').close()
        self.assertFalse(path.islink(self.local_settings_path))

        self.manager.link_local_settings('dev')

        self.assertTrue(path.islink(self.local_settings_path))
        # assert the link goes to the correct file
        linkto = os.readlink(self.local_settings_path)
        self.assertEqual(linkto, 'local_settings.py.dev')

    def test_link_local_settings_removes_local_settings_pyc(self):
        self.create_settings_py()
        local_settings_pyc_path = self.local_settings_path + 'c'
        self.create_local_settings_py_dev(self.local_settings_path)
        open(local_settings_pyc_path, 'a').close()

        self.manager.link_local_settings('dev')

        self.assertFalse(path.exists(local_settings_pyc_path))


class TestGetCacheTable(ManagerTestMixin, unittest.TestCase):

    def setUp(self):
        self.create_manager()
        self.settings_base = path.join(path.dirname(__file__), 'data', 'cachedir')

    def test_get_cache_table_returns_none_when_no_cache_at_all(self):
        self.manager.django_settings_dir = path.join(self.settings_base, 'nocache')
        try:
            self.assertIsNone(self.manager.get_cache_table())
        finally:
            self.sys_path_remove(self.manager.django_settings_dir)

    def test_get_cache_table_returns_none_when_cache_is_not_database(self):
        self.manager.django_settings_dir = path.join(self.settings_base, 'nondbcache')
        try:
            self.assertIsNone(self.manager.get_cache_table())
        finally:
            self.sys_path_remove(self.manager.django_settings_dir)

    def test_get_cache_table_returns_table_name_when_db_cache_in_use(self):
        self.manager.django_settings_dir = path.join(self.settings_base, 'dbcache')
        try:
            self.assertEqual('cachetable', self.manager.get_cache_table())
        finally:
            self.sys_path_remove(self.manager.django_settings_dir)

    # rm all pyc

    # find migrations

    # create private settings

    # create rollback version - only in fabric

    # get django db settings

    # clean db

    # clean ve

    # update ve

    # update db

    # update git submodules

    # manage py jenkins

    # run jenkins

    # deploy

    # patch south


if __name__ == '__main__':
    unittest.main()
