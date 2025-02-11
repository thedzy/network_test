#!/usr/bin/env python3

__author__ = 'thedzy'
__copyright__ = 'Copyright 2024, thedzy'
__license__ = 'GPL'
__version__ = '1.0'
__maintainer__ = 'thedzy'
__email__ = 'thedzy@hotmail.com'
__status__ = 'Development'
__date__ = '2025-02-07'
__description__ = \
    """
    ping_test.py: 
    Continuous network ping test
    """

import argparse
import json
import logging
import logging.config
import os
import pprint
import re
import socket
import struct
import time
from datetime import datetime
from io import StringIO
from pathlib import Path

import matplotlib.pyplot as plt
import requests


class ColourFormat(logging.Formatter):
    """
    Add colour to logging events
    """

    def __init__(self, fmt: str = None, datefmt: str = None, style: str = '%', levels={}) -> None:
        """
        Initialise the formatter
        ft: (str) Format String
        datefmt: (str) Date format
        style: (str) Format style
        levels: tuple, tuple (level number start, colour, attribute
        """
        self.levels = {}
        set_levels = {10: 90, 20: 92, 30: 93, 40: 91, 50: (41, 97)}
        set_levels.update(levels)

        for key in sorted(set_levels.keys()):
            value = set_levels[key]
            colour = str(value) if isinstance(value, (str, int)) else ';'.join(map(str, value))

            self.levels[key] = f'\x1b[5;{colour};m'

        super().__init__(fmt, datefmt, style)

    def formatMessage(self, record: logging.LogRecord, **kwargs: dict) -> str:
        """
        Override the formatMessage method to add colour
        """
        no_colour = u'\x1b[0m'
        for level in self.levels:
            colour = self.levels[level] if record.levelno >= level else colour

        return f'{colour}{super().formatMessage(record, **kwargs)}{no_colour}'


def main():
    logger.info('Start')

    if os.geteuid() != 0:
        logger.critical('Script requires root privileges')
        exit()

    # Append any hosts
    if len(options.hosts) > 0:
        hosts = []
        for hostnames in options.hosts:
            for hostname in hostnames:
                hosts.insert(0, hostname)
    else:
        # Get a list of public verified DNS
        csv_url = f'https://public-dns.info/nameserver/{options.region}.json'
        response = requests.get(csv_url)

        if response.status_code == 200:
            json_data = json.load(StringIO(response.text))
        else:
            logger.critical(f'Failed to fetch CSV. Status code: {response.status_code}')
            logger.critical(f'Check https://public-dns.info/nameserver/{options.region}.json')
            exit()

        # Convert checked_at to datetime before sorting
        for item in json_data:
            item['checked_at'] = datetime.strptime(item['checked_at'].rstrip('Z'), '%Y-%m-%dT%H:%M:%S.%f')

        # Filter for relaibility
        json_data = sorted(json_data, key=lambda x: (x['reliability'], x['checked_at']), reverse=True)
        if options.reliability is not None:
            json_data = [record for record in json_data if record['reliability'] >= options.reliability]
        if options.top_dns is not None:
            json_data = json_data[0:options.top_dns]

        # Filter for IPv4
        hosts = [dns_server['ip'] for dns_server in json_data if re.match(r'(\d+\.){3}\d+', dns_server['ip'])]

    logger.debug(pprint.pformat(hosts))

    return_times, times, failure_flags, hostnames = [], [], [], []

    # Start a chart/plot
    plt.ion()
    fig, ax = plt.subplots()

    while True:
        host = hosts.pop()
        hosts.insert(0, host)

        if options.dns_lookup:
            return_time, success, now = dns_test(host=host, timeout=options.default_timeout)
        else:
            return_time, success, now = ping_test(host=host, timeout=options.default_timeout)

        if options.filter_failed and not success:
            logger.debug(f'Filtered host: {hostname} for failure')
            hosts.remove(host)
        if options.filter_long is not None and return_time > options.filter_long:
            logger.debug(f'Filtered long host: {hostname} for {return_time:0.0f} > {options.filter_long}')
            hosts.remove(host)

        if len(hosts) == 0:
            logger.critical(f'All hosts filtered')
            exit()

        if not success:
            try:
                return_time = max(return_times)
            except ValueError:
                pass

        logger.debug(f'{host:16} {return_time:9.2f} {success}')

        return_times.append(return_time)
        times.append(now)
        failure_flags.append(success)
        hostnames.append(host)

        # Keep only the last x data points
        return_times = return_times[-options.data_points:]
        times = times[-options.data_points:]
        failure_flags = failure_flags[-options.data_points:]
        hostnames = hostnames[-options.data_points:]

        width = 1 if len(times) < 1 else (max(times) - min(times)) / options.data_points

        ax.clear()
        colours = ['blue' if failure else 'red' for failure in failure_flags]
        bars = ax.bar(times, return_times, width=width, label='Ping Time', color=colours)
        for bar, hostname in zip(bars, hostnames):
            ax.text(bar.get_x() + bar.get_width() / 2, 0, f' {hostname} ', ha='center', va='bottom', fontsize=10,
                    color='white', rotation=90)

        ax.set_xlabel('Date/Time')
        ax.set_ylabel('Time (ms)')
        ax.set_title('Ping Time Times')
        ax.legend()
        plt.xticks(rotation=45)
        plt.pause(1)
    plt.ioff()
    plt.show()

    logger.info('Done')


