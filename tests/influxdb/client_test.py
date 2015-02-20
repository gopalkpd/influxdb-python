# -*- coding: utf-8 -*-
"""
unit tests
"""
import json
import requests
import socket
import unittest
import requests_mock
from nose.tools import raises
from mock import patch
import warnings

from influxdb import InfluxDBClient
from influxdb.client import session


def _build_response_object(status_code=200, content=""):
    resp = requests.Response()
    resp.status_code = status_code
    resp._content = content.encode("utf8")
    return resp


def _mocked_session(method="GET", status_code=200, content=""):

    method = method.upper()

    def request(*args, **kwargs):
        c = content

        # Check method
        assert method == kwargs.get('method', 'GET')

        if method == 'POST':
            data = kwargs.get('data', None)

            if data is not None:
                # Data must be a string
                assert isinstance(data, str)

                # Data must be a JSON string
                assert c == json.loads(data, strict=True)

                c = data

        # Anyway, Content must be a JSON string (or empty string)
        if not isinstance(c, str):
            c = json.dumps(c)

        return _build_response_object(status_code=status_code, content=c)

    mocked = patch.object(
        session,
        'request',
        side_effect=request
    )

    return mocked


class TestInfluxDBClient(unittest.TestCase):

    def setUp(self):
        # By default, raise exceptions on warnings
        warnings.simplefilter('error', FutureWarning)

        self.cli = InfluxDBClient('localhost', 8086, 'username', 'password')
        self.dummy_points = [
            {
                "name": "cpu_load_short",
                "tags": {
                    "host": "server01",
                    "region": "us-west"
                },
                "timestamp": "2009-11-10T23:00:00Z",
                "values": {
                    "value": 0.64
                }
            }
        ]

    def test_scheme(self):
        cli = InfluxDBClient('host', 8086, 'username', 'password', 'database')
        assert cli._baseurl == 'http://host:8086'

        cli = InfluxDBClient(
            'host', 8086, 'username', 'password', 'database', ssl=True
        )
        assert cli._baseurl == 'https://host:8086'

    def test_switch_database(self):
        cli = InfluxDBClient('host', 8086, 'username', 'password', 'database')
        cli.switch_database('another_database')
        assert cli._database == 'another_database'

    def test_switch_user(self):
        cli = InfluxDBClient('host', 8086, 'username', 'password', 'database')
        cli.switch_user('another_username', 'another_password')
        assert cli._username == 'another_username'
        assert cli._password == 'another_password'

    def test_write(self):
        with requests_mock.Mocker() as m:
            m.register_uri(
                requests_mock.POST,
                "http://localhost:8086/write"
            )
            cli = InfluxDBClient(database='db')
            cli.write(
                {"database": "mydb",
                 "retentionPolicy": "mypolicy",
                 "points": [{"name": "cpu_load_short",
                             "tags": {"host": "server01",
                                      "region": "us-west"},
                             "timestamp": "2009-11-10T23:00:00Z",
                             "values": {"value": 0.64}}]}
            )

            self.assertEqual(
                json.loads(m.last_request.body),
                {"database": "mydb",
                 "retentionPolicy": "mypolicy",
                 "points": [{"name": "cpu_load_short",
                             "tags": {"host": "server01",
                                      "region": "us-west"},
                             "timestamp": "2009-11-10T23:00:00Z",
                             "values": {"value": 0.64}}]}
            )

    def test_write_points(self):
        with requests_mock.Mocker() as m:
            m.register_uri(
                requests_mock.POST,
                "http://localhost:8086/write"
            )

            cli = InfluxDBClient(database='db')
            cli.write_points(
                self.dummy_points,
            )
            self.assertDictEqual(
                {
                    "database": "db",
                    "points": self.dummy_points,
                },
                json.loads(m.last_request.body)
            )

    @unittest.skip('Not implemented for 0.9')
    def test_write_points_string(self):
        with requests_mock.Mocker() as m:
            m.register_uri(
                requests_mock.POST,
                "http://localhost:8086/db/db/series"
            )

            cli = InfluxDBClient(database='db')
            cli.write_points(
                str(json.dumps(self.dummy_points))
            )

            self.assertListEqual(
                json.loads(m.last_request.body),
                self.dummy_points
            )

    @unittest.skip('Not implemented for 0.9')
    def test_write_points_batch(self):
        with _mocked_session('post', 200, self.dummy_points):
            cli = InfluxDBClient('host', 8086, 'username', 'password', 'db')
            assert cli.write_points(
                data=self.dummy_points,
                batch_size=2
            ) is True

    def test_write_points_udp(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(('0.0.0.0', 4444))

        cli = InfluxDBClient(
            'localhost', 8086, 'root', 'root',
            'test', use_udp=True, udp_port=4444
        )
        cli.write_points(self.dummy_points)

        received_data, addr = s.recvfrom(1024)

        self.assertDictEqual(
            {
                "points": self.dummy_points,
                "database": "test"
            },
            json.loads(received_data.decode(), strict=True)
        )

    def test_write_bad_precision_udp(self):
        cli = InfluxDBClient(
            'localhost', 8086, 'root', 'root',
            'test', use_udp=True, udp_port=4444
        )

        with self.assertRaisesRegexp(
                Exception,
                "InfluxDB only supports seconds precision for udp writes"
        ):
            cli.write_points(
                self.dummy_points,
                time_precision='ms'
            )

    @raises(Exception)
    def test_write_points_fails(self):
        with _mocked_session('post', 500):
            cli = InfluxDBClient('host', 8086, 'username', 'password', 'db')
            cli.write_points([])

    def test_write_points_with_precision(self):
        with requests_mock.Mocker() as m:
            m.register_uri(
                requests_mock.POST,
                "http://localhost:8086/write"
            )

            cli = InfluxDBClient(database='db')
            cli.write_points(
                self.dummy_points,
                time_precision='n'
            )

            self.assertDictEqual(
                {u'points': self.dummy_points,
                 u'database': u'db',
                 u'precision': u'n',
                 },
                json.loads(m.last_request.body)
            )

    def test_write_points_bad_precision(self):
        cli = InfluxDBClient()
        with self.assertRaisesRegexp(
            Exception,
            "Invalid time precision is given. "
            "\(use 'n', 'u', 'ms', 's', 'm' or 'h'\)"
        ):
            cli.write_points(
                self.dummy_points,
                time_precision='g'
            )

    @raises(Exception)
    def test_write_points_with_precision_fails(self):
        with _mocked_session('post', 500):
            cli = InfluxDBClient('host', 8086, 'username', 'password', 'db')
            cli.write_points_with_precision([])

    def test_query(self):
        data = [
            {
                "name": "foo",
                "columns": ["time", "sequence_number", "column_one"],
                "points": [
                    [1383876043, 16, "2"], [1383876043, 15, "1"],
                    [1383876035, 14, "2"], [1383876035, 13, "1"]
                ]
            }
        ]
        with _mocked_session('get', 200, data):
            cli = InfluxDBClient('host', 8086, 'username', 'password', 'db')
            result = cli.query('select column_one from foo;')
            assert len(result[0]['points']) == 4

    @unittest.skip('Not implemented for 0.9')
    def test_query_chunked(self):
        cli = InfluxDBClient(database='db')
        example_object = {
            'points': [
                [1415206250119, 40001, 667],
                [1415206244555, 30001, 7],
                [1415206228241, 20001, 788],
                [1415206212980, 10001, 555],
                [1415197271586, 10001, 23]
            ],
            'name': 'foo',
            'columns': [
                'time',
                'sequence_number',
                'val'
            ]
        }
        example_response = \
            json.dumps(example_object) + json.dumps(example_object)

        with requests_mock.Mocker() as m:
            m.register_uri(
                requests_mock.GET,
                "http://localhost:8086/db/db/series",
                text=example_response
            )

            self.assertListEqual(
                cli.query('select * from foo', chunked=True),
                [example_object, example_object]
            )

    @raises(Exception)
    def test_query_fail(self):
        with _mocked_session('get', 401):
            self.cli.query('select column_one from foo;')

    def test_create_database(self):
        with requests_mock.Mocker() as m:
            m.register_uri(
                requests_mock.GET,
                "http://localhost:8086/query",
                text='{"results":[{}]}'
            )
            self.cli.create_database('new_db')
            self.assertEqual(
                m.last_request.qs['q'][0],
                'create database new_db'
            )

    @raises(Exception)
    def test_create_database_fails(self):
        with _mocked_session('post', 401):
            self.cli.create_database('new_db')

    def test_drop_database(self):
        with requests_mock.Mocker() as m:
            m.register_uri(
                requests_mock.GET,
                "http://localhost:8086/query",
                text='{"results":[{}]}'
            )
            self.cli.drop_database('new_db')
            self.assertEqual(
                m.last_request.qs['q'][0],
                'drop database new_db'
            )

    @raises(Exception)
    def test_drop_database_fails(self):
        with _mocked_session('delete', 401):
            cli = InfluxDBClient('host', 8086, 'username', 'password', 'db')
            cli.drop_database('old_db')

    def test_get_list_database(self):
        data = {
            "results":
            [
                {"rows": [
                    {"columns": ["name"],
                     "values":[["mydb"], ["myotherdb"]]}]}
            ]
        }

        with _mocked_session('get', 200, json.dumps(data)):
            self.assertListEqual(
                self.cli.get_list_database(),
                [u'mydb', u'myotherdb']
            )

    @raises(Exception)
    def test_get_list_database_fails(self):
        with _mocked_session('get', 401):
            cli = InfluxDBClient('host', 8086, 'username', 'password')
            cli.get_list_database()

    @unittest.skip('Not implemented for 0.9')
    def test_get_series_list(self):
        cli = InfluxDBClient(database='db')

        with requests_mock.Mocker() as m:
            example_response = \
                '[{"name":"list_series_result","columns":' \
                '["time","name"],"points":[[0,"foo"],[0,"bar"]]}]'

            m.register_uri(
                requests_mock.GET,
                "http://localhost:8086/db/db/series",
                text=example_response
            )

            self.assertListEqual(
                cli.get_list_series(),
                ['foo', 'bar']
            )

    def test_get_list_retention_policies(self):
        example_response = \
            u'{"results": [{"rows": [{"values": [["fsfdsdf", "24h0m0s", 2]],' \
            u' "columns": ["name", "duration", "replicaN"]}]}]}'

        with requests_mock.Mocker() as m:
            m.register_uri(
                requests_mock.GET,
                "http://localhost:8086/query",
                text=example_response
            )
            self.assertListEqual(
                self.cli.get_list_retention_policies(),
                [{u'duration': u'24h0m0s', u'name': u'fsfdsdf', u'replicaN': 2}]
            )
