#!/usr/bin/env python

"""File system path monitor that will run a function when files change on the
given path.
"""

import inotifyx
import fnmatch
import time
import os


class Reporter(object):
    """Responsible for displaying info on the terminal."""

    def __init__(self):
        """Creates a new reporter."""
        self.run_number = 0

    def __enter__(self):
        """Report starting."""

        return self

    def monitor_count(self, count):
        """Report number of paths monitored."""
        pass

    def begin_run(self, change_set):
        """Report the beginning of the run."""

        self.run_number += 1
        print('=' * 80)
        print('Run Number: %s' % self.run_number)
        print('Files     : %s\n' % '\n            '.join(change_set))

    def end_run(self, ignored_change_set):
        """Report the end of the run."""

        print
        if ignored_change_set:
            print 'Ignoring changed files : %s' % ' '.join(ignored_change_set)
            print
        print '-' * 80

    def __exit__(self, e_type, e_value, tb):
        """Print blank line so shell prompt on clean new line."""
        print


class ChangeMonitor(object):
    """Responsible for detecting files being changed."""

    def __init__(self, paths, white_list, black_list, delay):
        """Creates a new file change monitor."""

        # Events of interest.
        self.WATCH_EVENTS = inotifyx.IN_CREATE | inotifyx.IN_MODIFY | inotifyx.IN_MOVE# | inotifyx.IN_DELETE_SELF | inotifyx.IN_DELETE

        # Remember params.
        self.white_list = white_list
        self.black_list = black_list
        self.delay = delay

        # Init inotify.
        self.fd = inotifyx.init()

        # Watch specified paths.
        self.watches = {}
        self.watches.update((inotifyx.add_watch(self.fd, path, self.WATCH_EVENTS), path)
                            for path in paths)

        # Watch sub dirs of specified paths.  Ensure we modify dirs
        # variable in place so that os.walk only traverses white
        # listed dirs.
        for path in paths:
            for root, dirs, files in os.walk(path):
                dirs[:] = [dir for dir in dirs if self.is_white_listed(dir)]
                self.watches.update((inotifyx.add_watch(self.fd, os.path.join(root, dir), self.WATCH_EVENTS), os.path.join(root, dir))
                                    for dir in dirs)

    def monitor_count(self):
        """Return number of paths being monitored."""

        return len(self.watches)

    def __iter__(self):
        """Iterating a monitor returns the next set of changed files.

        When requesting the next item from a monitor it will block
        until file changes are detected and then return the set of
        changed files.
        """

        while True:
            # Block until events arrive.
            events = inotifyx.get_events(self.fd)

            # Collect any events that occur within the delay period.
            # This allows events that occur close to the trigger event
            # to be collected now rather than causing another run
            # immediately after this run.
            if self.delay:
                time.sleep(self.delay)
                events.extend(inotifyx.get_events(self.fd, 0))

            # Filter to events that are white listed.
            events = [event for event in events if self.is_white_listed(event.name)]

            if events:
                # Track watched dirs.
                for event in events:
                    if event.mask & inotifyx.IN_ISDIR and event.mask & inotifyx.IN_CREATE:
                        self.watches[inotifyx.add_watch(self.fd, os.path.join(self.watches.get(event.wd), event.name), self.WATCH_EVENTS)] = os.path.join(self.watches.get(event.wd), event.name)
                    elif event.mask & inotifyx.IN_DELETE_SELF:
                        self.watches.pop(event.wd, None)

                # Supply this set of changes to the caller.
                change_set = set(os.path.join(self.watches.get(event.wd, ''),
                                              event.name or '')
                                 for event in events)
                yield change_set

    def clear(self):
        """Clears and returns any changed files that are waiting in the
        queue."""

        events = inotifyx.get_events(self.fd, 0)
        change_set = set(os.path.join(self.watches.get(event.wd, ''),
                                      event.name or '')
                         for event in events if self.is_white_listed(event.name))
        return change_set

    def is_white_listed(self, name):
        """Return whether name is in or out."""

        # Events with empty name are in as we have a watch on that
        # path.
        if not name:
            return True

        # Names in white list are always considered in.
        for pattern in self.white_list:
            if fnmatch.fnmatch(name, pattern):
                return True

        # Names in black list are always considered out.
        for pattern in self.black_list:
            if fnmatch.fnmatch(name, pattern):
                return False

        # If not white or black listed then considered in.
        return True


class Runner(object):
    """Responsible for running a specified command upon file changes."""

    def __init__(self, reporter, change_monitor, ignore_events, no_initial_run,
                 function):
        """Creates a new command runner."""

        self.reporter = reporter
        self.change_monitor = change_monitor
        self.ignore_events = ignore_events
        self.no_initial_run = no_initial_run
        self.function = function

    def do_run(self, change_set):
        """Perform a command run."""

        self.reporter.begin_run(change_set)
        for change in change_set:
            self.function(change)
        ignored_change_set = self.change_monitor.clear() if self.ignore_events else set()
        self.reporter.end_run(ignored_change_set)

    def main_loop(self):
        """Waits for a set of changed files and then does a function run."""

        # Report number of paths being monitored.
        self.reporter.monitor_count(self.change_monitor.monitor_count())

        # Do initial function run.
        if not self.no_initial_run:
            self.do_run(set())

        # Monitor and run the specified function until keyboard interrupt.
        for change_set in self.change_monitor:
            self.do_run(change_set)


#def test_function(change):
#    """Simple tester, put our real function in here"""
#    print "Run: %s" % change


def main():
    """Setup and enter main loop."""

    from trommons_script import run_stuff, DELAY_BEFORE_RUN, POOTLE_DIR

    #: function to execute when files change
    function = run_stuff  #was test_function

    #: paths to monitor
    paths = [POOTLE_DIR]


    #: how long to wait for additional events after a function run is
    #: triggered
    delay = DELAY_BEFORE_RUN
    #: whether to ignore events that occur during the command run
    ignore_events = False
    #: add a file to the white list, ensure globs are quoted to avoid shell
    #: expansion
    white_list = ['task-*']
    #: add a file to the black list, ensure globs are quoted to avoid shell
    #: expansion
    black_list = ['*']
    #: don't perform an initial run of the command, instead start
    #: monitoring and wait for changes
    no_initial_run = True

    try:
        # Create the reporter that prints info to the terminal.
        with Reporter() as reporter:

            # Create the monitor that watches for file changes.
            change_monitor = ChangeMonitor(paths, white_list, black_list,
                                           delay)

            # Create the runner that invokes the function on file changes.
            runner = Runner(reporter, change_monitor, ignore_events,
                            no_initial_run, function)

            # Enter the main loop until we break out.
            runner.main_loop()

    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
