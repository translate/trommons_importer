#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# Copyright 2013 Zuza Software Foundation
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, see <http://www.gnu.org/licenses/>.

"""In order to use this script it is necessary to:

* Alter this script to set the appropriate values in the constants,
* Run it using the directory monitor script,
* Have a functional Pootle install with the API enabled,
* Have a user with enough permissions to create stuff using the API,
* Have a site defined,
* Run it inside the same virtualenv where Pootle is being run.
* Have Slumber installed: `pip install slumber`
* Have inotifyx installed: `pip install inotifyx`

Further tweaks to Pootle server:

* Change global permissions for 'nobody' and 'default' so they don't have any
  permission to alter any project or translation project. That way every user
  would see only its projects, avoiding potential problems.

"""

import json
import logging
import os
import shutil
import subprocess
from tempfile import mkdtemp

import slumber

# This must be run before importing Django.
os.environ['DJANGO_SETTINGS_MODULE'] = 'pootle.settings'

from django.conf import settings


# How long to wait for additional events after a function run is triggered.
#
# Moved to this file to have all the settings in this file instead of the
# directory monitor script.
DELAY_BEFORE_RUN = 0.1

#TODO maybe put the following two constants on Pootle settings.
# Directory where Trommons leaves stuff for Pootle.
#
# Moved to this file to have all the settings in this file instead of the
# directory monitor script.
POOTLE_DIR = "/home/your-user/pootle/"

# Directory where Pootle leaves stuff for Trommons.
TROMMONS_DIR = "/home/your-user/trommons/"


# This is necessary when calling management commands.
POOTLE_SETTINGS_FILE = ("/home/your-user/repos/pootle/pootle/settings/"
                        "90-dev-local.conf")

# Pootle API URL.
API_URL = "http://localhost:8000/api/v1/"

# Username and password for login into the Pootle API.
#
# Must be a user with rights enough to create stuff and assign permissions.
API_AUTH = ('api-user', 'api-user')


# Filename of the JSON file used to exchange data. Have it in one place in case
# we need to alter it.
JSON_FILENAME = "meta.json"


def run_stuff(changed_dir_path):
    """Run all the machinery for importing a project from Trommons task.
    
    This creates any object required, imports the translation file, and assigns
    the necessary permissions to the translator.
    """
    # It is necessary to set the POOTLE_SETTINGS environment variable before
    # calling the Pootle management commands.
    os.environ['POOTLE_SETTINGS'] = POOTLE_SETTINGS_FILE

    # Set the default logging level to INFO, which makes easier to check that
    # everything works as expected.
    logging.basicConfig(level=logging.INFO)

    try:
        # Initialize API client to use for all the queries to Pootle API.
        API_OBJ = slumber.API(API_URL, auth=API_AUTH)

        # Make sure the required files are in the directory.
        ensure_files(changed_dir_path, JSON_FILENAME)

        # Get the data from the JSON file.
        provided = parse_input_json(changed_dir_path, JSON_FILENAME)

        # Make sure that in the provided JSON there are all the data we need.
        validate_provided_data(provided)

        # Add a custom field for further use.
        provided['project_code'] = "task-%d" % provided['task_id']

        # Make sure the required languages exist.
        source_lang_api_uri = ensure_languages(API_OBJ, provided)

        # Get the URL for the project for Trommons to use. This requires
        # setting a proper Site in Pootle admin.
        proj_backlink = create_new_project(API_OBJ, provided,
                                           source_lang_api_uri)

        # Import the translation file for the project.
        import_project_file(changed_dir_path, provided)

        # Make sure the user exists, or create it if not.
        ensure_user(API_OBJ, provided['assignee_id'])

        # Assign the user the necessary permissions in the project.
        assign_user_to_project(provided['assignee_id'],
                               provided['project_code'])

        # Import finished, so notify Trommons.
        notify_trommons(provided['project_code'], proj_backlink, JSON_FILENAME,
                        TROMMONS_DIR)
    except:
        logging.exception("Something wrong happened. Aborting.")

###############################################################################

