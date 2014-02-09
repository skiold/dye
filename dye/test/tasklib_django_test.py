import os
from os import path
import sys
import shutil
import unittest

dye_dir = path.join(path.dirname(__file__), os.pardir)
sys.path.append(dye_dir)
from tasklib.managers import DjangoManager
from tasklib.exceptions import InvalidProjectError

example_dir = path.join(dye_dir, os.pardir, '{{cookiecutter.project_name}}', 'deploy')
sys.path.append(example_dir)
import project_settings


class ManagerTestMixin(object):

    def setup_project_settings(self, testdir):
        project_settings.project_name = 'testproj'
        project_settings.django_apps = ['testapp']
        project_settings.project_type = 'django'
        project_settings.use_virtualenv = False
        project_settings.relative_django_dir = path.join(
            "django", project_settings.project_name)
        project_settings.local_deploy_dir = path.dirname(__file__)
        project_settings.local_vcs_root = testdir
        project_settings.django_dir = path.join(project_settings.local_vcs_root,
            project_settings.relative_django_dir)
        project_settings.relative_django_settings_dir = path.join(
            project_settings.relative_django_dir, project_settings.project_name)
        project_settings.relative_ve_dir = path.join(
            project_settings.relative_django_dir, '.ve')

    def create_manager(self):
        self.manager = DjangoManager(project_settings=project_settings, quiet=True, noinput=True)
        #self.manager.python_bin = path.join(self.manager.ve_dir, 'bin', 'python')

    def create_django_dirs(self):
        if not path.exists(self.manager.django_dir):
            os.makedirs(self.manager.django_dir)
            os.makedirs(self.manager.django_settings_dir)

    def remove_django_dirs(self):
        shutil.rmtree(self.testdir)


class TestLinkLocalSettings(ManagerTestMixin, unittest.TestCase):

    def setUp(self):
        self.testdir = path.join(path.dirname(__file__), 'testdir')
        self.setup_project_settings(self.testdir)
        self.create_manager()
        self.create_django_dirs()

    def tearDown(self):
        self.remove_django_dirs()

    def create_empty_settings_py(self):
        settings_path = path.join(self.manager.django_settings_dir, 'settings.py')
        open(settings_path, 'a').close()

    def create_settings_py(self):
        settings_path = path.join(self.manager.django_settings_dir, 'settings.py')
        with open(settings_path, 'w') as f:
            f.write('import local_settings')

    def create_local_settings_py_dev(self, local_settings_path):
        local_settings_dev_path = local_settings_path + '.dev'
        # create local_settings.py.dev, run link_local_settings, confirm it exists
        with open(local_settings_dev_path, 'w') as lsdev:
            lsdev.write('# python file')
        return local_settings_dev_path

    def test_link_local_settings_raises_error_if_settings_py_not_present(self):
        # We don't create settings.py, just call link_local_settings()
        # and see if it dies with the correct error
        local_settings_path = path.join(self.manager.django_settings_dir, 'local_settings.py')
        self.create_local_settings_py_dev(local_settings_path)
        with self.assertRaises(InvalidProjectError):
            self.manager.link_local_settings('dev')

    def test_link_local_settings_raises_error_if_settings_py_does_not_import_local_settings(self):
        # We don't create settings.py, just call link_local_settings()
        # and see if it dies with the correct error
        local_settings_path = path.join(self.manager.django_settings_dir, 'local_settings.py')
        self.create_local_settings_py_dev(local_settings_path)
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
        local_settings_path = path.join(self.manager.django_settings_dir, 'local_settings.py')
        self.create_local_settings_py_dev(local_settings_path)

        self.manager.link_local_settings('dev')

        self.assertTrue(path.islink(local_settings_path))
        # assert the link goes to the correct file
        linkto = os.readlink(local_settings_path)
        self.assertEqual(linkto, 'local_settings.py.dev')

    def test_link_local_settings_replaces_old_local_settings(self):
        self.create_settings_py()
        local_settings_path = path.join(self.manager.django_settings_dir, 'local_settings.py')
        self.create_local_settings_py_dev(local_settings_path)
        open(local_settings_path, 'a').close()
        self.assertFalse(path.islink(local_settings_path))

        self.manager.link_local_settings('dev')

        self.assertTrue(path.islink(local_settings_path))
        # assert the link goes to the correct file
        linkto = os.readlink(local_settings_path)
        self.assertEqual(linkto, 'local_settings.py.dev')

    def test_link_local_settings_removes_local_settings_pyc(self):
        self.create_settings_py()
        local_settings_path = path.join(self.manager.django_settings_dir, 'local_settings.py')
        local_settings_pyc_path = local_settings_path + 'c'
        self.create_local_settings_py_dev(local_settings_path)
        open(local_settings_pyc_path, 'a').close()

        self.manager.link_local_settings('dev')

        self.assertFalse(path.exists(local_settings_pyc_path))

    # find migrations

    # create rollback version

    # create dir if not exists

    # get django db settings

    # clean db

    # clean ve

    # update ve

    # create private settings

    # get cache table

    # update db

    # update git submodules

    # manage py jenkins

    # run jenkins

    # rm all pyc

    # infer evironment

    # deploy

    # patch south


if __name__ == '__main__':
    unittest.main()
