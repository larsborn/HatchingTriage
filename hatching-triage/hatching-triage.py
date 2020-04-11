#!/usr/bin/env python3
import argparse
import logging
import os
import datetime
import json
import hashlib
import socket

import requests
import requests.adapters

__version__ = '1.0.0'


class FixedTimeoutAdapter(requests.adapters.HTTPAdapter):
    def send(self, *pargs, **kwargs):
        if kwargs['timeout'] is None:
            kwargs['timeout'] = 10
        return super(FixedTimeoutAdapter, self).send(*pargs, **kwargs)


class HatchingTriageException(Exception):
    pass


class FeedItem:
    def __init__(self, completed, filename, id, kind, private, status, submitted, tasks):
        self.completed = completed
        self.filename = filename
        self.id = id
        self.kind = kind
        self.private = private
        self.status = status
        self.submitted = submitted
        self.tasks = tasks

    def __repr__(self):
        return F'<FeedItem {self.id}, {self.submitted.strftime("%Y-%m-%d %H:%M:%S")}: {self.filename}>'


class HatchingTriageApi:
    BASE_URL = 'https://api.tria.ge/v0'
    MAX_LIMIT = 200

    def __init__(self, user_agent: str, access_key: str):
        self.session = requests.session()
        self.session.mount('https://', FixedTimeoutAdapter())
        self.session.mount('http://', FixedTimeoutAdapter())
        self.session.headers = {
            'Authorization': F'Bearer {access_key}',
            'User-Agent': user_agent,
        }

    def feed(self, owned: bool = False, limit: int = MAX_LIMIT, use_pagination=False):
        offset = None
        while True:
            params = {
                'subset': 'owned' if owned else 'public',
                'limit': limit,
            }
            if offset:
                params['offset'] = offset
            response = self.session.get(
                F'{self.BASE_URL}/samples',
                params=params
            )
            if response.status_code != 200:
                raise HatchingTriageException(F'Api-Exception: {response.content}')
            j = response.json()
            for row in j['data']:
                yield FeedItem(
                    datetime.datetime.strptime(row['completed'], '%Y-%m-%dT%H:%M:%SZ')
                    if 'completed' in row.keys() else None,
                    row['filename'] if 'filename' in row.keys() else None,
                    row['id'],
                    row['kind'],
                    row['private'],
                    row['status'],
                    datetime.datetime.strptime(row['submitted'], '%Y-%m-%dT%H:%M:%S.%fZ'),
                    row['tasks'] if 'tasks' in row.keys() else None
                )
            if not use_pagination:
                break
            if 'next' not in j.keys():
                break
            offset = j['next']

    def report(self, sample_id):
        response = self.session.get(F'{self.BASE_URL}/samples/{sample_id}/reports/static')
        if response.status_code != 200:
            raise HatchingTriageException(F'Api-Exception: {response.content}')
        return response.json()

    def download(self, sample_id):
        response = self.session.get(F'{self.BASE_URL}/samples/{sample_id}/sample')
        if response.status_code != 200:
            raise HatchingTriageException(F'Api-Exception: {response.content}')
        return response.content


class ConsoleHandler(logging.Handler):
    def emit(self, record):
        print('[%s] %s' % (record.levelname, record.msg))


