#!/usr/bin/env python3
import argparse
import logging
import os
import datetime
import json
import hashlib
import socket
import enum
import time
import webbrowser
import typing

import requests
import requests.adapters

__version__ = '1.0.0'


class FixedTimeoutAdapter(requests.adapters.HTTPAdapter):
    def send(self, *pargs, **kwargs):
        if kwargs['timeout'] is None:
            kwargs['timeout'] = 10
        return super(FixedTimeoutAdapter, self).send(*pargs, **kwargs)


class EnumFactory:
    @staticmethod
    def get_by_member_value(enum_class, value):
        for enum_member in enum_class:
            if enum_member.value == value:
                return enum_member


@enum.unique
class HatchingTriageSubmissionKind(enum.Enum):
    File = 'file'
    Url = 'url'
    Fetch = 'fetch'


@enum.unique
class HatchingTriageSubmissionStatus(enum.Enum):
    # A sample has been submitted and is queued for static analysis or the static analysis is in progress.
    Pending = 'pending'

    # The static analysis report is ready. The sample will remain in this status until a profile is selected.
    Static_analysis = 'static_analysis'

    # All parameters for sandbox analysis have been selected. The sample is scheduled for running on the sandbox.
    Scheduled = 'scheduled'

    # The sandbox has finished running the sample and the resulting metrics are being processed into reports.
    Processing = 'processing'

    # The sample is being run by the sandbox.
    Running = 'running'

    # The sample has reports that can be retrieved. This status is terminal.
    Reported = 'reported'

    # Analysis of the sample has failed. Any other status may transition into this status. This status is terminal.
    Failed = 'failed'


class HatchingSampleId:
    def __init__(self, value):
        self.value = value


class HatchingTriageSubmissionResponse:
    def __init__(
            self,
            hatching_id: HatchingSampleId,
            status: HatchingTriageSubmissionStatus,
            kind: HatchingTriageSubmissionKind,
            filename: str,
            private: bool,
            submitted: datetime.datetime,
    ):
        self.id = hatching_id
        self.status = status
        self.kind = kind
        self.filename = filename
        self.private = private
        self.submitted = submitted

    @staticmethod
    def from_response(j):
        return HatchingTriageSubmissionResponse(
            HatchingSampleId(j['id']),
            EnumFactory.get_by_member_value(HatchingTriageSubmissionStatus, j['status']),
            EnumFactory.get_by_member_value(HatchingTriageSubmissionKind, j['kind']),
            j['filename'],
            j['private'],
            datetime.datetime.strptime(j['submitted'], '%Y-%m-%dT%H:%M:%SZ')
        )

    def __repr__(self):
        return F'<HatchingTriageSubmissionResponse ' \
               F'id="{self.id}" ' \
               F'status={self.status.name} ' \
               F'kind={self.kind.name} ' \
               F'filename="{self.filename}" ' \
               F'private={self.private} ' \
               F'submitted="{self.submitted.strftime("%Y-%m-%d %H:%M:%S")}" ' \
               F'>'


class HatchingTriageException(Exception):
    pass


class FeedItem:
    def __init__(self, completed, filename, feed_id: HatchingSampleId, kind, private, status, submitted, tasks):
        self.completed = completed
        self.filename = filename
        self.id = feed_id
        self.kind = kind
        self.private = private
        self.status = status
        self.submitted = submitted
        self.tasks = tasks

    def __repr__(self):
        return F'<FeedItem {self.id.value}, {self.submitted.strftime("%Y-%m-%d %H:%M:%S")}: {self.filename}>'


