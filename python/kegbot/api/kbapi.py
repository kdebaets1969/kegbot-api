# Copyright 2010 Mike Wakerly <opensource@hoho.com>
#
# This file is part of the Pykeg package of the Kegbot project.
# For more information on Pykeg or Kegbot, see http://kegbot.org/
#
# Pykeg is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# Pykeg is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Pykeg.  If not, see <http://www.gnu.org/licenses/>.

"""Kegweb API client."""

import datetime
import sys
import requests

from kegbot.util import kbjson

import gflags

gflags.DEFINE_float('api_timeout', 10.0,
    'Socket timeout, in seconds, for Kegbot web API operations. '
    'Note that this timeout only applies to blocking socket operations '
    '(such as opening a connection) and not I/O.')

FLAGS = gflags.FLAGS

_DEFAULT_URL = 'http://localhost:8000/api/'
_DEFAULT_KEY = ''
try:
  from pykeg import settings
  if hasattr(settings, 'KEGWEB_BASE_URL'):
    _DEFAULT_URL = '%s/api/' % getattr(settings, 'KEGWEB_BASE_URL')
  if hasattr(settings, 'KEGWEB_API_KEY'):
    _DEFAULT_KEY = settings.KEGWEB_API_KEY
except ImportError:
  # Non-fatal if we can't load settings.
  pass

gflags.DEFINE_string('api_url', _DEFAULT_URL,
    'Base URL for the Kegweb HTTP api.')

gflags.DEFINE_string('api_key', _DEFAULT_KEY,
    'Access key for the Kegweb HTTP api.')

### begin common

class Error(Exception):
  """An error occurred."""
  HTTP_CODE = 400
  def Message(self):
    if self.message:
      return self.message
    m = self.__class__.__doc__
    m = m.split('\n', 1)[0]
    return m

class NotFoundError(Error):
  """The requested object could not be found."""
  HTTP_CODE = 404

class ServerError(Error):
  """The server had a problem fulfilling your request."""
  HTTP_CODE = 500

class BadRequestError(Error):
  """The request was incompleted or malformed."""
  HTTP_CODE = 401

class NoAuthTokenError(Error):
  """An api_key is required."""
  HTTP_CODE = 401

class BadApiKeyError(Error):
  """The api_key given is invalid."""
  HTTP_CODE = 401

class PermissionDeniedError(Error):
  """The api_key given does not have permission for this resource."""
  HTTP_CODE = 401

MAP_NAME_TO_EXCEPTION = dict((c.__name__, c) for c in Error.__subclasses__())

def ErrorCodeToException(code, message=None):
  cls = MAP_NAME_TO_EXCEPTION.get(code, Error)
  return cls(message)

def decode_response(response):
  """Decodes the requests response object as a JSON response.

  For normal responses, the return value is the Python JSON-decoded 'result'
  field of the response.  If the response is an error, a RemoteError exception
  is raised.
  """

  status_code = response.status_code
  response_dict = kbjson.loads(response.text)

  if 'error' in response_dict:
    # Response had an error: translate to exception.
    err = response_dict['error']
    code = err.get('code', status_code)
    message = err.get('message', None)
    e = ErrorCodeToException(code, message)
    raise e
  elif 'object' in response_dict or 'objects' in response_dict:
    # Response was OK, return the result.
    return response_dict
  else:
    # WTF?
    raise ValueError('Invalid response from server: missing result or error')

### end common

