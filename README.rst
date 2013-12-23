Trommons importer
=================

`Pootle <http://pootle.translatehouse.org/>`_ is an online translation and
localization tool.  It works to lower the barrier of entry, providing tools to
enable teams to work towards higher quality while welcoming newcomers.

`Trommons <http://trommons.org/>`_ is an online platform for empowering
localization.

**Trommons importer** is a set of scripts that binds together both platforms in
order to allow use Pootle as the online translation tool for the Trommons
platform.


Install and use
---------------

In order to use this it is necessary to:

- Have Slumber installed: ``pip install slumber``
- Have inotifyx installed: ``pip install inotifyx``
- Alter the ``trommons_script.py`` file to set the appropriate values in the
  constants,
- Have a functional Pootle install with the API enabled,
- Have a user with enough permissions to create stuff using the API,
- Have a site defined,
- Run this from inside the same virtualenv where Pootle is being run.
- Run using the directory monitor script (``trommons_checker.py``),


It is also recommended to perform some further tweaks on the Pootle server:

- Change global permissions for 'nobody' and 'default' so they don't have any
  permission to alter any project or translation project. That way every user
  would see only its projects, avoiding potential problems.


Copying
-------

Trommons importer is released under the General Public License, version 2 or
later. See the file LICENSE for details.
