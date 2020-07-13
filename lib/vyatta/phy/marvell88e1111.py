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

    ADV_ASYM_PAUSE = 1 << 11
    ADV_PAUSE = 1 << 10
    ADV_100FD = 1 << 8
    ADV_100HD = 1 << 7
    ADV_10FD = 1 << 6
    ADV_10HD = 1 << 5

    STS_1000FD = 1 << 11
    STS_1000HD = 1 << 10

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

    def _phy_soft_reset(self, bus):
        '''
        Perform a software reset and wait for it to complete
        '''
        self._phy_modify_reg(bus, self.REG_CTRL, 0, self.CTRL_RESET)

        # From 802.3 22.2.4.1.1: The reset process shall be completed
        # within 0.5 s from the setting of bit 0.15
        # So we shoot a bit over to 0.525s
        for i in range(0, 600, 75):
            if not (socket.ntohs(bus.read_word_data(self.PHYADDR, self.REG_CTRL)) & self.CTRL_RESET):
                return
            # 75ms
            sleep(0.075)
        raise PhyAccessException("reset timed out")

    def enable_sgmii(self, bus):
        self._phy_modify_reg(bus, self.REG_EX_PHY_STATUS,
                             self.HWCFG_MODE_MASK | self.FIBER_COPPER_AS_MASK,
                             self.HWCFG_MODE_SGMII_NO_CLOCK | self.FIBER_COPPER_AS_DISABLE)
        # Commit the hardware config mode and fiber/copper
        # auto-selection changes by performing a soft reset
        self._phy_soft_reset(bus)

        self.set_autoneg_caps(bus, {'1000full': True, '1000half': True, '100full': True, '100half': True, '10full': True, '10half': True })

    def set_autoneg_caps(self, bus, speeds):
        an_adv = self.ADV_PAUSE | self.ADV_ASYM_PAUSE
        if speeds.get('100full', False):
            an_adv |= self.ADV_100FD
        if speeds.get('100half', False):
            an_adv |= self.ADV_100HD
        if speeds.get('10full', False):
            an_adv |= self.ADV_10FD
        if speeds.get('10half', False):
            an_adv |= self.ADV_10HD

        gbaset = 0
        if speeds.get('1000full', False):
            gbaset |= self.CTRL_1000BASE_T_FD
        if speeds.get('1000half', False):
            gbaset |= self.CTRL_1000BASE_T_HD

        self._phy_modify_reg(bus, self.REG_AUTONEG_ADV,
                             self.ADV_PAUSE | self.ADV_ASYM_PAUSE |
                             self.ADV_100FD | self.ADV_100HD | self.ADV_10FD |
                             self.ADV_10HD,
                             an_adv)
        self._phy_modify_reg(bus, self.REG_1000BASET_CTRL,
                             self.CTRL_1000BASE_T_FD | self.CTRL_1000BASE_T_HD,
                             gbaset)

        self._phy_modify_reg(bus, self.REG_CTRL, 0, self.CTRL_AN_ENABLE)

        # Commit the auto-neg enablement and advertisement changes
        self._phy_soft_reset(bus)

    def get_linkpartner_caps(self, bus):
        caps = {}
        an_caps = socket.ntohs(bus.read_word_data(self.PHYADDR, self.REG_LPABIL))

        if an_caps & self.ADV_100FD:
            caps['100full'] = True
        if an_caps & self.ADV_100HD:
            caps['100half'] = True
        if an_caps & self.ADV_10FD:
            caps['10full'] = True
        if an_caps & self.ADV_10HD:
            caps['10half'] = True

        gbaset = socket.ntohs(bus.read_word_data(self.PHYADDR, self.REG_1000BASET_STS))
        if gbaset & self.STS_1000FD:
            caps['1000full'] = True
        if gbaset & self.STS_1000HD:
            caps['1000half'] = True

        return caps

    def get_linkstatus(self, bus):
        phy_sts = socket.ntohs(bus.read_word_data(self.PHYADDR, self.REG_PHY_STS))
        link_str = 'down'
        speed = 0
        duplex = 'unknown'
        if phy_sts & 0x0400:
            link_str = 'up'
        # If speed and duplex resolved
        if phy_sts & 0x0800:
            if phy_sts & 0x2000:
                duplex = 'full'
            else:
                duplex = 'half'
            if phy_sts & 0xc000 == 0x0000:
                speed = 10
            elif phy_sts & 0xc000 == 0x4000:
                speed = 100
            elif phy_sts & 0xc000 == 0x8000:
                speed = 1000

        return (link_str, speed, duplex)

    def set_speed_duplex(self, bus, speed, duplex):
        ctrl_reg_val = self.CTRL_RESET
        speed_to_regval = {
            1000: 0x0040,
            100: 0x2000,
            10: 0x0000,
        }
        ctrl_reg_val |= speed_to_regval[speed]
        if duplex == 'half':
            # bit 8 = 0
            pass
        else:
            ctrl_reg_val |= 0x0100
        self._phy_modify_reg(bus, self.REG_CTRL, 0x2140 | self.CTRL_AN_ENABLE, ctrl_reg_val)