def ensure_files(changed_dir_path, json_filename):
    """Make sure the required files are in place.
    
    We need a "meta.json" file and a translation file in the directory.
    """
    if not os.path.exists(changed_dir_path):
        logging.error("Directory does not exist. Maybe it was deleted after "
                      "succesful import. Aborting.")
        raise Exception
    
    if not os.path.isdir(changed_dir_path):
        logging.error("Path is not a directory. Aborting.")
        raise Exception

    try:
        filenames = os.listdir(changed_dir_path)
    except OSError:
        logging.error("Some problem happened when trying to read the task "
                      "directory contents. Maybe it was deleted.")
        raise

    if json_filename not in filenames:
        logging.error("The '%s' file is not present. Aborting." %
                      json_filename)
        raise Exception
    elif len(filenames) > 2:
        logging.error("More than one translation file is provided. Aborting.")
        raise Exception
    elif len(filenames) < 2:
        logging.error("No translation file has been provided. Aborting.")
        raise Exception


def parse_input_json(base_dir, json_filename):
    """Parse the provided JSON file."""
    try:
        input_file = open(os.path.join(base_dir, json_filename), "r")
    except IOError:
        logging.error("Error while opening the '%s' file. Aborting." %
                      json_filename)
        raise

    provided = json.load(input_file)
    input_file.close()
    return provided


def validate_provided_data(provided):
    """Ensure that all the required data is provided using the right types."""
    required = {
        "title": unicode,
        "description": unicode,
        "source_code": unicode,
        "source_name": unicode,
        "target_code": unicode,
        "target_name": unicode,
        "assignee_id": unicode,
        "backlink": unicode,
        "translation_filename": unicode,
        "task_id": int,
    }

    if not set(required.keys()).issubset(set(provided.keys())):
        logging.error("Not all the required fields are present in the "
                      "provided JSON file.")
        raise Exception

    for key, key_type in required.items():
        if not isinstance(provided[key], key_type):
            logging.error("The type for the '%s' field in provided JSON file "
                          "doesn't have the right type." % key)
            raise Exception

    logging.info("The provided JSON file has all the required data.")


def get_language_api_uri(api, code):
    """Return the URI in the Pootle API for the given language code.

    If the language doesn't exist in Pootle then an empty string is returned.
    """
    # GET query to http://localhost:8000/api/v1/languages/?code__iexact=en_US
    # assuming that the provided code is "en_US".
    lang_data = api.languages.get(code__iexact=code)

    # lang_data['meta']['total_count'] holds the number of resources that match
    # the query.
    if lang_data['meta']['total_count'] == 1:
        return lang_data['objects'][0]['resource_uri']
    else:
        return ""


def ensure_languages(api, provided):
    """Make sure the necessary languages exist.

    If any of them doesn't exist, it is created using the Pootle API.

    The API URI for the source language is returned for creating the project.
    """
    source_lang_api_uri = get_language_api_uri(api, provided['source_code'])

    if source_lang_api_uri:
        logging.info("Language '%s' already exists." % provided['source_code'])
    else:
        logging.info("Language '%s' doesn't exist." % provided['source_code'])
        create_new_language(api, provided['source_code'],
                            provided['source_name'])

    if get_language_api_uri(api, provided['target_code']):
        logging.info("Language '%s' already exists." % provided['target_code'])
    else:
        logging.info("Language '%s' doesn't exist." % provided['target_code'])
        create_new_language(api, provided['target_code'],
                            provided['target_name'])

    return source_lang_api_uri


def create_new_language(api, code, fullname):
    """Create a new language in Pootle using the Pootle API."""
    language_data = {
        'code': code,
        'fullname': fullname,
        'translation_projects': [],
    }

    try:
        api.languages.post(language_data)
    except slumber.exceptions.HttpServerError:
        logging.error("Some problem occurred while trying to create a new "
                      "language using the Pootle API. Aborting.")
        raise

    logging.info("Succesfully created language '%s'." % code)


def create_new_project(api, provided, source_lang_api_uri):
    """Create a new language in Pootle using the Pootle API."""

    #TODO need to check why the description is not displayed properly in Pootle.
    # Maybe because this is a MarkupField and maybe it is not correctly mapped
    # when creating the API automatically. Maybe look at
    # http://django-tastypie.readthedocs.org/en/latest/fields.html
    description = ('%s<br/><br/><a href="%s">Task in Trommons<a/>.' %
                   (provided['description'].replace("\n\n", "<br/>"),
                    provided['backlink']))

    project_data = {
        'code': provided['project_code'],
        'fullname': provided['title'],
        'description': description,
        'source_language': source_lang_api_uri,
        'translation_projects': [],
    }

    try:
        # This depends on having
        # http://django-tastypie.readthedocs.org/en/latest/resources.html#always-return-data
        # enabled for the API to return the data for the new project.
        new_proj = api.projects.post(project_data)
    except slumber.exceptions.HttpServerError:
        logging.error("Some problem occurred while trying to create a new "
                      "project using the Pootle API. Aborting.")
        raise

    logging.info("Succesfully created project '%s'." %
                 provided['project_code'])
    return new_proj['backlink']


