import os
from os import path

# put this here so it can be imported cleanly
env = {}


def _setup_paths(project_settings, localtasks):
    """Set up the paths used by other tasks"""
    # first merge in variables from project_settings - but ignore __doc__ etc
    user_settings = [x for x in vars(project_settings).keys() if not x.startswith('__')]
    for setting in user_settings:
        env.setdefault(setting, vars(project_settings)[setting])

    env.setdefault('localtasks', localtasks)
    # what is the root of the project - one up from this directory
    if 'local_vcs_root' in env:
        env['vcs_root_dir'] = env['local_vcs_root']
    else:
        env['vcs_root_dir'] = \
            path.abspath(path.join(env['deploy_dir'], os.pardir))
