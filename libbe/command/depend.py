# Copyright (C) 2009 Gianluca Montecchi <gian@grys.it>
#                    W. Trevor King <wking@drexel.edu>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import copy
import os

import libbe
import libbe.bug
import libbe.command
import libbe.command.util
import libbe.util.tree

BLOCKS_TAG="BLOCKS:"
BLOCKED_BY_TAG="BLOCKED-BY:"

class BrokenLink (Exception):
    def __init__(self, blocked_bug, blocking_bug, blocks=True):
        if blocks == True:
            msg = "Missing link: %s blocks %s" \
                % (blocking_bug.uuid, blocked_bug.uuid)
        else:
            msg = "Missing link: %s blocked by %s" \
                % (blocked_bug.uuid, blocking_bug.uuid)
        Exception.__init__(self, msg)
        self.blocked_bug = blocked_bug
        self.blocking_bug = blocking_bug

class Depend (libbe.command.Command):
    """Add/remove bug dependencies

    >>> import sys
    >>> import libbe.bugdir
    >>> bd = libbe.bugdir.SimpleBugDir(memory=False)
    >>> cmd = Depend()
    >>> cmd._setup_io = lambda i_enc,o_enc : None
    >>> cmd.stdout = sys.stdout

    >>> ret = cmd.run(bd.storage, bd, {}, ['/a', '/b'])
    a blocked by:
    b
    >>> ret = cmd.run(bd.storage, bd, {}, ['/a'])
    a blocked by:
    b
    >>> ret = cmd.run(bd.storage, bd, {'show-status':True}, ['/a']) # doctest: +NORMALIZE_WHITESPACE
    a blocked by:
    b closed
    >>> ret = cmd.run(bd.storage, bd, {}, ['/b', '/a'])
    b blocked by:
    a
    b blocks:
    a
    >>> ret = cmd.run(bd.storage, bd, {'show-status':True}, ['/a']) # doctest: +NORMALIZE_WHITESPACE
    a blocked by:
    b closed
    a blocks:
    b closed
    >>> ret = cmd.run(bd.storage, bd, {'repair':True})
    >>> ret = cmd.run(bd.storage, bd, {'remove':True}, ['/b', '/a'])
    b blocks:
    a
    >>> ret = cmd.run(bd.storage, bd, {'remove':True}, ['/a', '/b'])
    >>> bd.cleanup()
    """
    name = 'depend'

    def __init__(self, *args, **kwargs):
        libbe.command.Command.__init__(self, *args, **kwargs)
        self.requires_bugdir = True
        self.options.extend([
                libbe.command.Option(name='remove', short_name='r',
                    help='Remove dependency (instead of adding it)'),
                libbe.command.Option(name='show-status', short_name='s',
                    help='Show status of blocking bugs'),
                libbe.command.Option(name='status',
                    help='Only show bugs matching the STATUS specifier',
                    arg=libbe.command.Argument(
                        name='status', metavar='STATUS', default=None,
                        completion_callback=libbe.command.util.complete_status)),
                libbe.command.Option(name='severity',
                    help='Only show bugs matching the SEVERITY specifier',
                    arg=libbe.command.Argument(
                        name='severity', metavar='SEVERITY', default=None,
                        completion_callback=libbe.command.util.complete_severity)),
                libbe.command.Option(name='tree-depth', short_name='t',
                    help='Print dependency tree rooted at BUG-ID with DEPTH levels of both blockers and blockees.  Set DEPTH <= 0 to disable the depth limit.',
                    arg=libbe.command.Argument(
                        name='tree-depth', metavar='INT', type='int',
                        completion_callback=libbe.command.util.complete_severity)),
                libbe.command.Option(name='repair',
                    help='Check for and repair one-way links'),
                ])
        self.args.extend([
                libbe.command.Argument(
                    name='bug-id', metavar='BUG-ID', default=None,
                    optional=True,
                    completion_callback=libbe.command.util.complete_bug_id),
                libbe.command.Argument(
                    name='blocking-bug-id', metavar='BUG-ID', default=None,
                    optional=True,
                    completion_callback=libbe.command.util.complete_bug_id),
                ])

    def _run(self, storage, bugdir, **params):
        if params['repair'] == True and params['bug-id'] != None:
            raise libbe.command.UsageError(
                'No arguments with --repair calls.')
        if params['repair'] == False and params['bug-id'] == None:
            raise libbe.command.UsageError(
                'Must specify either --repair or a BUG-ID')
        if params['tree-depth'] != None \
                and params['blocking-bug-id'] != None:
            raise libbe.command.UsageError(
                'Only one bug id used in tree mode.')
        if params['repair'] == True:
            good,fixed,broken = check_dependencies(bugdir, repair_broken_links=True)
            assert len(broken) == 0, broken
            if len(fixed) > 0:
                print >> self.stdout, 'Fixed the following links:'
                print >> self.stdout, \
                    '\n'.join(['%s |-- %s' % (blockee.uuid, blocker.uuid)
                               for blockee,blocker in fixed])
            return 0
        allowed_status_values = \
            libbe.command.util.select_values(
                params['status'], libbe.bug.status_values)
        allowed_severity_values = \
            libbe.command.util.select_values(
                params['severity'], libbe.bug.severity_values)

        bugA, dummy_comment = libbe.command.util.bug_comment_from_user_id(
            bugdir, params['bug-id'])

        if params['tree-depth'] != None:
            dtree = DependencyTree(bugdir, bugA, params['tree-depth'],
                                   allowed_status_values,
                                   allowed_severity_values)
            if len(dtree.blocked_by_tree()) > 0:
                print >> self.stdout, '%s blocked by:' % bugA.uuid
                for depth,node in dtree.blocked_by_tree().thread():
                    if depth == 0: continue
                    print >> self.stdout, \
                        '%s%s' % (' '*(depth),
                        node.bug.string(shortlist=True))
            if len(dtree.blocks_tree()) > 0:
                print >> self.stdout, '%s blocks:' % bugA.uuid
                for depth,node in dtree.blocks_tree().thread():
                    if depth == 0: continue
                    print >> self.stdout, \
                        '%s%s' % (' '*(depth),
                        node.bug.string(shortlist=True))
            return 0

        if params['blocking-bug-id'] != None:
            bugB,dummy_comment = libbe.command.util.bug_comment_from_user_id(
                bugdir, params['blocking-bug-id'])
            if params['remove'] == True:
                remove_block(bugA, bugB)
            else: # add the dependency
                add_block(bugA, bugB)

        blocked_by = get_blocked_by(bugdir, bugA)
        if len(blocked_by) > 0:
            print >> self.stdout, '%s blocked by:' % bugA.uuid
            if params['show-status'] == True:
                print >> self.stdout, \
                    '\n'.join(['%s\t%s' % (_bug.uuid, _bug.status)
                               for _bug in blocked_by])
            else:
                print >> self.stdout, \
                    '\n'.join([_bug.uuid for _bug in blocked_by])
        blocks = get_blocks(bugdir, bugA)
        if len(blocks) > 0:
            print >> self.stdout, '%s blocks:' % bugA.uuid
            if params['show-status'] == True:
                print >> self.stdout, \
                    '\n'.join(['%s\t%s' % (_bug.uuid, _bug.status)
                               for _bug in blocks])
            else:
                print >> self.stdout, \
                    '\n'.join([_bug.uuid for _bug in blocks])
        return 0

    def _long_help(self):
        return """
Set a dependency with the second bug (B) blocking the first bug (A).
If bug B is not specified, just print a list of bugs blocking (A).

To search for bugs blocked by a particular bug, try
  $ be list --extra-strings BLOCKED-BY:<your-bug-uuid>

The --status and --severity options allow you to either blacklist or
whitelist values, for example
  $ be list --status open,assigned
will only follow and print dependencies with open or assigned status.
You select blacklist mode by starting the list with a minus sign, for
example
  $ be list --severity -target
which will only follow and print dependencies with non-target severity.

If neither bug A nor B is specified, check for and repair the missing
side of any one-way links.

The "|--" symbol in the repair-mode output is inspired by the
"negative feedback" arrow common in biochemistry.  See, for example
  http://www.nature.com/nature/journal/v456/n7223/images/nature07513-f5.0.jpg
"""

