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
    netwrok_test.py: 
    Continuous network test
    """

import argparse
import collections
import csv
import logging
import logging.config
import pprint
import re
import socket
import threading
import time
from datetime import datetime
from io import StringIO
from pathlib import Path

import matplotlib.pyplot as plt
import requests


class ThreadManager:
    """Class to manage threading, getting its results and tracking if it's been handled.
    V3
    """

    def __init__(self, semaphores=25, limit=0, seconds=0, minutes=0, hours=0):
        """
        Initialisation
        """
        # Set rate limits
        try:
            self.rate = (seconds + (minutes * 60) + (hours * 60 * 60)) / limit
        except ZeroDivisionError:
            self.rate = 0
        self._semaphores = threading.Semaphore(semaphores)
        self._queued = collections.deque()
        self._threads = collections.deque()
        self._completed_threads = collections.deque()

        self.started = False

    def __del__(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.__del__()

    def append(self, func: callable, *args, **kwargs) -> None:
        """
        Create a new thread by appending it to the threads to be processed
        :param func: (func) Function
        :param args: (list) Arguments
        :param kwargs: (dict) Keywords
        :return: void
        """
        thread = self.ThreadFunction(target=func, args=args, kwargs=kwargs, semaphores=self._semaphores)
        thread.name = func.__name__

        # Queue the thread
        self._queued.append(thread)

        # Start the queue
        if not self.started:
            self.start_job()
            self.started = True

    def active_count(self, name=None) -> int:
        """
        Get remaining thread count
        :return: (int) Threads
        """
        return len([thread for thread in self._threads if thread.name == name or name is None]) + len(self._queued)

    def inactive_count(self) -> int:
        """
        Get remaining inactive thread count, threads that are done and need values returned
        :return: (int) Threads
        """
        return len([thread for thread in self._threads if not thread.is_alive()])

    def get_threads(self) -> list:
        """
        Get all threads
        :return: (list) threading.Thread
        """
        return self._threads

    def abort(self) -> None:
        """
        Terminate all threads, send stop signal
        WARNING: This will not return the results of the threads
        WARNING: This can result in corrupted data
        :return: void
        """
        while len(self._threads) > 0:
            thread = self._threads.popleft()
            thread.stop()
            del thread

    def get_value(self) -> any:
        """
        Return the value of the first completed thread
        :return: (any) Return value
        """
        while True:
            if len(self._threads) > 0:
                thread = self._threads.popleft()
                if thread.is_alive():
                    self._threads.append(thread)
                else:
                    return thread.value()

    def start_job(self) -> None:
        """
        Start the next queued job
        :return: None
        """
        # Schedule the next execution
        if len(self._queued) > 0:
            thread = self._queued.popleft()
            thread.start()
            self._threads.append(thread)
        self.schedule_next_job()

    def schedule_next_job(self):
        """
        Start a timer for the next job to start
        :return: (any) Return value
        """
        if self.active_count() > 0:
            threading.Timer(self.rate, self.start_job).start()

    class ThreadFunction(threading.Thread):
        def __init__(self, group=None, target=None, name=None, args=(), kwargs=None, *, daemon=None, semaphores=None):
            """
            Initialisation
            """
            self.semaphores = semaphores
            if 'semaphores' in kwargs:
                del kwargs['semaphores']

            self.event = threading.Event()

            threading.Thread.__init__(self, group, target, name, args, kwargs, daemon=daemon)

            self._return = None

        def __del__(self):
            self.semaphores.release()
            pass

        def run(self) -> threading.Thread:
            """
            Override the run to get the return value
            :return:
            """
            self.semaphores.acquire()
            self._return = self._target(*self._args, **self._kwargs)
            return self

        def stop(self) -> None:
            """
            Stop thread
            :return: None
            """
            if self._tstate_lock is not None:
                self._tstate_lock.release()
            self._stop()
            self.semaphores.release()

        def value(self) -> any:
            """
            Get the results of the function
            :return:
            """
            threading.Thread.join(self)
            return self._return


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

    # Append any hosts
    if len(options.hosts) > 0:
        hosts = []
        for host in options.hosts:
            hostname, port, timeout = host
            hosts.insert(0, dict(host=hostname, port=int(port), timeout=int(timeout)))
    else:
        # Get a list of public verified DNS
        csv_url = 'https://public-dns.info/nameservers.csv'
        response = requests.get(csv_url)

        if response.status_code == 200:
            csv_data = StringIO(response.text)
            csv_reader = csv.DictReader(csv_data)
        else:
            logger.critical(f'Failed to fetch CSV. Status code: {response.status_code}')
            exit()

        # Filter for IPv4
        hosts = [dict(host=dns_server['ip_address'], port=53, timeout=10) for dns_server in csv_reader if
                 re.match(r'(\d+\.){3}\d+', dns_server['ip_address'])]

    send_times = []
    receive_times = []
    host_labels = []
    times = []

    plt.ion()
    fig, ax = plt.subplots()

    with ThreadManager(semaphores=10, limit=60, minutes=1) as thread_manager:
        # Create process threads
        for host in range(len(hosts)):
            # Append the function to the queue
            host = hosts.pop(0)
            thread_manager.append(check_connectivity, host=host['host'], port=host['port'], timeout=host['timeout'])

        # While the queue is not empty
        total_time = 0
        while thread_manager.active_count() > 0:
            # Get one value at a time
            hostname, port, timeout, send, receive, now = thread_manager.get_value()
            thread_manager.append(check_connectivity, host=hostname, port=port, timeout=timeout)

            logger.debug(f'{hostname:16} {host["port"]:4d} {send:0.3f} {receive:0.3f}')

            send_times.append(send)
            receive_times.append(receive)
            host_labels.append(hostname)
            times.append(now)

            # Keep only the last x data points
            send_times = send_times[-options.data_points:]
            receive_times = receive_times[-options.data_points:]
            host_labels = host_labels[-options.data_points:]
            times = times[-options.data_points:]

            ax.clear()
            ax.plot(times, send_times, marker='o', label='Send Time')
            ax.plot(times, receive_times, marker='s', label='Receive Time')
            ax.set_xlabel('Date/Time')
            ax.set_ylabel('Time (s)')
            ax.set_title('Network Connectivity Times')
            ax.legend()
            plt.xticks(rotation=45)
            plt.pause(1)
    plt.ioff()
    plt.show()

    logger.info('Done')


def check_connectivity(host, port=53, timeout=2):
    now = datetime.now()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)

            # Measure connection (sending) time
            start_connect = time.monotonic()
            s.connect((host, port))
            end_connect = time.monotonic()

            send_time = end_connect - start_connect

            # Measure receive time by sending and waiting for a response
            start_receive = time.monotonic()
            s.sendall(b'\x00')  # Send a minimal packet
            try:
                s.recv(1)  # Wait for a minimal response
            except socket.timeout:
                print('timeout')
                return host, port, timeout, 0, 0, now
            end_receive = time.monotonic()

            receive_time = end_receive - start_receive

            return host, port, timeout, send_time, receive_time, now
    except Exception as e:
        print(f"Error: {e}")
        return host, port, timeout, 0, 0, now


def create_logger(name: str = __file__, levels: dict = {}) -> logging.Logger:
    # Create log level
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

    parser.add_argument('-d', '--data-points', type=int, default=60,
                        action='store', dest='data_points',
                        help='how many data points')

    parser.add_argument('-H', '--host', nargs=3, default=[],
                        action='append', dest='hosts',
                        metavar=('HOST', 'PORT', 'TIMEOUT'),
                        help='custom hosts')

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
