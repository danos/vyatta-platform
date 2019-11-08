#!/usr/bin/env python3
# Copyright (c) 2019, AT&T Intellectual Property.  All rights reserved.
#
# SPDX-License-Identifier: LGPL-2.1-only
# **** End License ****

from abc import ABC, abstractmethod

class PhyException(Exception):
    pass

class PhyNotFoundException(PhyException):
    def __init__(self, arg):
        self.arg = arg

class PhyAccessException(PhyException):
    def __init__(self, arg):
        self.arg = arg

class BasePhy(ABC):
    @abstractmethod
    def is_sgmii_capable(self, bus):
        """
        Is this PHY SGMII capable? If not, then it will be assumed
        that the PHY supports 1000BASE-X AN only over SERDES.
        """
        pass

    @abstractmethod
    def enable_sgmii(self, bus):
        """
        Enable SGMII mode on the PHY. If the PHY uses SGMII by default
        then this can be a no-op.
        """
        pass

    @abstractmethod
    def set_autoneg_caps(self, bus, caps):
        """
        Set auto-negotiate enabled and its capabilities.

        Caps is a map of key to boolean value that describes the set
        of capabilities to advertise. Capabilities supported are:
         - 1000full
         - 1000half
         - 100full
         - 100half
         - 10full
         - 10half
        Capabilities not supported should be ignored.
        """
        pass

    @abstractmethod
    def get_linkpartner_caps(self, bus):
        """
        Get the capabilities advertised by the link-partner.

        Returns a map of key to boolean value that describes the set
        of capabilities to advertise. Capabilities that may be
        supported include:
         - 1000full
         - 1000half
         - 100full
         - 100half
         - 10full
         - 10half
        """
        pass

    @abstractmethod
    def get_linkstatus(self, bus):
        """
        Get the link status.

        Returns a tuple of (<linkstatus>, <speed>, <duplex>). Where
        linkstatus is "up" or "down", speed is an integer number of
        Mbps used by the link, and duplex is "full", "half", or
        "unknown" (if auto-negotiated and auto-negotiate still in
        progress).
        """
        pass

    @abstractmethod
    def set_speed_duplex(self, bus, speed, duplex):
        """
        Disable autonegotiate and use the specified speed and duplex.
        """
        pass
