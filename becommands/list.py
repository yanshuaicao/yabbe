# Copyright (C) 2005-2009 Aaron Bentley and Panometrics, Inc.
#                         Gianluca Montecchi <gian@grys.it>
#                         Oleg Romanyshyn <oromanyshyn@panoramicfeedback.com>
#                         W. Trevor King <wking@drexel.edu>
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
"""List bugs"""
from libbe import cmdutil, bugdir, bug
import os
import re
__desc__ = __doc__

# get a list of * for cmp_*() comparing two bugs. 
AVAILABLE_CMPS = [fn[4:] for fn in dir(bug) if fn[:4] == 'cmp_']
AVAILABLE_CMPS.remove("attr") # a cmp_* template.

def execute(args, manipulate_encodings=True, restrict_file_access=False):
    """
    >>> import os
    >>> bd = bugdir.SimpleBugDir()
    >>> os.chdir(bd.root)
    >>> execute([], manipulate_encodings=False)
    a:om: Bug A
    >>> execute(["--status", "closed"], manipulate_encodings=False)
    b:cm: Bug B
    >>> bd.cleanup()
    """
    parser = get_parser()
    options, args = parser.parse_args(args)
    complete(options, args, parser)    
    if len(args) > 0:
        raise cmdutil.UsageError("Too many arguments.")
    cmp_list = []
    if options.sort_by != None:
        for cmp in options.sort_by.split(','):
            if cmp not in AVAILABLE_CMPS:
                raise cmdutil.UserError(
                    "Invalid sort on '%s'.\nValid sorts:\n  %s"
                    % (cmp, '\n  '.join(AVAILABLE_CMPS)))
            cmp_list.append(eval('bug.cmp_%s' % cmp))
    
    bd = bugdir.BugDir(from_disk=True,
                       manipulate_encodings=manipulate_encodings)
    bd.load_all_bugs()
    # select status
    if options.status != None:
        if options.status == "all":
            status = bug.status_values
        else:
            status = cmdutil.select_values(options.status, bug.status_values)
    else:
        status = []
        if options.active == True:
            status.extend(list(bug.active_status_values))
        if options.unconfirmed == True:
            status.append("unconfirmed")
        if options.open == True:
            status.append("opened")
        if options.test == True:
            status.append("test")
        if status == []: # set the default value
            status = bug.active_status_values
    # select severity
    if options.severity != None:
        if options.severity == "all":
            severity = bug.severity_values
        else:
            severity = cmdutil.select_values(options.severity,
                                             bug.severity_values)
    else:
        severity = []
        if options.wishlist == True:
            severity.extend("wishlist")
        if options.important == True:
            serious = bug.severity_values.index("serious")
            severity.append(list(bug.severity_values[serious:]))
        if severity == []: # set the default value
            severity = bug.severity_values
    # select assigned
    if options.assigned != None:
        if options.assigned == "all":
            assigned = "all"
        else:
            possible_assignees = []
            for _bug in bd:
                if _bug.assigned != None \
                        and not _bug.assigned in possible_assignees:
                    possible_assignees.append(_bug.assigned)
            assigned = cmdutil.select_values(options.assigned,
                                             possible_assignees)
            print 'assigned', assigned
    else:
        assigned = []
        if options.mine == True:
            assigned.extend('-')
        if assigned == []: # set the default value
            assigned = "all"
    for i in range(len(assigned)):
        if assigned[i] == '-':
            assigned[i] = bd.user_id
    if options.extra_strings != None:
        extra_string_regexps = [re.compile(x) for x in options.extra_strings.split(',')]

    def filter(bug):
        if status != "all" and not bug.status in status:
            return False
        if severity != "all" and not bug.severity in severity:
            return False
        if assigned != "all" and not bug.assigned in assigned:
            return False
        if options.extra_strings != None:
            if len(bug.extra_strings) == 0 and len(extra_string_regexps) > 0:
                return False
            for string in bug.extra_strings:
                for regexp in extra_string_regexps:
                    if not regexp.match(string):
                        return False
        return True

    bugs = [b for b in bd if filter(b) ]
    if len(bugs) == 0 and options.xml == False:
        print "No matching bugs found"
    
    def list_bugs(cur_bugs, title=None, just_uuids=False, xml=False):
        if xml == True:
            print '<?xml version="1.0" encoding="%s" ?>' % bd.encoding
            print "<bugs>"
        if len(cur_bugs) > 0:
            if title != None and xml == False:
                print cmdutil.underlined(title)
            for bg in cur_bugs:
                if xml == True:
                    print bg.xml(show_comments=True)
                elif just_uuids:
                    print bg.uuid
                else:
                    print bg.string(shortlist=True)
        if xml == True:
            print "</bugs>"

    # sort bugs
    cmp_list.extend(bug.DEFAULT_CMP_FULL_CMP_LIST)
    cmp_fn = bug.BugCompoundComparator(cmp_list=cmp_list)
    bugs.sort(cmp_fn)

    # print list of bugs
    list_bugs(bugs, just_uuids=options.uuids, xml=options.xml)

