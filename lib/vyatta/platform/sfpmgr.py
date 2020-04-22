# Copyright (c) 2019, AT&T Intellectual Property.  All rights reserved.
#
# SPDX-License-Identifier: LGPL-2.1-only

import zmq
import json
import select
import os
import base64
from vyatta.platform.basesfphelper import SfpHelperException
from vyatta.platform.basesfphelper import ModuleNotPresentException

class SfpState:
    def __init__(self, porttype, port, extra_state):
        if extra_state:
            self.state = extra_state
        else:
            self.state = {}
        self.state['type'] = porttype
        self.state['port'] = port

class SfpStateManager(object):
    '''
    SFP State Manager

    Keeps track of SFP state and notifies interested parties of
    changes via ZMQ, and allows those parties to also enact changes to
    the state of SFPs.
    '''
    def __init__(self, pub_endpoint, rep_endpoint, req_endpoint, sfphelper):
        self._ctx = zmq.Context.instance()
        self._ctx.IPV6 = 1
        self._ctx.LINGER = 0
        self.pub_socket = self._ctx.socket(zmq.PUB)
        self.pub_socket.bind(pub_endpoint)
        if pub_endpoint.startswith("ipc://"):
            # Make it user/group readable/writable so it's possible
            # for clients not running as the same user to use it
            os.chmod(pub_endpoint[6:], 0o770)
        self.rep_socket = self._ctx.socket(zmq.REP)
        self.rep_socket.bind(rep_endpoint)
        if rep_endpoint.startswith("ipc://"):
            # Make it user/group readable/writable so it's possible
            # for clients not running as the same user to use it
            os.chmod(rep_endpoint[6:], 0o770)
        self.sfp_state = {}
        self.sfphelper = sfphelper
        self._req_endpoint = req_endpoint

    def _dict_merge(self, a, b, path=None):
        '''
        Performs a deep merge of dictionary b into a
        '''
        if path is None: path = []
        for key in b:
            if key in a:
                if isinstance(a[key], dict) and isinstance(b[key], dict):
                    self._dict_merge(a[key], b[key], path + [str(key)])
                elif a[key] == b[key]:
                    pass # same leaf value
                else:
                    raise Exception(
                        'Conflict at %s' % '.'.join(path + [str(key)]))
            else:
                a[key] = b[key]
        return a

    def _serialise_sfp_state(self, portname, presence, sfp_state):
        '''
        Convert SFP state into a dictionary for encoding in JSON
        '''
        state = {
            'ports': {
                portname: {
                    'present': presence
                }
            }
        }
        state['ports'][portname].update(sfp_state.state)
        return state

    def _sfp_eeprom_get_extra_state(self, port, sfp_state):
        try:
            content = self.sfphelper.read_eeprom('SFP', port, offset=0, length=128)
            eth_10g = content[3]
            eth_compat = content[6]
            eth_extended_comp = content[36]
            sfp_state['eeprom_eth_10g'] = eth_10g
            sfp_state['eeprom_eth_compat'] = eth_compat
            sfp_state['eeprom_eth_extended_comp'] = eth_extended_comp
        except SfpHelperException:
            # Module was removed in between notification it was
            # inserted and retrieval of information, or no EEPROM
            # information is present. Either way, to be expected so
            # eat the exception and return no extra state
            pass

    def _qsfp_eeprom_get_extra_state(self, port, sfp_state):
        try:
            content = self.sfphelper.read_eeprom('QSFP', port, offset=0, length=256)
            # SFF-8636 Extended Identifier
            sfp_state['rx_cdr_present'] = True if content[129] & 0x4 else False

            eth_1040100g = content[131]
            eth_extended_comp = content[192]
            sfp_state['eeprom_eth_1040100g'] = eth_1040100g
            # SFF_8636_EXT_COMPLIANCE
            if eth_1040100g & 0x80:
                sfp_state['eeprom_eth_extended_comp'] = eth_extended_comp
        except SfpHelperException:
            # Module was removed in between notification it was
            # inserted and retrieval of information, or no EEPROM
            # information is present. Either way, to be expected so
            # eat the exception and return no extra state
            pass

    def on_sfp_presence_change(self, portname, porttype, port, presence,
                               extra_state={}):
        '''
        Notifies the SFP manager that the presence of an SFP has
        changed

        portname should represent the name of the port in the system
        minus the dp<n> prefix. porttype should be either 'SFP' or
        'QSFP'.
        '''
        topic = "sfp"
        if not extra_state:
            if porttype == 'SFP':
                self._sfp_eeprom_get_extra_state(port, extra_state)
            elif porttype == 'QSFP':
                self._qsfp_eeprom_get_extra_state(port, extra_state)

        sfp_state = SfpState(porttype, port, extra_state)
        if presence:
            self.sfp_state[portname] = sfp_state
        elif portname in self.sfp_state:
            del self.sfp_state[portname]
        state = self._serialise_sfp_state(portname, presence,
                                          sfp_state)
        self.pub_socket.send_string(topic + ' ' + json.dumps(state))

    def _process_replay_command(self):
        '''
        Process a request for a replay of SFP state from a client
        '''
        all_sfp_state = {}
        for portname, sfp_state in self.sfp_state.items():
            self._dict_merge(all_sfp_state, self._serialise_sfp_state(
                portname, True, sfp_state))
        self.rep_socket.send_json(all_sfp_state)

    def _process_phylinkstatus_command(self):
        '''
        Process a request for the PHY link status from a client
        '''
        all_phylinkstatus_state = {}
        all_phylinkstatus_state['phy_links'] = {}
        for portname, sfp_state in self.sfp_state.items():
            if self.sfphelper:
                (link, speed, duplex) = self.sfphelper.get_phy_link_status(
                    sfp_state.state['type'], sfp_state.state['port'])
                phy_link_dict = {}
                phy_link_dict['link'] = link
                phy_link_dict['speed'] = speed
                phy_link_dict['duplex'] = duplex
                all_phylinkstatus_state['phy_links'][portname] = phy_link_dict
        self.rep_socket.send_json(all_phylinkstatus_state)

    def _process_physpeedduplexset_command(self, json):
        speed = json['speed']
        duplex = json['duplex']
        portname = json['portname']
        if not portname in self.sfp_state:
            self.rep_socket.send_json({ 'result': 'SFP not present'})
            return

        sfp_state = self.sfp_state[portname]
        porttype = sfp_state.state['type']
        port = sfp_state.state['port']

        self.sfphelper.set_phy_speed_duplex(porttype, port, speed, duplex)
        self.rep_socket.send_json({ 'result': 'OK' })

    def _process_phyautonegset_command(self, json):
        portname = json['portname']
        if not portname in self.sfp_state:
            self.rep_socket.send_json({ 'result': 'SFP not present'})
            return

        sfp_state = self.sfp_state[portname]
        porttype = sfp_state.state['type']
        port = sfp_state.state['port']

        self.sfphelper.set_phy_autoneg(porttype, port)
        self.rep_socket.send_json({ 'result': 'OK' })

    def _process_sfpstateset_command(self, json):
        portname = json['portname']
        enabled = json['enabled']

        try:
            self.sfphelper.set_sfp_state(portname, enabled)
        except ModuleNotPresentException:
            # The module not being present is fine. The client is
            # expected to replay the SFP state set command when a
            # module is inserted, since this is needed for vyatta-sfpd
            # restart support anyway.
            pass
        self.rep_socket.send_json({ 'result': 'OK' })

    def _process_sfpreadeeprom_command(self, json):
        portname = json['portname']
        offset = None
        length = None
        if 'offset' in json:
            offset = int(json['offset'])
        if 'length' in json:
            length = int(json['length'])

        if not portname in self.sfp_state:
            self.rep_socket.send_json({ 'result': 'SFP not present'})
            return

        sfp_state = self.sfp_state[portname]
        porttype = sfp_state.state['type']
        port = sfp_state.state['port']

        data = self.sfphelper.read_eeprom(porttype, port, offset, length)
        self.rep_socket.send_json({ 'result': 'OK',
                                    'data': base64.b64encode(data).decode() })

    def _process_sfpqueryeeprom_command(self, json):
        portname = json['portname']
        if not portname in self.sfp_state:
            self.rep_socket.send_json({ 'result': 'SFP not present'})
            return

        sfp_state = self.sfp_state[portname]
        porttype = sfp_state.state['type']
        port = sfp_state.state['port']

        pages = self.sfphelper.query_eeprom(porttype, port)
        self.rep_socket.send_json({ 'result': 'OK',
                                    'porttype': porttype,
                                    'pages': pages })

    def _process_sfpinsertedremoved_command(self, json):
        portname = json['portname']
        portid = json['portid']
        inserted = json['inserted']

        success = self.sfphelper.process_sfpinsertedremoved(portname, int(portid),
                                                            inserted)
        if success:
            self.rep_socket.send_json({ 'result': 'OK' })
        else:
            self.rep_socket.send_json({ 'result': 'FAILED' })

    def process_rep_socket(self):
        '''
        Process a message becoming available on the REP socket
        '''
        eventProcessed = False
        while self.rep_socket.getsockopt(zmq.EVENTS) & zmq.POLLIN:
            try:
                json = self.rep_socket.recv_json()
                if json is None or not "command" in json:
                    self.rep_socket.send_json({ 'result': 'bad command' })
                    continue
                command = json["command"]
                if command == 'REPLAY':
                    self._process_replay_command()
                elif command == 'PHYLINKSTATUS':
                    self._process_phylinkstatus_command()
                elif command == 'PHYSPEEDDUPLEXSET':
                    self._process_physpeedduplexset_command(json)
                elif command == 'PHYAUTONEGSET':
                    self._process_phyautonegset_command(json)
                elif command == 'SFPSTATESET':
                    self._process_sfpstateset_command(json)
                elif command == 'SFPREADEEPROM':
                    self._process_sfpreadeeprom_command(json)
                elif command == 'SFPQUERYEEPROM':
                    self._process_sfpqueryeeprom_command(json)
                elif command == 'SFPINSERTEDREMOVED':
                    self._process_sfpinsertedremoved_command(json)
                else:
                    self.rep_socket.send_json(
                        { 'result': 'unrecognised command {}'.format(command) })
                    continue
                eventProcessed = True
            except Exception as e:
                self.rep_socket.send_json({ 'result': str(e) })
        return eventProcessed

    def get_rep_socket_fd(self):
        '''
        Get the REP socket
        '''
        return self.rep_socket.get(zmq.FD)

    def get_req_socket(self):
        '''
        Get the REP socket
        '''
        return self._ctx.socket(zmq.REQ)

    def get_req_socket_endpoint(self):
        '''
        Get the REP socket
        '''
        return self._req_endpoint

