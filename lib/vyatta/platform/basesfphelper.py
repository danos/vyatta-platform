# Copyright (c) 2019-2020, AT&T Intellectual Property.  All rights reserved.
#
# SPDX-License-Identifier: LGPL-2.1-only

from abc import ABC, abstractmethod
import time
from vyatta.phy.phy import PhyBus
from vyatta.phy.basephy import PhyException

class SfpHelperException(Exception):
    pass

class BusNotSupportedException(SfpHelperException):
    def __init__(self, arg):
        self.arg = arg

class ModuleNotPresentException(SfpHelperException):
    def __init__(self, arg):
        self.arg = arg

class BaseSfpHelper(ABC):
    """
    Class that is the base of all SFP helper objects
    """

    # Possibly useful constants for concrete implementations

    # SFF-8472, Diagnostic Monitoring Type [Address A0h, Byte 92]
    DMT_BYTE = 92
    # implemented?
    DMT_IMPL = 0x40
    # address change required?
    DMT_ADDR_CHNG_REQ = 0x4

    # Common PHYs like the MVL88E1111 declare time from power on to
    # register read/write available being 15 msec, but we assume the
    # minimum granularity offered by the scheduler is in the order of
    # 75 msec and this also gives a bit of a margin.
    PHY_PROBE_TRIES = 1
    PHY_PROBE_RETRY_TIME = 0.075 # 75 msec

    @abstractmethod
    def get_bus(self, porttype, port):
        """
        Gets the bus for the given port.

        Returns an object with open, close and context manager
        methods.  The bus can be then be used to interact with any PHY
        that is present
        """
        pass

    @abstractmethod
    def set_sfp_state(self, portname, enabled):
        """
        Enable or disable a port.

        There may not be an SFP present in the port, but as soon as
        one is plugged in it should be disabled such that the lasers
        are not active and any device at the other end of the link
        doesn't see the link as up.
        """
        pass

    @abstractmethod
    def main_loop(self, file_evmask_tuple_list):
        """
        Main event loop

        Should loop forever and notify the parent listener by calling
        on_sfp_presence_change() or on_file_event() on it as SFP
        presence events, or other file events occur respectively.
        """
        pass

    @abstractmethod
    def read_eeprom(self, porttype, port, offset=None, length=None):
        """
        Reads the EEPROM for the given port.

        Returns one flat list for all pages in the specified range. If
        length isn't specified then it is assumed that all pages of
        the EEPROM should be read.
        """
        pass

    @abstractmethod
    def query_eeprom(self, porttype, port):
        """
        Query the EEPROM for pages that are implemented.

        Returns a list of the supported pages. For SFPs, this may
        consist of strings A0 and A2. For QSFP, this is a list of
        integers that may range from 0x00 to 0xff.
        """
        pass

    def process_sfpinsertedremoved(self, portname, porttype, port, inserted,
                                   extra_state):
        """
        Process the message that says an sfp has been plugged/unplugged
        """
        self.sfpd.on_sfp_presence_change(portname, porttype,
                                         port, inserted, extra_state)

    def set_sgmii_enabled(self, porttype, port):
        is_sgmii = False
        try:
            for i in range(0, self.PHY_PROBE_TRIES):
                with self.get_bus(porttype, port) as bus:
                    try:
                        phy = PhyBus.create_phy(bus)
                        is_sgmii = phy.is_sgmii_capable(bus)
                        if is_sgmii:
                            phy.enable_sgmii(bus)
                            break
                    except PhyException as e:
                        print(e)
                    time.sleep(self.PHY_PROBE_RETRY_TIME)
        except SfpHelperException as e:
            print(e)
        return is_sgmii

    def get_phy_link_status(self, porttype, port):
        """
        Get the link status of any PHY on the port
        """
        status = ("down", 0, "unknown")
        try:
            with self.get_bus(porttype, port) as bus:
                try:
                    phy = PhyBus.create_phy(bus)
                    status = phy.get_linkstatus(bus)
                except PhyException as e:
                    pass
        except SfpHelperException as e:
            pass
        return status

    def set_phy_speed_duplex(self, porttype, port, speed, duplex):
        """
        Set the PHY forced speed and duplex
        """
        try:
            with self.get_bus(porttype, port) as bus:
                try:
                    phy = PhyBus.create_phy(bus)
                    phy.set_speed_duplex(bus, speed, duplex)
                except PhyException as e:
                    pass
        except SfpHelperException as e:
            pass

    def set_phy_autoneg(self, porttype, port):
        """
        Set the PHY autonegotiate to on
        """
        try:
            with self.get_bus(porttype, port) as bus:
                try:
                    phy = PhyBus.create_phy(bus)

                    phy.set_autoneg_caps(bus, {'1000full': True, '1000half': True, '100full': True, '100half': True, '10full': True, '10half': True })
                except PhyException as e:
                    pass
        except SfpHelperException as e:
            pass