class HatchingTriageApi:
    BASE_URL = 'https://api.tria.ge/v0'
    REPORT_BASE_URL = 'https://tria.ge'
    MAX_LIMIT = 200

    def __init__(self, user_agent: str, access_key: str):
        self.session = requests.session()
        self.session.mount('https://', FixedTimeoutAdapter())
        self.session.mount('http://', FixedTimeoutAdapter())
        self.session.headers = {
            'Authorization': F'Bearer {access_key}',
            'User-Agent': user_agent,
        }

    def detonate_file(self, file_content: bytes, interactive: bool = False) -> HatchingTriageSubmissionResponse:
        response = self.session.post(
            F'{self.BASE_URL}/samples',
            files={'file': file_content},
            data={'__json': json.dumps({
                'kind': HatchingTriageSubmissionKind.File.value,
                'interactive': interactive,
            })}
        )
        return HatchingTriageSubmissionResponse.from_response(response.json())

    def sample_status(self, sample_id: HatchingSampleId) -> HatchingTriageSubmissionResponse:
        return HatchingTriageSubmissionResponse.from_response(
            self.session.get(F'{self.BASE_URL}/samples/{sample_id.value}').json()
        )

    def get_triage_report_url(self, sample_id: HatchingSampleId) -> str:
        return F'{self.REPORT_BASE_URL}/{sample_id.value}'

    def feed(self, owned: bool = False, limit: int = MAX_LIMIT, use_pagination=False) -> typing.Iterable[FeedItem]:
        offset = None
        while True:
            params = {
                'subset': 'owned' if owned else 'public',
                'limit': limit,
            }
            if offset:
                params['offset'] = offset
            response = self.session.get(F'{self.BASE_URL}/samples', params=params)
            if response.status_code != 200:
                raise HatchingTriageException(F'Api-Exception: {response.content}')
            j = response.json()
            for row in j['data']:
                yield FeedItem(
                    datetime.datetime.strptime(row['completed'], '%Y-%m-%dT%H:%M:%SZ')
                    if 'completed' in row.keys() else None,
                    row['filename'] if 'filename' in row.keys() else None,
                    HatchingSampleId(row['id']),
                    row['kind'],
                    row['private'],
                    row['status'],
                    datetime.datetime.strptime(row['submitted'], '%Y-%m-%dT%H:%M:%SZ'),
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

    submit_parser = subparsers.add_parser('submit', help='Upload sample for detonation.')
    submit_parser.add_argument(
        'target',
        help='File on disk to detonate or URL on the internet to detonate or download and detonate'
    )
    kind_values = [kind.value for kind in HatchingTriageSubmissionKind]
    submit_parser.add_argument(
        '-k', '--kind',
        choices=kind_values,
        help=F'Possible values: {", ".join(kind_values)}',
        default=HatchingTriageSubmissionKind.File.value
    )
    submit_parser.add_argument('-i', '--interactive', help='File to be uploaded')
    submit_parser.add_argument(
        '-p', '--poll', action='store_true',
        help='If specified, the script will poll for the task to be finished.'
    )
    submit_parser.add_argument(
        '-b', '--browser', action='store_true',
        help='If specified (in combination with -p), the script will open a web browser when the task is done.'
    )
    submit_parser.add_argument(
        '--sleep-time', type=int, default=10,
        help='Specify the time in seconds to sleep between pools for status.'
    )

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
        if args.command == 'submit':
            kind = EnumFactory.get_by_member_value(HatchingTriageSubmissionKind, args.kind)
            if kind == HatchingTriageSubmissionKind.File:
                with open(args.target, 'rb') as fp:
                    content = fp.read()
                api_response = api.detonate_file(content)
            elif kind == HatchingTriageSubmissionKind.Url:
                raise NotImplementedError('submission kind "url" not implemented')
            elif kind == HatchingTriageSubmissionKind.Fetch:
                raise NotImplementedError('submission kind "fetch" not implemented')
            else:
                raise HatchingTriageException(F'Invalid kind: {args.kind} specified')
            if args.poll:
                while api_response.status not in [
                    HatchingTriageSubmissionStatus.Failed,
                    HatchingTriageSubmissionStatus.Reported,
                ]:
                    time.sleep(args.sleep_time)
                    api_response = api.sample_status(api_response.id)
                if api_response.status == HatchingTriageSubmissionStatus.Reported:
                    logger.info(F'Task with id {api_response.id.value} finished.')
                    if args.browser:
                        webbrowser.open(api.get_triage_report_url(api_response.id))
                else:
                    logger.error(F'Failed task: {api_response}')

        elif args.command == 'feed':
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
                    try:
                        report = api.report(feed_item.id)
                    except HatchingTriageException:
                        logger.error(F'Cannot retrieve report for {feed_item.id}, skipping.')
                        continue
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
