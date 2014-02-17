#!/usr/bin/env python2.7
from collections import namedtuple
import simplejson as json
import os
import pprint
import sys
import re
import urllib2

class AmbiguousLocation(Exception):
    """Raised when a geolookup returns multiple locations"""
    def __init__(self, lookup, results):
        self.lookup = lookup
        self.results = results

    def __str__(self):
        return repr(self.lookup)

class WunderAPI:
    def __init__(self, apikey, location):
        self.api_key = apikey
        self.user_location = location
        self.location = self._format_location(location)
        self.json = self._get_json()

        self._validate_response()

    def _get_json(self):
        url = 'http://api.wunderground.com/api/%s/geolookup/conditions/alerts/forecast/q/%s.json' % (self.api_key, self.location)
        u = urllib2.urlopen(url)
        return json.loads(u.read())

    def _format_location(self,location):
        return re.sub('\W','_',location)

    def _validate_response(self):
        if 'results' in self.json['response']:
            raise AmbiguousLocation(self.location,self.json['response']['results'])
        
        

def main(argv=None):
   pass 


if __name__ == '__main__':
    sys.exit(main())