def compute_checksum(packet: bytes):
    """
    Compute the Internet Checksum (16-bit one's complement sum) for a given packet.
    :param packet: (bytes or bytearray): The packet data to compute the checksum for.
    :returns:int: The 16-bit checksum (unsigned).
    """
    s = 0
    for i in range(0, len(packet), 2):
        s += (packet[i] << 8) + (packet[i + 1] if i + 1 < len(packet) else 0)
    s = (s >> 16) + (s & 0xffff)
    s = (s >> 16) + s
    return ~s & 0xffff


def ping_test(host: str, timeout: float = 1) -> (float, bool, datetime):
    """
    Send an ICMP packet and measure its return time
    :param host: Hostname/ip
    :param timeout: How long before we consider it a timeout
    :return:  return time, successful, time of test
    """
    now = datetime.now()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        sock.settimeout(timeout)

        packet_id = os.getpid() & 0xFFFF
        header = struct.pack('!BBHHH', 8, 0, 0, packet_id, 1)
        payload = b'ping'
        packet = header + payload

        checksum = compute_checksum(packet)
        header = struct.pack('!BBHHH', 8, 0, checksum, packet_id, 1)
        packet = header + payload

        start_time = time.perf_counter()
        sock.sendto(packet, (host, 1))
        sock.recvfrom(1024)
        end_time = time.perf_counter()

        return (end_time - start_time) * 1000, True, now
    except socket.timeout:
        return -1, False, now
    except Exception as e:
        print(f"Error: {e}")
        return -1, False, now


def dns_test(host: str, hostname: str = 'google.com', timeout: float = 1) -> (float, bool, datetime):
    """
    Perform a raw DNS query to a specified DNS server using Python's built-in socket module.

    :param hostname: The domain name to query.
    :param dns_server: The IP address of the DNS server to use (default: 8.8.8.8).
    :param timeout: Timeout in seconds.
    :return: Resolved IP address or None if the query fails.
    """
    now = datetime.now()

    # Set up a UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)

    # DNS header
    transaction_id = 0xAAAA  # Random ID
    flags = 0x0100  # Standard query
    questions = 1
    header = struct.pack('!HHHHHH', transaction_id, flags, questions, 0, 0, 0)

    # DNS question section
    qname = b''.join(bytes([len(part)]) + part.encode() for part in hostname.split('.')) + b'\x00'
    qtype = 1  # A record
    qclass = 1  # IN (Internet)
    question = qname + struct.pack('!HH', qtype, qclass)

    # Send the query
    message = header + question
    server_address = (host, 53)

    try:
        start_time = time.perf_counter()

        sock.sendto(message, server_address)
        data, _ = sock.recvfrom(512)  # Receive response
        end_time = time.perf_counter()

        return (end_time - start_time) * 1000, True, now
    except socket.timeout:
        return - 1, False, now
    except Exception as e:
        return -1, False, now
    finally:
        sock.close()


