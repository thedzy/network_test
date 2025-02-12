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
import pprint
import subprocess
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.widgets import MultiCursor


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


def main() -> None:
    logger.info('Start')

    window_open = True

    def window_close(event) -> None:
        """
        Triggered when Matplotlib window is closed.
        """
        nonlocal window_open
        window_open = False

    data_points = options.data_points

    il_h2_req_resp = [0] * data_points
    il_tcp_handshake_443 = [0] * data_points
    il_tls_handshake = [0] * data_points
    base_rtt = [0] * data_points

    fig, axs = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
    fig.canvas.manager.set_window_title('Network Quality')
    fig.canvas.mpl_connect('close_event', window_close)
    fig.suptitle('Network Quality Metrics', fontsize=14)
    info_text = fig.text(0.5, 0.01, '', ha='center', fontsize=10, bbox=dict(facecolor='white', alpha=0.5))

    axs = axs.flatten()

    # MultiCursor(fig.canvas, axs, color='r', lw=2)

    plt.ion()

    logger.info('Ctrl-C to stop, or close the window')
    while window_open:
        try:
            data = network_quality()
            logger.debug(pprint.pformat(data))

            # Keep only the last x data points
            for i in range(0, len(data['il_h2_req_resp'])):
                il_h2_req_resp.append(data['il_h2_req_resp'][i])
                il_tcp_handshake_443.append(data['il_tcp_handshake_443'][i])
                il_tls_handshake.append(data['il_tls_handshake'][i])
                base_rtt.append(data['base_rtt'])

            il_h2_req_resp = il_h2_req_resp[-data_points:]
            il_tcp_handshake_443 = il_tcp_handshake_443[-data_points:]
            il_tls_handshake = il_tls_handshake[-data_points:]
            base_rtt = base_rtt[-data_points:]

            graphs = (
                (il_h2_req_resp, 'HTTP/2 Request-Response'),
                (il_tcp_handshake_443, 'TLS Handshake'),
                (il_tls_handshake, 'TCP Handshake'),
                (base_rtt, 'Base Round Trip Time')
            )

            # Keep graphs at same scale
            # min_y = min(min(il_h2_req_resp), min(il_tcp_handshake_443), min(il_tls_handshake), min(base_rtt))
            max_y = max(max(il_h2_req_resp), max(il_tcp_handshake_443), max(il_tls_handshake), max(base_rtt))

            for index, graph in enumerate(graphs):
                axs[index].cla()
                axs[index].plot(graph[0], label='Latency')
                axs[index].set_title(graph[1])
                axs[index].legend()
                axs[index].set_ylim(0, max_y)

            interface = data['interface_name']
            server = data['test_endpoint']

            # Update info text
            info_text.set_text(f'Interface: {interface} | Server: {server}')

            plt.pause(2.0)
            fig.canvas.flush_events()
        except KeyboardInterrupt:
            plt.close()
            break

    plt.ioff()
    plt.show()
    logger.info('\nDone')


def network_quality(binary: str = '/usr/bin/networkQuality', download=False, upload=False, cert_validation=True) -> dict:
    """
    Use Apples NetworkQuality to measure connection
    :param binary: Binary
    :param download: Perform teh download test, no just latency
    :param upload: Perform teh upload test, not just latency
    :param cert_validation: Validate certs
    :return:  return time, successful, time of test
    """
    command = [binary, '-c']
    if download is False:
        command.append('-d')
    if upload is False:
        command.append('-u')
    if cert_validation is False:
        command.append('-k')

    process = subprocess.run(command, universal_newlines=True, stdout=subprocess.PIPE)

    json_data = json.loads(process.stdout)
    return json_data


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

    parser.add_argument('-d', '--data-points', type=int, default=500,
                        action='store', dest='data_points',
                        help='how many data points to plot, default %(default)s')

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
