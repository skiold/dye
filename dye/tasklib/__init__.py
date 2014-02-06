# import all functions that don't start with _
from .tasklib import get_application_manager_class

# the global dictionary and a funcation to populate it
from .environment import env, setup_paths
