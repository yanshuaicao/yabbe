# Copyright (C) 2005-2009 Aaron Bentley and Panometrics, Inc.
#                         Gianluca Montecchi <gian@grys.it>
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

"""
Create, save, and load the per-user config file at path().
"""

import ConfigParser
import codecs
import os.path

import libbe
import libbe.util.encoding
if libbe.TESTING == True:
    import doctest


default_encoding = libbe.util.encoding.get_filesystem_encoding()

def path():
    """Return the path to the per-user config file"""
    return os.path.expanduser("~/.bugs_everywhere")

def set_val(name, value, section="DEFAULT", encoding=None):
    """Set a value in the per-user config file

    :param name: The name of the value to set
    :param value: The new value to set (or None to delete the value)
    :param section: The section to store the name/value in
    """
    if encoding == None:
        encoding = default_encoding
    config = ConfigParser.ConfigParser()
    if os.path.exists(path()) == False: # touch file or config
        open(path(), 'w').close()       # read chokes on missing file
    f = codecs.open(path(), 'r', encoding)
    config.readfp(f, path())
    f.close()
    if value is not None:
        config.set(section, name, value)
    else:
        config.remove_option(section, name)
    f = codecs.open(path(), 'w', encoding)
    config.write(f)
    f.close()

def get_val(name, section="DEFAULT", default=None, encoding=None):
    """
    Get a value from the per-user config file

    :param name: The name of the value to get
    :section: The section that the name is in
    :return: The value, or None
    >>> get_val("junk") is None
    True
    >>> set_val("junk", "random")
    >>> get_val("junk")
    u'random'
    >>> set_val("junk", None)
    >>> get_val("junk") is None
    True
    """
    if os.path.exists(path()):
        if encoding == None:
            encoding = default_encoding
        config = ConfigParser.ConfigParser()
        f = codecs.open(path(), 'r', encoding)
        config.readfp(f, path())
        f.close()
        try:
            return config.get(section, name)
        except ConfigParser.NoOptionError:
            return default
    else:
        return default

if libbe.TESTING == True:
    suite = doctest.DocTestSuite()