def import_project_file(base_dir, provided):
    """Import the translation file for the given project."""

    # It is not necessary to create the directory because when creating it
    # using the API it already creates the project directory here for us.
    project_dir = os.path.join(settings.PODIRECTORY, provided['project_code'])

    # Create the target language directory.
    language_dir = os.path.join(project_dir, provided['target_code'])
    try:
        os.mkdir(language_dir)
    except OSError:
        logging.error("The language directory in PODIRECTORY already exists.")
        raise
    logging.info("Succesfully created directory '%s'" % language_dir)

    # Move the translation file to the target language directory.
    shutil.move(os.path.join(base_dir, provided['translation_filename']),
                os.path.join(language_dir, provided['translation_filename']))
    logging.info("Succesfully moved translation file to '%s'" % language_dir)

    # Now run the management command to actually import the translation file.
    cmd_args = [
        "pootle",
        "update_translation_projects",
        "--project",
        provided['project_code'],
    ]
    subprocess.call(cmd_args)
    logging.info("Sucessfully imported the translation file.")

    # Remove the directory provided by Trommons (including all the files and
    # subdirectories within it).
    shutil.rmtree(base_dir)
    logging.info("Sucessfully removed directory provided by Trommons.")


def create_new_user(api, username):
    """Create a new user in Pootle using the Pootle API."""
    user_data = {
        'username': username,
        'email': username,
    }

    try:
        api.users.post(user_data)
    except slumber.exceptions.HttpServerError:
        logging.exception("Some problem occurred while trying to create a new "
                          "user using the Pootle API. Aborting.")
        raise

    logging.info("Succesfully created user '%s'." % username)


def ensure_user(api, username):
    """Make sure the necessary user exists.

    If it doesn't exist, it is created using the Pootle API.
    """
    # GET query to http://localhost:8000/api/v1/users/?username__exact=sauron
    # assuming that the provided username is "sauron".
    user_data = api.users.get(username__exact=username)

    # lang_data['meta']['total_count'] holds the number of resources that match
    # the query.
    user_exists = user_data['meta']['total_count'] == 1

    if user_exists:
        logging.info("User '%s' already exists." % username)
    else:
        logging.info("User '%s' doesn't exist." % username)
        create_new_user(api, username)


def assign_user_to_project(username, project):
    """Assign permissions to the user with assign_permissions."""
    cmd_args = [
        "pootle",
        "assign_permissions",
        "--project",
        project,
        "--user",
        username,
        "--permissions",
        "view,suggest,translate,overwrite,review,archive",
    ]
    subprocess.call(cmd_args)
    logging.info("Succesfully assigned permissions to the translator.")


def notify_trommons(task_dir_name, project_backlink, json_filename,
                    trommons_dir):
    """Write the 'meta.json' and translated file so Trommons can get it."""

    # Create a temporary directory.
    temp_dir = mkdtemp()

    # Create a directory named like the Pootle project (Trommons task) inside
    # the temporary directory.
    temp_proj_dir = os.path.join(temp_dir, task_dir_name)
    os.mkdir(temp_proj_dir)

    # Open the destination file inside that directory to write the JSON and
    # notify Trommons that the project has been succesfully added.
    temp_file_name = os.path.join(temp_proj_dir, json_filename)
    output_json_file = open(temp_file_name, "w")

    # Create a dictionary for output JSON file.
    response_data = {
        'created': True,
        'backlink': project_backlink,
        'completed': False,
    }

    # Dump the JSON to the file, using pretty printing.
    json.dump(response_data, output_json_file, indent=4,
              separators=(',', ': '))

    # Close the file to actually write the JSON.
    output_json_file.close()

    # Move the task directory to the final destination inside the Trommons
    # directory.
    shutil.move(temp_proj_dir, trommons_dir)

    # Remove the temporary directory since we are already done with it.
    shutil.rmtree(temp_dir)

    logging.info("Succesfully notified Trommons the success in importing.")
