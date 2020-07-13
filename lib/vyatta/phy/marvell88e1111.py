#!/usr/bin/env python3
# Copyright (c) 2019-2020, AT&T Intellectual Property.  All rights reserved.
#
# SPDX-License-Identifier: LGPL-2.1-only
# **** End License ****

from vyatta.phy.basephy import BasePhy
import socket

class Marvell88E1111Phy(BasePhy):
    '''
    Driver for Marvell 88E1111 PHY

    See 88E111 Datasheet for reference
    '''
    PHYID = 0x01410cc0
    PHYMASK = 0xfffffff0
    PHYADDR = 0x56 # 0xAC >> 1

    REG_CTRL = 0x00
    REG_1000BASET_CTRL = 0x09
    REG_1000BASET_STS = 0x0a
    REG_AUTONEG_ADV = 0x04
    REG_LPABIL = 0x05
    REG_PHY_STS = 0x11
    REG_EX_PHY_STATUS = 0x1b

    HWCFG_MODE_MASK = 0xf
    # SGMII without Clock with SGMII Auto-Neg to copper
    HWCFG_MODE_SGMII_NO_CLOCK = 0x4
    FIBER_COPPER_AS_MASK = 1 << 15
    # Fiber/Copper Auto Selection Disable
    FIBER_COPPER_AS_DISABLE = 1 << 15

    # PHY Software Reset
    CTRL_RESET = 0x8000
    # Auto-Negotiation Enable
    CTRL_AN_ENABLE = 1 << 12

    # Advertise 1000BASE-T full duplex
    CTRL_1000BASE_T_FD = 1 << 9
    # Advertise 1000BASE-T half duplex
    CTRL_1000BASE_T_HD = 1 << 8

    def is_sgmii_capable(self, bus):
        return True

    def _phy_modify_reg(self, bus, reg, mask, value):
        '''
        Modify a PHY register, masking off bits and or'ing in a new value

        Mask and value should be in host endian form.
        '''
        exist_value = socket.ntohs(bus.read_word_data(self.PHYADDR, reg))
        new_value = (exist_value & ~mask) | value
        bus.write_word_data(self.PHYADDR, reg, socket.htons(new_value))

    def enable_sgmii(self, bus):
        self._phy_modify_reg(bus, self.REG_EX_PHY_STATUS,
                             self.HWCFG_MODE_MASK | self.FIBER_COPPER_AS_MASK,
                             self.HWCFG_MODE_SGMII_NO_CLOCK | self.FIBER_COPPER_AS_DISABLE)
        # Commit the hardware config mode and fiber/copper
        # auto-selection changes by performing a soft reset
        self._phy_modify_reg(bus, self.REG_CTRL, 0, self.CTRL_RESET)

        self.set_autoneg_caps(bus, {'1000full': True, '1000half': True, '100full': True, '100half': True, '10full': True, '10half': True })

    def set_autoneg_caps(self, bus, speeds):
        # Asymmetric Pause, Pause, Selector Field = 802.3
        an_adv = 0x010c
        gbaset = bus.read_word_data(self.PHYADDR, self.REG_1000BASET_CTRL)

        if speeds.get('100full', False):
            an_adv |= 0x0001
        if speeds.get('100half', False):
            an_adv |= 0x8000
        if speeds.get('10full', False):
            an_adv |= 0x4000
        if speeds.get('10half', False):
            an_adv |= 0x2000

        gbaset = gbaset & ~0x0003
        if speeds.get('1000full', False):
            gbaset |= 0x0001
        if speeds.get('1000half', False):
            gbaset |= 0x0002

        bus.write_word_data(self.PHYADDR, self.REG_AUTONEG_ADV, an_adv)
        bus.write_word_data(self.PHYADDR, self.REG_1000BASET_CTRL, gbaset)

        # Set Reset, Auto-Negotiation Enable
        bus.write_word_data(self.PHYADDR, self.REG_CTRL, 0x4091)

    def get_linkpartner_caps(self, bus):
        caps = {}
        an_caps = bus.read_word_data(self.PHYADDR, self.REG_LPABIL)

        if an_caps & 0x0001:
            caps['100full'] = True
        if an_caps & 0x8000:
            caps['100half'] = True
        if an_caps & 0x4000:
            caps['10full'] = True
        if an_caps & 0x2000:
            caps['10half'] = True

        gbaset = bus.read_word_data(self.PHYADDR, self.REG_1000BASET_STS)
        if gbaset & 0x0008:
            caps['1000full'] = True
        if gbaset & 0x0004:
            caps['1000half'] = True

        return caps

    def get_linkstatus(self, bus):
        phy_sts = bus.read_word_data(self.PHYADDR, self.REG_PHY_STS)
        link_str = 'down'
        speed = 0
        duplex = 'unknown'
        if phy_sts & 0x0004:
            link_str = 'up'
        # If speed and duplex resolved
        if phy_sts & 0x0008:
            if phy_sts & 0x0020:
                duplex = 'full'
            else:
                duplex = 'half'
            if phy_sts & 0x00c0 == 0x0000:
                speed = 10
            elif phy_sts & 0x00c0 == 0x0040:
                speed = 100
            elif phy_sts & 0x00c0 == 0x0080:
                speed = 1000

        return (link_str, speed, duplex)

    def set_speed_duplex(self, bus, speed, duplex):
        ctrl_reg_val = 0x0080
        speed_to_regval = {
            1000: 0x4000,
            100: 0x0020,
            10: 0x0000,
        }
        ctrl_reg_val |= speed_to_regval[speed]
        if duplex == 'half':
            # bit 8 = 0
            pass
        else:
            ctrl_reg_val |= 0x0001
        bus.write_word_data(self.PHYADDR, self.REG_CTRL, ctrl_reg_val)
