#!/usr/bin/env python3

# Copyright (c) 2020 AT&T Intellectual Property.
# All rights reserved.
""" Decode the ONIE TLV data blob """

import sys

class ONIETLVInfo:
    # See https://opencomputeproject.github.io/onie/design-spec/hw_requirements.html

    TLVINFO_HEADER = 'TlvInfo'
    TLVINFO_INVALID = 0x0
    TLVINFO_TLV_FIELDS = 11
    TLVINFO_TLV_HEADER = 2
    TLVINFO_PRODUCT_NAME = 0x21
    TLVINFO_PART_NUMBER = 0x22
    TLVINFO_SERIAL_NUMBER = 0x23
    TLVINFO_MAC_1_BASE = 0x24
    TLVINFO_MANUFACTURE_DATE = 0x25
    TLVINFO_DEVICE_VERSION = 0x26
    TLVINFO_LABEL_REVISION = 0x27
    TLVINFO_PLATFORM_NAME = 0x28
    TLVINFO_ONIE_VERSION = 0x29
    TLVINFO_NUM_MACS = 0x2A
    TLVINFO_MANUFACTURER = 0x2B
    TLVINFO_COUNTRY_CODE = 0x2C
    TLVINFO_VENDOR = 0x2D
    TLVINFO_DIAG_VERSION = 0x2E
    TLVINFO_SERVICE_TAG = 0x2F
    TLVINFO_VENDOR_EXTENSION = 0xFD
    TLVINFO_CRC_32 = 0xFE

    def decode_variable(self, data, start, length):
        return ''.join('{:c}'.format(data[b]) for b in range(start, start + length))

    def decode_int(self, data, start):
        return int(data[start] << 24 | data[start + 1] << 16 | data[start + 2] << 8 | data[start + 3])

    def decode_short(self, data, start):
        return int(data[start] << 8 | data[start + 1])

    def decode(self, eeprom_data):
        header  = self.decode_variable(eeprom_data, 0, 7)
        if header != self.TLVINFO_HEADER:
            raise ValueError('The CPU EEPROM is corrupted or empty.')

        total_len = eeprom_data[9] * 256 + eeprom_data[10]

        decoded_data = dict()

        i = self.TLVINFO_TLV_FIELDS
        while i < total_len:
            tlv_type = eeprom_data[i]
            tlv_len = eeprom_data[i + 1]
            tlv_start = i + self.TLVINFO_TLV_HEADER

            if tlv_type == self.TLVINFO_INVALID:
                # This shouldn't happen. If it does, something is very wrong.
                raise ValueError('The CPU EEPROM is corrupted or empty.')

            elif tlv_type == self.TLVINFO_PRODUCT_NAME:
                decoded_data['product_name'] = self.decode_variable(eeprom_data, tlv_start, tlv_len)

            elif tlv_type == self.TLVINFO_PART_NUMBER:
                decoded_data['part_number'] = self.decode_variable(eeprom_data, tlv_start, tlv_len)

            elif tlv_type == self.TLVINFO_SERIAL_NUMBER:
                decoded_data['serial_number'] = self.decode_variable(eeprom_data, tlv_start, tlv_len)

            elif tlv_type == self.TLVINFO_MAC_1_BASE:
                base_mac  = ':'.join('{:02x}'.format(eeprom_data[b]) for b in range(tlv_start, tlv_start + tlv_len))
                decoded_data['base_mac'] = '{}'.format(base_mac)

            elif tlv_type == self.TLVINFO_MANUFACTURE_DATE:
                decoded_data['manufacture_date'] = self.decode_variable(eeprom_data, tlv_start, tlv_len)

            elif tlv_type == self.TLVINFO_DEVICE_VERSION:
                decoded_data['device_version'] = int(eeprom_data[tlv_start])

            elif tlv_type == self.TLVINFO_LABEL_REVISION:
                decoded_data['label_revision'] = self.decode_variable(eeprom_data, tlv_start, tlv_len)

            elif tlv_type == self.TLVINFO_PLATFORM_NAME:
                decoded_data['platform_name'] = self.decode_variable(eeprom_data, tlv_start, tlv_len)

            elif tlv_type == self.TLVINFO_ONIE_VERSION:
                decoded_data['onie_version'] = self.decode_variable(eeprom_data, tlv_start, tlv_len)

            elif tlv_type == self.TLVINFO_NUM_MACS:
                decoded_data['num_macs'] = self.decode_short(eeprom_data, tlv_start)

            elif tlv_type == self.TLVINFO_MANUFACTURER:
                decoded_data['manufacturer'] = self.decode_variable(eeprom_data, tlv_start, tlv_len)

            elif tlv_type == self.TLVINFO_COUNTRY_CODE:
                decoded_data['country_code'] = self.decode_variable(eeprom_data, tlv_start, tlv_len)

            elif tlv_type == self.TLVINFO_VENDOR:
                decoded_data['vendor'] = self.decode_variable(eeprom_data, tlv_start, tlv_len)

            elif tlv_type == self.TLVINFO_DIAG_VERSION:
                decoded_data['diag_version'] = self.decode_variable(eeprom_data, tlv_start, tlv_len)

            elif tlv_type == self.TLVINFO_SERVICE_TAG:
                decoded_data['service_tag'] = self.decode_variable(eeprom_data, tlv_start, tlv_len)

            elif tlv_type == self.TLVINFO_VENDOR_EXTENSION:
                iana_num = self.decode_int(eeprom_data, tlv_start)
                decoded_data['vendor_extension'] = (iana_num, self.decode_variable(eeprom_data, tlv_start + 4, tlv_len - 4))

            elif tlv_type == self.TLVINFO_CRC_32:
                decoded_data['crc-32'] = self.decode_int(eeprom_data, tlv_start)

            i += tlv_len + self.TLVINFO_TLV_HEADER

        return decoded_data
