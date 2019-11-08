# **** License ****
# Copyright (c) 2019, AT&T Intellectual Property.  All rights reserved.
#
# SPDX-License-Identifier: LGPL-2.1-only
# **** End License ****

import logging
import sys
import subprocess
import os
import importlib

LOG = logging.getLogger('vyatta.platform.detect')

class PlatformError(Exception):
    pass

class DefaultPlatform(object):
    def is_switch(self):
        """
        Determine if this platform is a switch. If not, then it's a router
        """
        return True

    def get_platform_string(self):
        """
        Get a string that identifies the platform. This should be in
        the form <vendor>.<product>[.<revision>], where the components
        are all lower-case.
        """
        return ''

    def configure_dataplane(self, conf_file):
        """
        Configure the dataplane for the platform
        """
        return

    def __str__(self):
        return self.get_platform_string()

def gen_platform_type_modules():
    """
    Generator for found platform type modules (i.e. starting with
    vyatta.platform.type) in python library paths.
    """
    for path in sys.path:
        type_mod_path = os.path.join(path, 'vyatta', 'platform', 'type')
        if not os.path.isdir(type_mod_path):
            continue
        for entry in os.scandir(type_mod_path):
            if (entry.name.endswith('.py') or
                entry.name.endswith('.pyc')) and entry.is_file():
                # Strip off extension and prefix with vyatta.platform.type
                type_mod_name = '.'.join(['vyatta', 'platform', 'type',
                                          entry.name.rpartition('.')[0]])
                yield type_mod_name

def detect():
    """ Detect platform and return the platform object """
    sysmfr = subprocess.run(["/usr/sbin/dmidecode", "-s", "system-manufacturer"],
                            check=True, stdout=subprocess.PIPE,
                            universal_newlines=True).stdout
    sysmfr = sysmfr.rstrip('\n')
    sysname = subprocess.run(["/usr/sbin/dmidecode", "-s", "system-product-name"],
                             check=True, stdout=subprocess.PIPE,
                             universal_newlines=True).stdout
    sysname = sysname.rstrip('\n')
    # The expected way of identifying a platform is using the system
    # manufacturer and product name, but often on alpha units these
    # are not filled in and the best way of identifying Alpha units is
    # the BIOS version, so extract that so it can be used as well.
    biosver = subprocess.run(["/usr/sbin/dmidecode", "-s", "bios-version"],
                             check=True, stdout=subprocess.PIPE,
                             universal_newlines=True).stdout
    biosver = biosver.rstrip('\n')
    LOG.debug('sysmfr = {}, sysname = {}, biosvr = {}'.format(
        sysmfr, sysname, biosver))

    for mod_name in gen_platform_type_modules():
        plat_mod = importlib.import_module(mod_name)
        try:
            platform = plat_mod.detect(sysmfr=sysmfr, sysname=sysname, biosver=biosver)
        except PlatformError as e:
            LOG.debug('not detected as ' + mod_name + ' due to ' + repr(e))
            continue
        return platform

    raise PlatformError('no platform detected')