def get_parser():
    parser = cmdutil.CmdOptionParser("be list [options]")
    parser.add_option("--status", dest="status", metavar="STATUS",
                      help="Only show bugs matching the STATUS specifier")
    parser.add_option("--severity", dest="severity", metavar="SEVERITY",
                      help="Only show bugs matching the SEVERITY specifier")
    parser.add_option("-a", "--assigned", metavar="ASSIGNED", dest="assigned",
                      help="List bugs matching ASSIGNED", default=None)
    parser.add_option("-e", "--extra-strings", metavar="STRINGS", dest="extra_strings",
                      help="List bugs matching _all_ extra strings in comma-seperated list STRINGS.  e.g. --extra-strings TAG:working,TAG:xml", default=None)
    parser.add_option("-S", "--sort", metavar="SORT-BY", dest="sort_by",
                      help="Adjust bug-sort criteria with comma-separated list SORT-BY.  e.g. \"--sort creator,time\".  Available criteria: %s" % ','.join(AVAILABLE_CMPS), default=None)
    # boolean options.  All but uuids and xml are special cases of long forms
    bools = (("u", "uuids", "Only print the bug UUIDS"),
             ("x", "xml", "Dump as XML"),
             ("w", "wishlist", "List bugs with 'wishlist' severity"),
             ("i", "important", "List bugs with >= 'serious' severity"),
             ("A", "active", "List all active bugs"),
             ("U", "unconfirmed", "List unconfirmed bugs"),
             ("o", "open", "List open bugs"),
             ("T", "test", "List bugs in testing"),
             ("m", "mine", "List bugs assigned to you"))
    for s in bools:
        attr = s[1].replace('-','_')
        short = "-%c" % s[0]
        long = "--%s" % s[1]
        help = s[2]
        parser.add_option(short, long, action="store_true",
                          dest=attr, help=help, default=False)
    return parser


def help():
    longhelp="""
This command lists bugs.  Normally it prints a short string like
  576:om: Allow attachments
Where
  576   the bug id
  o     the bug status is 'open' (first letter)
  m     the bug severity is 'minor' (first letter)
  Allo... the bug summary string

You can optionally (-u) print only the bug ids.

There are several criteria that you can filter by:
  * status
  * severity
  * assigned (who the bug is assigned to)
Allowed values for each criterion may be given in a comma seperated
list.  The special string "all" may be used with any of these options
to match all values of the criterion.  As with the --status and
--severity options for `be depend`, starting the list with a minus
sign makes your selections a blacklist instead of the default
whitelist.

status
  %s
severity
  %s
assigned
  free form, with the string '-' being a shortcut for yourself.

In addition, there are some shortcut options that set boolean flags.
The boolean options are ignored if the matching string option is used.
""" % (','.join(bug.status_values),
       ','.join(bug.severity_values))
    return get_parser().help_str() + longhelp

def complete(options, args, parser):
    for option, value in cmdutil.option_value_pairs(options, parser):
        if value == "--complete":
            if option == "status":
                raise cmdutil.GetCompletions(bug.status_values)
            elif option == "severity":
                raise cmdutil.GetCompletions(bug.severity_values)
            raise cmdutil.GetCompletions()
    if "--complete" in args:
        raise cmdutil.GetCompletions() # no positional arguments for list
