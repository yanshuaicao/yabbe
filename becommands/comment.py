# Copyright (C) 2005-2009 Aaron Bentley and Panometrics, Inc.
#                         Chris Ball <cjb@laptop.org>
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
"""Add a comment to a bug"""
from libbe import cmdutil, bugdir, comment, editor
import os
import sys
try: # import core module, Python >= 2.5
    from xml.etree import ElementTree
except ImportError: # look for non-core module
    from elementtree import ElementTree
__desc__ = __doc__

def execute(args, manipulate_encodings=True):
    """
    >>> import time
    >>> bd = bugdir.SimpleBugDir()
    >>> os.chdir(bd.root)
    >>> execute(["a", "This is a comment about a"], manipulate_encodings=False)
    >>> bd._clear_bugs()
    >>> bug = cmdutil.bug_from_shortname(bd, "a")
    >>> bug.load_comments(load_full=False)
    >>> comment = bug.comment_root[0]
    >>> print comment.body
    This is a comment about a
    <BLANKLINE>
    >>> comment.author == bd.user_id
    True
    >>> comment.time <= int(time.time())
    True
    >>> comment.in_reply_to is None
    True

    >>> if 'EDITOR' in os.environ:
    ...     del os.environ["EDITOR"]
    >>> execute(["b"], manipulate_encodings=False)
    Traceback (most recent call last):
    UserError: No comment supplied, and EDITOR not specified.

    >>> os.environ["EDITOR"] = "echo 'I like cheese' > "
    >>> execute(["b"], manipulate_encodings=False)
    >>> bd._clear_bugs()
    >>> bug = cmdutil.bug_from_shortname(bd, "b")
    >>> bug.load_comments(load_full=False)
    >>> comment = bug.comment_root[0]
    >>> print comment.body
    I like cheese
    <BLANKLINE>
    >>> bd.cleanup()
    """
    parser = get_parser()
    options, args = parser.parse_args(args)
    complete(options, args, parser)
    if len(args) == 0:
        raise cmdutil.UsageError("Please specify a bug or comment id.")
    if len(args) > 2:
        raise cmdutil.UsageError("Too many arguments.")

    shortname = args[0]
    if shortname.count(':') > 1:
        raise cmdutil.UserError("Invalid id '%s'." % shortname)
    elif shortname.count(':') == 1:
        # Split shortname generated by Comment.comment_shortnames()
        bugname = shortname.split(':')[0]
        is_reply = True
    else:
        bugname = shortname
        is_reply = False

    bd = bugdir.BugDir(from_disk=True,
                       manipulate_encodings=manipulate_encodings)
    bug = cmdutil.bug_from_shortname(bd, bugname)
    bug.load_comments(load_full=False)
    if is_reply:
        parent = bug.comment_root.comment_from_shortname(shortname,
                                                         bug_shortname=bugname)
    else:
        parent = bug.comment_root

    if len(args) == 1: # try to launch an editor for comment-body entry
        try:
            if parent == bug.comment_root:
                parent_body = bug.summary+"\n"
            else:
                parent_body = parent.body
            estr = "Please enter your comment above\n\n> %s\n" \
                % ("\n> ".join(parent_body.splitlines()))
            body = editor.editor_string(estr)
        except editor.CantFindEditor, e:
            raise cmdutil.UserError, "No comment supplied, and EDITOR not specified."
        if body is None:
            raise cmdutil.UserError("No comment entered.")
    elif args[1] == '-': # read body from stdin
        binary = not (options.content_type == None
                      or options.content_type.startswith("text/"))
        if not binary:
            body = sys.stdin.read()
            if not body.endswith('\n'):
                body+='\n'
        else: # read-in without decoding
            body = sys.__stdin__.read()
    else: # body = arg[1]
        body = args[1]
        if not body.endswith('\n'):
            body+='\n'

    if options.XML == False:
        new = parent.new_reply(body=body, content_type=options.content_type)
        if options.author != None:
            new.author = options.author
        if options.alt_id != None:
            new.alt_id = options.alt_id
    else: # import XML comment [list]
        # read in the comments
        str_body = body.encode("unicode_escape").replace(r'\n', '\n')
        comment_list = ElementTree.XML(str_body)
        if comment_list.tag not in ["bug", "comment-list"]:
            raise comment.InvalidXML(
                comment_list, "root element must be <bug> or <comment-list>")
        new_comments = []
        ids = []
        for c in bug.comment_root.traverse():
            ids.append(c.uuid)
            if c.alt_id != None:
                ids.append(c.alt_id)
        for child in comment_list.getchildren():
            if child.tag == "comment":
                new = comment.Comment(bug)
                new.from_xml(unicode(ElementTree.tostring(child)).decode("unicode_escape"))
                if new.alt_id in ids:
                    raise cmdutil.UserError(
                        "Clashing comment alt_id: %s" % new.alt_id)
                ids.append(new.uuid)
                if new.alt_id != None:
                    ids.append(new.alt_id)
                if new.in_reply_to == None:
                    new.in_reply_to = parent.uuid
                new_comments.append(new)
            else:
                print >> sys.stderr, "Ignoring unknown tag %s in %s" \
                    % (child.tag, comment_list.tag)
        try:
            comment.list_to_root(new_comments,bug,root=parent, # link new comments
                                 ignore_missing_references=options.ignore_missing_references)
        except comment.MissingReference, e:
            raise cmdutil.UserError(e)
        # Protect against programmer error causing data loss:
        kids = [c.uuid for c in parent.traverse()]
        for nc in new_comments:
            assert nc.uuid in kids, "%s wasn't added to %s" % (nc.uuid, parent.uuid)
            nc.save()