def create_logger(name: str = __file__, levels: dict = {}) -> logging.Logger:
    """
    Create a logger
    :param name: (str) Logging name
    :param levels: (dict) Custom logging levels
    :return: Logging instance
    """

    def make_log_level(level_name: str, level_int: int) -> None:
        logging.addLevelName(level_int, level_name.upper())
        setattr(new_logger, level_name, lambda *args: new_logger.log(level_int, *args))

    new_logger = logging.getLogger(name)

    logging_config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'stderr': {
                '()': ColourFormat,
                'style': '{', 'format': '{message}',
            },
            'file': {
                'style': '{', 'format': '[{asctime}] [{levelname:8}] {message}'
            }
        },
        'handlers': {
            'stderr': {
                'class': 'logging.StreamHandler',
                'formatter': 'stderr',
                'stream': 'ext://sys.stderr',
            },
            'file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'formatter': 'file',
                'filename': options.log_file if options.log_file else '/dev/null',
                'maxBytes': 1024 * 1
                ,
                'backupCount': 0
            }
        },
        'loggers': {
            'root': {
                'handlers': [
                    'stderr'
                ]
            },
            name: {
                'level': 10 if options.debug else 20,
                'handlers': [
                    'stderr'
                ]
            }
        }
    }

    if options.log_file is not None:
        logging_config['loggers'][name]['handlers'].append('file')

    logging.config.dictConfig(logging_config)

    # Create custom levels
    for level in levels.items():
        make_log_level(*level)

    return new_logger


if __name__ == '__main__':
    def valid_path(path):
        parent = Path(path).parent
        if not parent.is_dir():
            print(f'{parent} is not a directory, make it?', end=' ')
            if input('y/n: ').lower()[0] == 'y':
                parent.mkdir(parents=True, exist_ok=True)
                return Path(path)
            raise argparse.ArgumentTypeError(f'{path} is an invalid path')
        return Path(path)


    # Create argument parser
    parser = argparse.ArgumentParser(description=__description__)

    parser.add_argument('-r', '--region', default='us',
                        action='store', dest='region',
                        help='country/region, ex ca, us, ie')

    quality = parser.add_mutually_exclusive_group()
    quality.add_argument('-R', '--reliability', type=float, default=None,
                         action='store', dest='reliability',
                         help='reliability rating of x or higher 0.000-1.000')
    quality.add_argument('-T', '--top', type=int, default=None,
                         action='store', dest='top_dns',
                         help='top x for reliability')

    parser.add_argument('-d', '--data-points', type=int, default=60,
                        action='store', dest='data_points',
                        help='how many data points to plot')

    parser.add_argument('-t', '--timeout', type=float, default=0.95,
                        action='store', dest='default_timeout',
                        help='timeout length, default: %(default)s')

    parser.add_argument('--filter-long', type=int, default=None,
                        action='store', dest='filter_long',
                        help='don\'t reuse servers with pings greater than x')

    parser.add_argument('--filter-failures', default=False,
                        action='store_true', dest='filter_failed',
                        help='don\'t reuse servers that failed')

    parser.add_argument('-H', '--host', default=[], nargs=argparse.ONE_OR_MORE,
                        action='append', dest='hosts',
                        metavar='HOST(s)',
                        help='custom hosts')

    # Test type
    test_type = parser.add_mutually_exclusive_group()
    test_type.add_argument('--dns-lookup', default=False,
                           action='store_true', dest='dns_lookup',
                           help='dns lookup, for the test')
    test_type.add_argument('--ping', default=False,
                           action='store_false', dest='dns_lookup',
                           help='ping, for the test')

    # Debug/verbosity option
    parser.add_argument('--debug', default=False,
                        action='store_true', dest='debug',
                        help=argparse.SUPPRESS)

    # Output
    parser.add_argument('--log', type=valid_path,
                        default=None,
                        action='store', dest='log_file',
                        help='output log')

    options = parser.parse_args()

    logger = create_logger()
    logger.debug('Debug ON')
    logger.debug(pprint.pformat(options))

    main()
