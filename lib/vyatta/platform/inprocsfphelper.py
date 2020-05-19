#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Copyright (c) 2019, AT&T Intellectual Property.  All rights reserved.
#
# SPDX-License-Identifier: LGPL-2.1-only

import os
import select
import subprocess
import zmq
import base64
from vyatta.platform.basesfphelper import BaseSfpHelper
from vyatta.platform.basesfphelper import SfpHelperException
from vyatta.phy.phy import PhyBus
from vyatta.phy.basephy import PhyNotFoundException, PhyAccessException

class InprocSfpHelper(BaseSfpHelper):
    """Implement the SFP helper for the platforms that use the Inproc i2x bus

    The SFPs on the S/M/L platforms are accessed by an i2c bus via the
    Broadcom APIs. To get/set values from the SFP messages are sent to
    the FAL via ZMQm and the FAL will then get/set the values via Broadocm
    APIs.

    """
    def __init__(self, sfpd):
        self.sfpd = sfpd

    class InprocSfpBus():
        def __init__(self, parent, porttype, port):
            self.porttype = porttype
            self.port = port
            self.sfpd = parent.sfpd

        def read_word_data(self, phyaddr, reg_ctrl):
            """ Request the phy via the ZMQ socket to the FAL """
            with self.sfpd.sfpmgr.get_req_socket() as req_socket:
                req_socket.connect(self.sfpd.sfpmgr.get_req_socket_endpoint())

                phy_req = {}
                phy_req['command'] = 'PHYOPERATION'
                phy_req['subcmd'] = 'PHYREADWORD'
                phy_req['porttype'] = self.porttype
                phy_req['port'] = self.port
                phy_req['addr'] = phyaddr
                phy_req['regctrl'] = reg_ctrl

                req_socket.send_json(phy_req);
                msg = req_socket.recv_json(strict=False)

                if msg['result'] == 'OK':
                    data = msg['data']
                    hex_data = int(data, 16)
                    return hex_data
                else:
                    raise PhyNotFoundException("read data result %s" % msg['result'])

        def write_word_data(self, phyaddr, reg_ctrl, data):
            """ Request the phy via the ZMQ socket to the FAL """
            with self.sfpd.sfpmgr.get_req_socket() as req_socket:
                req_socket.connect(self.sfpd.sfpmgr.get_req_socket_endpoint())

                phy_req = {}
                phy_req['command'] = 'PHYOPERATION'
                phy_req['subcmd'] = 'PHYWRITEWORD'
                phy_req['porttype'] = self.porttype
                phy_req['port'] = self.port
                phy_req['addr'] = phyaddr
                phy_req['regctrl'] = reg_ctrl
                phy_req['regdata'] = data

                req_socket.send_json(phy_req);
                msg = req_socket.recv_json(strict=False)
                if msg['result'] != 'OK':
                    raise PhyNotFoundException("Write data result %s" % msg['result'])

    def get_bus(self, porttype, port):
        return self.InprocSfpBus(self, porttype, port)

    def set_sfp_state(self, portname, enabled):
        pass

    def set_sgmii_enabled(self, porttype, port):
        is_sgmii = False
        bus = self.get_bus(porttype, port)
        try:
            phy = PhyBus.create_phy(bus)
            is_sgmii = phy.is_sgmii_capable(bus)
            if is_sgmii:
                try:
                    phy.enable_sgmii(bus)
                except Exception as e:
                    return False
        except PhyNotFoundException as e:
            return False

        return is_sgmii

    def set_phy_speed_duplex(self, porttype, port, speed, duplex):
        """
        Set the PHY forced speed and duplex mode
        """
        bus = self.get_bus(porttype, port)
        try:
            phy = PhyBus.create_phy(bus)
            phy.set_speed_duplex(bus, speed, duplex)
        except Exception as e:
            pass

    def set_phy_autoneg(self, porttype, port):
        """
        Set the PHY autonegotiate to on
        """
        bus = self.get_bus(porttype, port)
        try:
            phy = PhyBus.create_phy(bus)

            phy.set_autoneg_caps(bus, {'1000full': True, '1000half': True, '100full': True, '100half': True, '10full': True, '10half': True })
        except Exception as e:
            pass

    def main_loop(self, file_evmask_tuple_list):
        p = select.poll()

        for (f, evmask) in file_evmask_tuple_list:
            p.register(f, evmask)

        while True:
            evtuple_list = p.poll()
            for (fd, event) in evtuple_list:
                self.sfpd.on_file_event(fd, event)

    def read_eeprom(self, porttype, port, offset=None, length=None):
        """ Request the eeprom via the ZMQ socket to the FAL """
        with self.sfpd.sfpmgr.get_req_socket() as req_socket:
            req_socket.connect(self.sfpd.sfpmgr.get_req_socket_endpoint())

            eeprom_req = {}
            eeprom_req['command'] = 'SFPREADEEPROM'
            eeprom_req['porttype'] = porttype
            eeprom_req['port'] = port
            if offset:
                eeprom_req['offset'] = offset
            else:
                eeprom_req['offset'] = 0

            if length:
                eeprom_req['length'] = length
            else:
                eeprom_req['length'] = 0

            req_socket.send_json(eeprom_req);
            msg = req_socket.recv_json(strict=False)

            if msg['result'] == 'OK':
                data = base64.b64decode(msg['data'])
                return bytes(data)
            elif msg['result'] == 'NOSFP':
                raise SfpHelperException

    def query_eeprom(self, porttype, port):
        """Get the set of pages that the spf has

        If an SFP read the DMT byte from page a0 of the sfp.  If implemented
        then we have pages a0 and a2 otherwise just a0.

        If a QSFP then assume pages 00h to 03h are all present.
        """
        pages = []
        if porttype == 'SFP':

            data = self.read_eeprom(porttype, port, self.DMT_BYTE, 1)
            if (data):
                pages.append(0xa0)
                dmt_imp = data[0] & (self.DMT_IMPL|self.DMT_ADDR_CHNG_REQ) == self.DMT_IMPL
                if dmt_imp:
                    pages.append(0xa2)

            else:
                    raise SfpHelperException
        elif porttype == 'QSFP':
            for page in range(4):
                pages.append(page)
        else:
            raise Exception("unexpected port type {}".format(porttype))
        return pages

def new_helper(sfpd):
    return InprocSfpHelper(sfpd)
