# This script is to set up various things for our projects. It can be used by:
#
# * developers - setting up their own environment
# * jenkins - setting up the environment and running tests
# * fabric - it will call a copy on the remote server when deploying
#
# The tasks it will do (eventually) include:
#
# * creating, updating and deleting the virtualenv
# * creating, updating and deleting the database (sqlite or mysql)
# * setting up the local_settings stuff
# * running tests
"""This script is to set up various things for our projects. It can be used by:

* developers - setting up their own environment
* jenkins - setting up the environment and running tests
* fabric - it will call a copy on the remote server when deploying

"""

from .managers import DjangoManager, WordpressManager
from .exceptions import InvalidProjectError


def get_application_manager_class(project_type):
    project_type_to_manager = {
        'django': DjangoManager,
        'wordpress': WordpressManager,
    }
    if project_type in project_type_to_manager:
        return project_type_to_manager[project_type]
    else:
        raise InvalidProjectError('project_type %s not supported' % project_type)
