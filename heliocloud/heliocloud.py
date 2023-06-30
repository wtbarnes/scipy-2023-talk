"""
This module provides a wrapper around the AWS S3 API.
"""

from datetime import datetime

import boto3
from botocore import UNSIGNED
from botocore.client import Config
from dateutil.rrule import DAILY, rrule

import astropy.table

import sunpy.net.attrs as a
from sunpy.net.attr import and_
from sunpy.net.base_client import BaseClient, QueryResponseTable
from sunpy.net.heliocloud.attrs import Dataset
from sunpy.net.heliocloud.walker import walker

__all__ = ['HelioCloudClient']

_HC_DATE_FMT = '%Y%m%d'
_HC_BASEURL = 'https://s3.amazonaws.com/gov-nasa-hdrl-data1/'

class HelioCloudClient(BaseClient):
    """
    Provides access to query and download from the HelioCloud S3 data storage.

    For now this only supports AIA files.

    Examples
    --------
    >>> import astropy.units as u
    >>> from sunpy.net import Fido, attrs as a
    >>> res = Fido.search(a.Time('2021/07/01', '2021/07/02'),
    ...                   a.heliocloud.Dataset('AIA'), a.Wavelength(171*u.AA)) # doctest: +REMOTE_DATA
    >>> res # doctest: +REMOTE_DATA
    <sunpy.net.fido_factory.UnifiedResponse object at ...>
    Results from 1 Provider:
    <BLANKLINE>
    361 Results from the HelioCloudClient:
    Source: HelioCloud AWS S3
    <BLANKLINE>
    Dataset      Start time
    ------- -------------------
        aia 2021-07-01 00:00:00
        aia 2021-07-01 00:04:00
        aia 2021-07-01 00:08:00
        aia 2021-07-01 00:12:00
        aia 2021-07-01 00:16:00
        aia 2021-07-01 00:20:00
        aia 2021-07-01 00:24:00
        aia 2021-07-01 00:28:00
        aia 2021-07-01 00:32:00
        aia 2021-07-01 00:36:00
        ...                 ...
        aia 2021-07-01 23:20:00
        aia 2021-07-01 23:24:00
        aia 2021-07-01 23:28:00
        aia 2021-07-01 23:32:00
        aia 2021-07-01 23:36:00
        aia 2021-07-01 23:40:00
        aia 2021-07-01 23:44:00
        aia 2021-07-01 23:48:00
        aia 2021-07-01 23:52:00
        aia 2021-07-01 23:56:00
        aia 2021-07-02 00:00:00
    Length = 361 rows
    <BLANKLINE>
    <BLANKLINE>
    """
    @property
    def info_url(self):
        return 'HelioCloud AWS S3'

    def search(self, *query, **kwargs):
        """
        Search for datasets provided by the Space Physics Data Facility.
        """
        query = and_(*query)
        queries = walker.create(query)
        results = []
        for query_parameters in queries:
            results.append(self._do_search(query_parameters))
        table = astropy.table.vstack(results)
        qrt = QueryResponseTable(table, client=self)
        qrt.hide_keys = ["URL"]
        return qrt

    def _do_search(self, query):
        response, urls = self._get_remote_files(query['dataset'],
                                          query['wavelength'],
                                          query['begin_time'],
                                          query['end_time'])
        fmt_string = f"sdo_{query['dataset']}_h2_%Y%m%dT%H%M%S_{query['wavelength']:04}_v1.fits"
        start_times = [datetime.strptime(f["Key"].split("/")[-1], fmt_string) for f in response]
        results_table = astropy.table.QTable(
            {'Dataset': [query['dataset']] * len(start_times),
             'Start time': start_times,
             'URL': urls}
            )
        results_table = results_table[results_table['Start time'] >= query['begin_time']]
        results_table = results_table[results_table['Start time'] <= query['end_time']]
        return results_table

    @staticmethod
    def _get_remote_files(dataset, wavelength, start, end):
        s3_client = boto3.client('s3', config=Config(signature_version=UNSIGNED))
        results = []
        for date in rrule(DAILY, dtstart=start.to_datetime(), until=end.to_datetime()):
            results.append(s3_client.list_objects_v2(Bucket="gov-nasa-hdrl-data1",
                                                     Prefix=f"sdo/{dataset}/{date.strftime(_HC_DATE_FMT)}/{wavelength:04}"))
        # Each file information is in the Contents key
        # We also want to filter out any directories.
        files = [obj for result in results for obj in result["Contents"] if obj["Key"].endswith(".fits")]
        urls = [_HC_BASEURL+file["Key"] for file in files]
        return files, urls

    def fetch(self, query_results, *, path, downloader, **kwargs):
        for row in query_results:
            fname = row['URL'].split('/')[-1]
            filepath = str(path).format(file=fname)
            downloader.enqueue_file(row['URL'], filename=filepath)

    @classmethod
    def _can_handle_query(cls, *query):
        required = {Dataset, a.Time, a.Wavelength}
        query_attrs = {type(x) for x in query}
        return required == query_attrs

    @classmethod
    def _attrs_module(cls):
        return 'heliocloud', 'sunpy.net.heliocloud.attrs'

    @classmethod
    def register_values(cls):
        from sunpy.net import attrs as a

        return {a.heliocloud.Dataset: [("AIA", "AIA data")]}