# internal helper functions

def _generate_blocks_string(blocked_bug):
    return '%s%s' % (BLOCKS_TAG, blocked_bug.uuid)

def _generate_blocked_by_string(blocking_bug):
    return '%s%s' % (BLOCKED_BY_TAG, blocking_bug.uuid)

def _parse_blocks_string(string):
    assert string.startswith(BLOCKS_TAG)
    return string[len(BLOCKS_TAG):]

def _parse_blocked_by_string(string):
    assert string.startswith(BLOCKED_BY_TAG)
    return string[len(BLOCKED_BY_TAG):]

def _add_remove_extra_string(bug, string, add):
    estrs = bug.extra_strings
    if add == True:
        estrs.append(string)
    else: # remove the string
        estrs.remove(string)
    bug.extra_strings = estrs # reassign to notice change

def _get_blocks(bug):
    uuids = []
    for line in bug.extra_strings:
        if line.startswith(BLOCKS_TAG):
            uuids.append(_parse_blocks_string(line))
    return uuids

def _get_blocked_by(bug):
    uuids = []
    for line in bug.extra_strings:
        if line.startswith(BLOCKED_BY_TAG):
            uuids.append(_parse_blocked_by_string(line))
    return uuids

def _repair_one_way_link(blocked_bug, blocking_bug, blocks=None):
    if blocks == True: # add blocks link
        blocks_string = _generate_blocks_string(blocked_bug)
        _add_remove_extra_string(blocking_bug, blocks_string, add=True)
    else: # add blocked by link
        blocked_by_string = _generate_blocked_by_string(blocking_bug)
        _add_remove_extra_string(blocked_bug, blocked_by_string, add=True)