def main():
    '''
    Standalone test for the class
    '''

    PUB_ENDPOINT = "ipc:///tmp/sfp_pub.socket"
    REQ_ENDPOINT = "ipc:///tmp/sfp_req.socket"
    pub_endpoint = PUB_ENDPOINT
    req_endpoint = REQ_ENDPOINT

    sfpmgr = SfpStateManager(PUB_ENDPOINT, REQ_ENDPOINT, None)

    context = zmq.Context()
    sub_sock = context.socket(zmq.SUB)
    sub_sock.connect(pub_endpoint)
    sub_sock.setsockopt_string(zmq.SUBSCRIBE, "sfp")
    req_sock = context.socket(zmq.REQ)
    req_sock.connect(req_endpoint)
    p = select.poll()
    p.register(sfpmgr.get_rep_socket_fd(), select.POLLIN)

    # Test REPLAY command with empty state

    replay_req_json = { 'command': 'REPLAY' }
    req_sock.send_json(replay_req_json)

    while not sfpmgr.process_rep_socket():
        p.poll()

    replay_rep_json = req_sock.recv_json()
    assert('ports' not in replay_rep_json)

    # Test insert of two ports

    sfpmgr.on_sfp_presence_change('xe17', 'SFP', 17, True)
    # Receive message, strip out topic string and convert to JSON
    pub_json = json.loads(sub_sock.recv_string().split(' ', maxsplit=1)[1])
    assert(len(pub_json['ports'].keys()) == 1)
    assert(pub_json['ports']['xe17']['present'] == True)
    sfpmgr.on_sfp_presence_change('xe19', 'SFP', 19, True)
    # Receive message, strip out topic string and convert to JSON
    pub_json = json.loads(sub_sock.recv_string().split(' ', maxsplit=1)[1])
    assert(len(pub_json['ports'].keys()) == 1)
    assert(pub_json['ports']['xe19']['present'] == True)

    # Test REPLAY command with non-empty state

    replay_req_json = { 'command': 'REPLAY' }
    req_sock.send_json(replay_req_json)

    while not sfpmgr.process_rep_socket():
        p.poll()

    replay_rep_json = req_sock.recv_json()
    assert(len(replay_rep_json['ports'].keys()) == 2)
    assert(replay_rep_json['ports']['xe17']['present'] == True)
    assert(replay_rep_json['ports']['xe19']['present'] == True)

    # Test remove of two ports

    sfpmgr.on_sfp_presence_change('xe17', 'SFP', 17, False)
    # Receive message, strip out topic string and convert to JSON
    pub_json = json.loads(sub_sock.recv_string().split(' ', maxsplit=1)[1])
    assert(len(pub_json['ports'].keys()) == 1)
    assert(pub_json['ports']['xe17']['present'] == False)
    sfpmgr.on_sfp_presence_change('xe19', 'SFP', 19, False)
    # Receive message, strip out topic string and convert to JSON
    pub_json = json.loads(sub_sock.recv_string().split(' ', maxsplit=1)[1])
    assert(len(pub_json['ports'].keys()) == 1)
    assert(pub_json['ports']['xe19']['present'] == False)

    # Test REPLAY command back to empty state

    replay_req_json = { 'command': 'REPLAY' }
    req_sock.send_json(replay_req_json)

    while not sfpmgr.process_rep_socket():
        p.poll()

    replay_rep_json = req_sock.recv_json()
    assert('ports' not in replay_rep_json)

if __name__ == "__main__":
    main()
