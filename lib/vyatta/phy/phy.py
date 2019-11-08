#!/usr/bin/env python3
# Copyright (c) 2019, AT&T Intellectual Property.  All rights reserved.
#
# SPDX-License-Identifier: LGPL-2.1-only
# **** End License ****

from smbus import SMBus
import sys
import time
import errno
from vyatta.phy.marvell88e1111 import Marvell88E1111Phy
from vyatta.phy.basephy import PhyNotFoundException, PhyAccessException

class PhyType(object):
    def __init__(self, phyclass):
        self.phyid = phyclass.PHYID
        self.mask = phyclass.PHYMASK
        self.phyclass = phyclass

    def __eq__(self, other):
        return other & self.mask == self.phyid

class PhyBus:

    PHY_TABLE = [
        PhyType(Marvell88E1111Phy),
    ]

    # Finisar Application Note AN-2036 and by convention
    PHYADDR = 0x56
    # From IEEE 802.3-2000 clause 22, table 22-6
    PHYID_MSB_REG = 0x02
    PHYID_LSB_REG = 0x03

    @classmethod
    def get_phy_type(cls, phyid):
        for phytype in cls.PHY_TABLE:
            if phytype == phyid:
                return phytype.phyclass()

        raise PhyNotFoundException("unsupported phy with id 0x%x" % (phyid))


    @classmethod
    def create_phy(cls, bus):
        try:
            phyid1 = bus.read_word_data(cls.PHYADDR, cls.PHYID_MSB_REG)
            phyid2 = bus.read_word_data(cls.PHYADDR, cls.PHYID_LSB_REG)
        except PhyNotFoundException:
            raise PhyNotFoundException("phy at address 0x%x not found" % cls.PHYADDR)
        except OSError as e:
            if e.errno == errno.ENXIO:
                raise PhyNotFoundException("phy at address 0x56 not found") from e
            raise PhyAccessException(e.strerror) from e
        phyid = (phyid1 & 0xff) << 24 | (phyid1 >> 8) << 16 | \
                (phyid2 & 0xff) << 8 | (phyid2 >> 8)
        return cls.get_phy_type(phyid)

# Standalone test
def main():
    if len(sys.argv) != 2:
        print("\nUsage: " + sys.argv[0] + " <I2Cbus#>")
        return

    bus = SMBus(int(sys.argv[1]))
    phy = PhyBus.create_phy(bus)
    print("Is SGMII capable? " + str(phy.is_sgmii_capable(bus)))
    phy.enable_sgmii(bus)
    for i in range(1, 5):
        linkstatus = phy.get_linkstatus(bus)
        (link, _, _) = linkstatus
        print("Link status: " + str(linkstatus))
        print("Link partner caps: " + str(phy.get_linkpartner_caps(bus)))
        if link == 'up':
            break
        time.sleep(1)

if __name__ == "__main__":
    main()