class Client:
  """Kegweb RESTful API client."""
  def __init__(self, api_url=None, api_key=None):
    if api_url is None:
      api_url = FLAGS.api_url
    if api_key is None:
      api_key = FLAGS.api_key
    self._api_url = api_url
    self._api_key = api_key

  def _Encode(self, s):
    return unicode(s).encode('utf-8')

  def _EncodePostData(self, post_data):
    if not post_data:
      return None
    return urlencode(dict(((k, self._Encode(v)) for k, v in
        post_data.iteritems() if v is not None)))

  def _GetURL(self, endpoint):
    base = self._api_url.rstrip('/')
    endpoint = endpoint.strip('/')
    return '%s/%s' % (base, endpoint)

  def SetAuthToken(self, api_key):
    self._api_key = api_key

  def DoGET(self, endpoint, params=None):
    """Issues a GET request to the endpoint, and retuns the result.

    Keyword arguments are passed to the endpoint as GET arguments.

    For normal responses, the return value is the Python JSON-decoded 'object'
    or 'objects' field of the response.  If the response is an error, a
    RemoteError exception is raised.

    If there was an error contacting the server, or in parsing its response, a
    ServerError is raised.
    """
    return self._FetchResponse(endpoint, params=params)

  def DoPOST(self, endpoint, post_data, params=None):
    """Issues a POST request to the endpoint, and returns the result.

    For normal responses, the return value is the Python JSON-decoded 'object'
    or 'objects' field of the response.  If the response is an error, a
    RemoteError exception is raised.

    If there was an error contacting the server, or in parsing its response, a
    ServerError is raised.
    """
    return self._FetchResponse(endpoint, params=params, post_data=post_data)

  def _FetchResponse(self, endpoint, params=None, post_data=None):
    """Issues a POST or GET request, depending on the arguments."""
    headers = {
      'X-Kegbot-Api-Key': self._api_key,
    }
    url = self._GetURL(endpoint)

    if post_data:
      r = requests.post(url, params=params, data=post_data, headers=headers,
          timeout=FLAGS.api_timeout)
    else:
      r = requests.get(url, params=params, headers=headers,
          timeout=FLAGS.api_timeout)

    return decode_response(r)

  def RecordDrink(self, tap_name, ticks, volume_ml=None, username=None,
      pour_time=None, duration=0, auth_token=None, spilled=False, shout=''):
    endpoint = '/taps/%s' % tap_name
    post_data = {
      'tap_name': tap_name,
      'ticks': ticks,
    }
    if volume_ml is not None:
      post_data['volume_ml'] = volume_ml
    if username is not None:
      post_data['username'] = username
    if duration > 0:
      post_data['duration'] = duration
    if auth_token is not None:
      post_data['auth_token'] = auth_token
    if spilled:
      post_data['spilled'] = spilled
    if shout:
      post_data['shout'] = shout
    if pour_time:
      post_data['pour_time'] = int(pour_time.strftime('%s'))
      post_data['now'] = int(datetime.datetime.now().strftime('%s'))
    return self.DoPOST(endpoint, post_data=post_data).object

  def CancelDrink(self, seqn, spilled=False):
    endpoint = '/cancel-drink'
    post_data = {
      'id': seqn,
      'spilled': spilled,
    }
    return self.DoPOST(endpoint, post_data=post_data).object

  def LogSensorReading(self, sensor_name, temperature, when=None):
    endpoint = '/thermo-sensors/%s' % (sensor_name,)
    post_data = {
      'temp_c': float(temperature),
    }
    # TODO(mikey): include post data
    return self.DoPOST(endpoint, post_data=post_data).object

  def TapStatus(self):
    """Gets the status of all taps."""
    return self.DoGET('taps').objects

  def GetToken(self, auth_device, token_value):
    url = 'auth-tokens/%s/%s' % (auth_device, token_value)
    try:
      return self.DoGET(url).object
    except ServerError, e:
      raise NotFoundError(e)

  def AllDrinks(self):
    """Gets a list of all drinks."""
    return self.DoGET('drinks').objects

  def AllSoundEvents(self):
    """Gets a list of all drinks."""
    return self.DoGET('sound-events').objects

def main():
  import pprint
  c = Client()

  print '== record a drink =='
  pprint.pprint(c.RecordDrink('kegboard.flow0', 2200))
  print ''

  print '== tap status =='
  for t in c.TapStatus():
    pprint.pprint(t)
    print ''

  print '== last drinks =='
  for d in c.AllDrinks():
    pprint.pprint(d)
    print ''

if __name__ == '__main__':
  FLAGS(sys.argv)
  main()