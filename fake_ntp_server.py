#!/usr/bin/env python
from __future__ import print_function

import argparse
import socket
import struct
import time

class NTPShort(object):

    seconds = 0
    fraction = 0

    def __init__(self, seconds, fraction):
        self.seconds = long(seconds)
        self.fraction = long(fraction)

    @staticmethod
    def from_bytes(data):
        if len(data) != 4:
            raise ValueError('data must contain 8 bytes')
        seconds, fraction = struct.unpack(b'>HH', data)
        return NTPShort(seconds, fraction)

    @staticmethod
    def from_float(value):
        seconds = long(value)
        fraction = long(round( (value - seconds) * 0x10000 ))
        if fraction > 0xffffL:
            seconds += 1
            fraction = 0
        return NTPShort(seconds, fraction)

    def to_bytes(self):
        return struct.pack(b'>HH', self.seconds, self.fraction)

    def to_float(self):
        return self.seconds + float(self.fraction) / 65536.0

    def __repr__(self):
        return 'NTPShort({seconds}, {fraction})'.format(seconds=repr(self.seconds), fraction=repr(self.fraction))

    def __str__(self):
        return str(self.to_float())

NTPShort.ZERO = NTPShort(0, 0)


class NTPTimestamp(object):

    seconds = 0
    fraction = 0

    def __init__(self, seconds, fraction):
        self.seconds = long(seconds)
        self.fraction = long(fraction)

    @staticmethod
    def from_bytes(data):
        if len(data) != 8:
            raise ValueError('data must contain 8 bytes')
        seconds, fraction = struct.unpack(b'>II', data)
        return NTPTimestamp(seconds, fraction)

    @staticmethod
    def from_unix_timestamp(timestamp):
        seconds = long(timestamp)
        fraction = long(round( (timestamp - seconds) * 0x100000000L ))
        if fraction > 0xffffffffL:
            fraction = 0xffffffffL
        seconds += 0x83aa7e80L
        seconds = (seconds & 0xffffffffL)
        return NTPTimestamp(seconds, fraction)

    def to_bytes(self):
        return struct.pack(b'>II', self.seconds, self.fraction)

    def to_unix_timestamp(self):
        return self.seconds - 0x83aa7e80 + float(self.fraction) / 0x100000000

    def __repr__(self):
        return 'NTPTimestamp({seconds}, {fraction})'.format(seconds=repr(self.seconds), fraction=repr(self.fraction))

    def __str__(self):
        ts = self.to_unix_timestamp()
        secs = long(ts)
        frac = long(round( (ts - secs) * 1000000 ))
        if frac >= 1000000:
            secs += 1
            frac = 0
        return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(secs)) + '.{:06d}Z'.format(frac)

NTPTimestamp.ZERO = NTPTimestamp(0, 0)


class NTPPacket(object):

    leap_indicator = 0
    version = 3
    mode = 3
    stratum = 0
    poll = 0
    precision = 0
    root_delay = NTPShort.ZERO
    root_dispersion = NTPShort.ZERO
    reference_identifier = b"\x00\x00\x00\x00"
    reference_timestamp = NTPTimestamp.ZERO
    origin_timestamp = NTPTimestamp.ZERO
    receive_timestamp = NTPTimestamp.ZERO
    transmit_timestamp = NTPTimestamp.ZERO

    @staticmethod
    def from_bytes(data):
        if len(data) < 48 and len(data) != 68:
            raise ValueError('packet too short')
        packet = NTPPacket()
        (b1, packet.stratum, packet.poll, packet.precision) = struct.unpack(b'>BBbb', data[0:4])
        packet.leap_indicator = (b1 >> 6) & 0x3
        packet.version = (b1 >> 3) & 0x7
        packet.mode = b1 & 0x7
        packet.root_delay = NTPShort.from_bytes(data[4:8])
        packet.root_dispersion = NTPShort.from_bytes(data[8:12])
        packet.reference_identifier = data[12:16]
        packet.reference_timestamp = NTPTimestamp.from_bytes(data[16:24])
        packet.origin_timestamp = NTPTimestamp.from_bytes(data[24:32])
        packet.receive_timestamp = NTPTimestamp.from_bytes(data[32:40])
        packet.transmit_timestamp = NTPTimestamp.from_bytes(data[40:48])
        return packet

    def to_bytes(self):
        b1 = self.leap_indicator << 6 | self.version << 3 | self.mode
        data = struct.pack(b'>BBbb', b1, self.stratum, self.poll, self.precision)
        data += self.root_delay.to_bytes()
        data += self.root_dispersion.to_bytes()
        data += self.reference_identifier
        data += self.reference_timestamp.to_bytes()
        data += self.origin_timestamp.to_bytes()
        data += self.receive_timestamp.to_bytes()
        data += self.transmit_timestamp.to_bytes()
        return data

    def __repr__(self):
        fields = (
            'leap_indicator',
            'version',
            'mode',
            'stratum',
            'poll',
            'precision',
            'root_delay',
            'root_dispersion',
            'reference_identifier',
            'reference_timestamp',
            'origin_timestamp',
            'receive_timestamp',
            'transmit_timestamp',
            )
        return 'NTPPacket(' + ', '.join([ field + '=' + repr(getattr(self, field)) for field in fields ]) + ')'

def fake_server(address):

    s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind( (address, 123) )

    drift_start = time.time()
    speed = 0.9996

    while True:
        packet, source = s.recvfrom(100)
        print('Received {length} byte packet from {source}'.format(length=len(packet), source=source[0]))
        packet = NTPPacket.from_bytes(packet)

        if packet.version not in (3, 4):
            print('Unsupported NTP version.')
            continue

        if packet.mode != 3:
            print('Not a client request.')
            continue

        try:
            print('Client time:', packet.transmit_timestamp)
        except:
            pass
        time_since_start = time.time() - drift_start
        return_time = drift_start + time_since_start * speed
        #return_time = time.time()

        response = NTPPacket()
        response.version = packet.version
        response.mode = 4
        response.stratum = 1
        response.reference_identifier = b'XFAK'
        response.origin_timestamp = packet.transmit_timestamp
        response.reference_timestamp = NTPTimestamp.from_unix_timestamp(return_time)
        response.receive_timestamp = NTPTimestamp.from_unix_timestamp(return_time)
        response.transmit_timestamp = NTPTimestamp.from_unix_timestamp(return_time)

        response = response.to_bytes()
        s.sendto(response, source)

def parse_bind_addr(address):
    address = socket.getaddrinfo(address, 123, 0, 0, 0, socket.AI_NUMERICHOST)
    address = address[0]
    if address[0] == socket.AF_INET:
        return '::ffff:' + address[4][0]
    else:
        return address[4][0]

def parse_args():
    parser = argparse.ArgumentParser(description='Fake NTP server')
    parser.add_argument('--listen', type=parse_bind_addr, default='::')
    return parser.parse_args()

def main():
    args = parse_args()
    fake_server(args.listen)

if __name__ == '__main__':
    main()