def get_parser():
    parser = cmdutil.CmdOptionParser("be comment ID [COMMENT]")
    parser.add_option("-a", "--author", metavar="AUTHOR", dest="author",
                      help="Set the comment author", default=None)
    parser.add_option("--alt-id", metavar="ID", dest="alt_id",
                      help="Set an alternate comment ID", default=None)
    parser.add_option("-c", "--content-type", metavar="MIME", dest="content_type",
                      help="Set comment content-type (e.g. text/plain)", default=None)
    parser.add_option("-x", "--xml", action="store_true", default=False,
                      dest='XML', help="Use COMMENT to specify an XML comment description rather than the comment body.  The root XML element should be either <bug> or <comment-list> with one or more <comment> children.  The syntax for the <comment> elements should match that generated by 'be show --xml COMMENT-ID'.  Unrecognized tags are ignored.  Missing tags are left at the default value.  The comment UUIDs are always auto-generated, so if you set a <uuid> field, but no <alt-id> field, your <uuid> will be used as the comment's <alt-id>.  An exception is raised if <alt-id> conflicts with an existing comment.")
    parser.add_option("-i", "--ignore-missing-references", action="store_true",
                      dest="ignore_missing_references",
                      help="For XML import, if any comment's <in-reply-to> refers to a non-existent comment, ignore it (instead of raising an exception).")
    return parser

longhelp="""
To add a comment to a bug, use the bug ID as the argument.  To reply
to another comment, specify the comment name (as shown in "be show"
output).  COMMENT, if specified, should be either the text of your
comment or "-", in which case the text will be read from stdin.  If
you do not specify a COMMENT, $EDITOR is used to launch an editor.  If
COMMENT is unspecified and EDITOR is not set, no comment will be
created.
"""

def help():
    return get_parser().help_str() + longhelp

def complete(options, args, parser):
    for option,value in cmdutil.option_value_pairs(options, parser):
        if value == "--complete":
            # no argument-options at the moment, so this is future-proofing
            raise cmdutil.GetCompletions()
    for pos,value in enumerate(args):
        if value == "--complete":
            if pos == 0: # fist positional argument is a bug or comment id
                if len(args) >= 2:
                    partial = args[1].split(':')[0] # take only bugid portion
                else:
                    partial = ""
                ids = []
                try:
                    bd = bugdir.BugDir(from_disk=True,
                                       manipulate_encodings=False)
                    bugs = []
                    for uuid in bd.list_uuids():
                        if uuid.startswith(partial):
                            bug = bd.bug_from_uuid(uuid)
                            if bug.active == True:
                                bugs.append(bug)
                    for bug in bugs:
                        shortname = bd.bug_shortname(bug)
                        ids.append(shortname)
                        bug.load_comments(load_full=False)
                        for id,comment in bug.comment_shortnames(shortname):
                            ids.append(id)
                except bugdir.NoBugDir:
                    pass
                raise cmdutil.GetCompletions(ids)
            raise cmdutil.GetCompletions()