# functions exposed to other modules

def add_block(blocked_bug, blocking_bug):
    blocked_by_string = _generate_blocked_by_string(blocking_bug)
    _add_remove_extra_string(blocked_bug, blocked_by_string, add=True)
    blocks_string = _generate_blocks_string(blocked_bug)
    _add_remove_extra_string(blocking_bug, blocks_string, add=True)

def remove_block(blocked_bug, blocking_bug):
    blocked_by_string = _generate_blocked_by_string(blocking_bug)
    _add_remove_extra_string(blocked_bug, blocked_by_string, add=False)
    blocks_string = _generate_blocks_string(blocked_bug)
    _add_remove_extra_string(blocking_bug, blocks_string, add=False)

def get_blocks(bugdir, bug):
    """
    Return a list of bugs that the given bug blocks.
    """
    blocks = []
    for uuid in _get_blocks(bug):
        blocks.append(bugdir.bug_from_uuid(uuid))
    return blocks

def get_blocked_by(bugdir, bug):
    """
    Return a list of bugs blocking the given bug.
    """
    blocked_by = []
    for uuid in _get_blocked_by(bug):
        blocked_by.append(bugdir.bug_from_uuid(uuid))
    return blocked_by

def check_dependencies(bugdir, repair_broken_links=False):
    """
    Check that links are bi-directional for all bugs in bugdir.

    >>> import libbe.bugdir
    >>> bd = libbe.bugdir.SimpleBugDir()
    >>> a = bd.bug_from_uuid("a")
    >>> b = bd.bug_from_uuid("b")
    >>> blocked_by_string = _generate_blocked_by_string(b)
    >>> _add_remove_extra_string(a, blocked_by_string, add=True)
    >>> good,repaired,broken = check_dependencies(bd, repair_broken_links=False)
    >>> good
    []
    >>> repaired
    []
    >>> broken
    [(Bug(uuid='a'), Bug(uuid='b'))]
    >>> _get_blocks(b)
    []
    >>> good,repaired,broken = check_dependencies(bd, repair_broken_links=True)
    >>> _get_blocks(b)
    ['a']
    >>> good
    []
    >>> repaired
    [(Bug(uuid='a'), Bug(uuid='b'))]
    >>> broken
    []
    """
    if bugdir.storage != None:
        bugdir.load_all_bugs()
    good_links = []
    fixed_links = []
    broken_links = []
    for bug in bugdir:
        for blocker in get_blocked_by(bugdir, bug):
            blocks = get_blocks(bugdir, blocker)
            if (bug, blocks) in good_links+fixed_links+broken_links:
                continue # already checked that link
            if bug not in blocks:
                if repair_broken_links == True:
                    _repair_one_way_link(bug, blocker, blocks=True)
                    fixed_links.append((bug, blocker))
                else:
                    broken_links.append((bug, blocker))
            else:
                good_links.append((bug, blocker))
        for blockee in get_blocks(bugdir, bug):
            blocked_by = get_blocked_by(bugdir, blockee)
            if (blockee, bug) in good_links+fixed_links+broken_links:
                continue # already checked that link
            if bug not in blocked_by:
                if repair_broken_links == True:
                    _repair_one_way_link(blockee, bug, blocks=False)
                    fixed_links.append((blockee, bug))
                else:
                    broken_links.append((blockee, bug))
            else:
                good_links.append((blockee, bug))
    return (good_links, fixed_links, broken_links)

class DependencyTree (object):
    """
    Note: should probably be DependencyDiGraph.
    """
    def __init__(self, bugdir, root_bug, depth_limit=0,
                 allowed_status_values=None,
                 allowed_severity_values=None):
        self.bugdir = bugdir
        self.root_bug = root_bug
        self.depth_limit = depth_limit
        self.allowed_status_values = allowed_status_values
        self.allowed_severity_values = allowed_severity_values

    def _build_tree(self, child_fn):
        root = tree.Tree()
        root.bug = self.root_bug
        root.depth = 0
        stack = [root]
        while len(stack) > 0:
            node = stack.pop()
            if self.depth_limit > 0 and node.depth == self.depth_limit:
                continue
            for bug in child_fn(self.bugdir, node.bug):
                if self.allowed_status_values != None \
                        and not bug.status in self.allowed_status_values:
                    continue
                if self.allowed_severity_values != None \
                        and not bug.severity in self.allowed_severity_values:
                    continue
                child = tree.Tree()
                child.bug = bug
                child.depth = node.depth+1
                node.append(child)
                stack.append(child)
        return root

    def blocks_tree(self):
        if not hasattr(self, "_blocks_tree"):
            self._blocks_tree = self._build_tree(get_blocks)
        return self._blocks_tree

    def blocked_by_tree(self):
        if not hasattr(self, "_blocked_by_tree"):
            self._blocked_by_tree = self._build_tree(get_blocked_by)
        return self._blocked_by_tree