if __name__ == '__main__':
    import platform

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='command')

    feed_parser = subparsers.add_parser('feed', help='Retrieve the public feed of samples.')
    feed_parser.add_argument('-o', '--owned', action='store_true', help='Only show files owned by user.')

    download_parser = subparsers.add_parser('report', help='Download data.')
    download_parser.add_argument('report_id', help='Copy from URL for example')

    download_parser = subparsers.add_parser('download', help='Download data.')
    download_parser.add_argument('report_id', help='Copy from URL for example')

    scrape_parser = subparsers.add_parser('scrape', help='Download samples.')
    scrape_parser.add_argument('target_dir')
    scrape_parser.add_argument('--max-new-sample-count', default=10, type=int)
    scrape_parser.add_argument('--ignore-last-scrape-date', action='store_true')

    parser.add_argument('--access-key', default=os.getenv('HATCHING_TRIAGE_ACCESS_KEY', None))
    parser.add_argument('--debug', action='store_true')
    parser.add_argument(
        '--user-agent',
        default=F'HatchingTriageClient/{__version__} (python-requests {requests.__version__}) '
                F'{platform.system()} ({platform.release()})'
    )
    args = parser.parse_args()

    logger = logging.getLogger('HatchingTriageClient')
    logger.handlers.append(ConsoleHandler())
    logger.setLevel(logging.DEBUG if args.debug else logging.INFO)

    logger.debug(F'Using User-Agent string: {args.user_agent}')
    api = HatchingTriageApi(args.user_agent, args.access_key)
    try:
        if args.command == 'feed':
            for feed_item in api.feed(args.owned):
                print(feed_item)

        elif args.command == 'report':
            print(json.dumps(api.report(args.report_id)))

        elif args.command == 'download':
            sample_content = api.download(args.report_id)
            file_name = hashlib.sha256(sample_content).hexdigest()
            logger.info(F'Writing {len(sample_content)} bytes to "{file_name}"...')
            with open(file_name, 'wb') as fp:
                fp.write(sample_content)

        elif args.command == 'scrape':

            # make sure, directories exist
            target_dir = args.target_dir
            if not os.path.exists(target_dir) or not os.path.isdir(target_dir):
                raise HatchingTriageException(F'target dir "{target_dir}" does not exist')
            report_dir = os.path.join(target_dir, 'reports')
            if not os.path.exists(report_dir):
                os.mkdir(report_dir)
            sample_dir = os.path.join(target_dir, 'samples')
            if not os.path.exists(sample_dir):
                os.mkdir(sample_dir)
            state_file = os.path.join(target_dir, 'state.json')
            if os.path.exists(state_file):
                with open(state_file, 'r') as fp:
                    state = json.load(fp)
                last_scrape = datetime.datetime.strptime(state['last_scrape'], '%Y-%m-%dT%H:%M:%SZ')
            else:
                last_scrape = datetime.datetime(1900, 1, 1, 0, 0, 0)

            # loop over all data from feed
            this_scrape = datetime.datetime.now()
            new_samples = 0
            for i, feed_item in enumerate(api.feed(use_pagination=True)):
                if i and not i % 100:
                    logger.debug(F'Processed {i} reports')

                # get report, either from API or local file system, cache on disk if from API
                report_file_name = os.path.join(report_dir, F'{feed_item.id}.json')
                if os.path.exists(report_file_name):
                    with open(report_file_name, 'r') as fp:
                        report = json.load(fp)
                else:
                    report = api.report(feed_item.id)
                    with open(report_file_name, 'w') as fp:
                        json.dump(report, fp)

                # stop processing if report is older than last scrape
                if 'reported' in report['analysis'].keys():
                    reported_timestamp = datetime.datetime.strptime(
                        report['analysis']['reported'],
                        '%Y-%m-%dT%H:%M:%SZ'
                    )
                    if reported_timestamp < last_scrape and not args.ignore_last_scrape_date:
                        break

                # download sample
                if feed_item.kind == 'file':
                    files = [file for file in report['files'] if file['depth'] == 0]
                    if len(files) != 1:
                        raise HatchingTriageException()
                    file = files[0]
                    sample_file_name = os.path.join(sample_dir, file['sha256'])
                    if not os.path.exists(sample_file_name):
                        sample_content = api.download(report['sample']['sample'])
                        logger.debug(F'Writing {len(sample_content)} bytes to "{sample_file_name}"...')
                        with open(sample_file_name, 'wb') as fp:
                            fp.write(sample_content)
                        new_samples += 1

                elif feed_item.kind == 'url':
                    # don't do anything with URLs
                    pass
                else:
                    raise HatchingTriageException(F'Unknown feed item type: {feed_item.kind}')

                if new_samples >= args.max_new_sample_count:
                    break

            logger.debug(F'{new_samples} new sample(s) found.')
            # persist last scrape to avoid re-processing on next call
            with open(state_file, 'w') as fp:
                json.dump({'last_scrape': this_scrape.strftime('%Y-%m-%dT%H:%M:%SZ')}, fp)

    except HatchingTriageException as e:
        logger.exception(e)
    except socket.timeout as e:
        logger.exception(e)
