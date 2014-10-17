#!/usr/bin/env python
# -*- coding: latin-1 -*-

###
# Copyright (c) 2009, Benjamin Rubin
# All rights reserved.
#
#
###
import supybot.conf as conf
#import supybot.utils as utils
from supybot.commands import *
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
#import supybot.utils as utils
import supybot.ircmsgs as ircmsgs
#import supybot.plugins as plugins
#from BeautifulSoup import BeautifulStoneSoup
#import cPickle as pickle
import os
#import pprint
#from string import Template
import GeoIP
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Sequence
import wunder
Base = declarative_base()


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, Sequence('user_id_seq'), primary_key=True)
    name = Column(String(50), unique=True, nullable=False)  # some nicklens: freenode = 16, oftc = 30
    temperature = Column(String(1), nullable=True)
    distance = Column(String(5), nullable=True)
    location = Column(String(255), nullable=True)

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return '<User: %s>' % self.name

# some validation/normalization functions


def normalize_temp(temp):
    temp = temp.lower().strip('.')
    if temp in ['c', 'celcius', 'centigrade']:
        return 'c'
    elif temp in ['f', 'fahrenheit']:
        return 'f'
    elif temp in ['kelvin', 'k']:
        return 'k'
    else:
        raise ValueError('Invalid temperature specified')


def normalize_dist(dist):
    dist = dist.lower().strip('.')
    if dist in ['miles', 'mi']:
        return 'mi'
    elif dist in ['kilometers', 'km']:
        return 'km'
    elif dist in ['meters', 'm']:
        return 'm'
    else:
        raise ValueError('Invalid measurement specified')


def getUserTemp(user, temp_f):
    savedTemp = user.temperature
    if not savedTemp or savedTemp == 'f':
        temp = ircutils.bold(temp_f) + 'F'
    elif savedTemp == 'c':
        temp = ircutils.bold('%.1f' % ((float(temp_f) - 32) / 1.8)) + 'C'
    elif savedTemp == 'k':
        temp = ircutils.bold('%.1f' % (((float(temp_f) - 32) / 1.8) + 273)) + 'K'

    return temp


def getUserDist(user, mph, direction):
    savedDist = user.distance
    if mph in [0, -9999, 9999, 999.0, -999.0]:
        formatted = ircutils.bold('Calm')
    else:
        if not savedDist or savedDist == 'mi':
            formatted = '%s mph %s' % (ircutils.bold(mph), direction)
        elif savedDist == 'km':
            formatted = '%s kph %s' % (ircutils.bold(str(int(float(mph) * 1.6))), direction)
        elif savedDist == 'm':
            formatted = '%s m/h %s' % (ircutils.bold(str(int(float(mph) * 1609))), direction)

    return formatted


class Wunder(callbacks.Plugin):
    threaded = True

    def __init__(self, irc):
        self.__parent = super(Wunder, self)
        self.__parent.__init__(irc)

        # TODO
        # Replace with database agnostic code
        if True:  # if sqlite
            filename = conf.supybot.directories.data.dirize('wunder.db')
            engine = create_engine('sqlite:///%s' % filename, echo=True)
            if not os.path.exists(filename):
                Base.metadata.create_all(engine)
            self.__session = sessionmaker(bind=engine, autoflush=True,
                                          autocommit=True)
            self.db = self.__session()

        self.gi = GeoIP.open("/usr/share/GeoIP/GeoIPCity.dat", GeoIP.GEOIP_STANDARD)

    def die(self):
        self.db.close_all()

    def get_user(self, username):
        try:
            query = self.db.query(User)
            user = query.filter(User.name == username).one()
            return user
        except NoResultFound:
            user = self.db.add(User(username))
            #self.db.commit()
            return query.filter(User.name == username).one()

    def geolookup(self, host):
        location = self.gi.record_by_name(host)
        try:
            return '{city}, {region}, {country_code}'.format(**location)
        except:
            return None

    def temp(self, irc, msg, args, query):
        """<unit>

        Sets the user's default temperature unit.
        Supports Celcius, Farenheit, Kelvin and their abbreviations"""
        user = self.get_user(msg.prefix)

        try:
            user.temperature = normalize_temp(query)
            #self.db.commit()
            irc.reply('Set unit preference')
        except ValueError, e:
            irc.reply('Error: %s' % e)
    temp = wrap(temp, ['text'])

    def dist(self, irc, msg, args, query):
        """<unit>

        Sets the user's default distance unit.
        Supports miles, kilometers, meters and their abbreviations"""
        user = self.get_user(msg.prefix)

        try:
            user.distance = normalize_dist(query)
            #self.db.commit()
            irc.reply('Set unit preference')
        except ValueError, e:
            irc.reply('Error: %s' % e)
    dist = wrap(dist, ['text'])

    def makeWeatherDict(json):
        d = {'location': current['display_location']['full'],
             'time': current['observation_time_rfc822'],
             'weather': current['weather'],
             'temp_f': current['temp_f'],
             'temp_c': current['temp_c'],
             'humidity': current['relative_humidity'],
             'wind_dir': current['wind_dir'],
             'wind_degrees': current['wind_degrees'],
             'wind_mph': current['wind_mph'],
             'wind_gust_mph': current['wind_gust_mph'],
             'pressure_mb': current['pressure_mb'],
             'pressure_in': current['pressure_in'],
             }
        return d

    def weather(self, irc, msg, args, query):
        """<location>

        Returns the current weather for a given location"""
        save = False
        if query:
            try:
                user = self.get_user(irc.state.nickToHostmask(query))
                locquery = user.location
                if not locquery:
                    irc.reply('No saved location found for %s' % user)
                    return
            except:
                self.log.info('Wunder.py: Location specified: %s.' % (query))
            save = True
            locquery = query
        else:
            self.log.info('Wunder.py: Looking for saved location for %s' % msg.prefix)
            user = self.get_user(msg.prefix)
            locquery = user.location
            if locquery:
                self.log.info('Wunder.py: Saved location found: %s' % locquery)
            else:
                self.log.info('Wunder.py: Saved location not found')
                locquery = self.geolookup(msg.host)
                if not locquery:
                    irc.reply('Location could not be determined, please specify a location.')
                    return

        user = self.get_user(msg.prefix)
        self.log.info('Wunder.py: Looking up weather for %s' % locquery)

        api_key = self.registryValue('api_key')
        w = wunder.WunderAPI(api_key, locquery)
        try:
            current = w.json['current_observation']
        except KeyError:
            irc.reply('Location not found')
            return
        ## Grab current weather information
        location = current['display_location']['full']
        #time = current['observation_time_rfc822']
        weather = current['weather']
        temp_f = current['temp_f']
        #temp_c = current['temp_c']
        feels_like_f = current['feelslike_f']
        humidity = current['relative_humidity']
        wind_dir = current['wind_dir']
        #wind_degrees = current['wind_degrees']
        wind_mph = current['wind_mph']
        #wind_gust_mph = current['wind_gust_mph']
        #pressure_mb = current['pressure_mb']
        #pressure_in = current['pressure_in']

        ## Grab weather alerts
        alert_items = w.json['alerts']
        alerts = list()
        for alert in alert_items:
            alerts.append(ircutils.bold(alert['description'].title()))
        alert_text = ''
        if alerts != []:
            alert_text = ' Alerts: %s,' % ', '.join(alerts)

        ## Get forecast
        # might as well pull out all the forecast data that we're given
        f = w.json['forecast']
        forecasts = f['txt_forecast']['forecastday']

        simple = f['simpleforecast']['forecastday']

        try:
            for i in range(len(forecasts)):
                conditions = '{0} ({1}/{2})'.format(ircutils.bold(simple[i]['conditions']),
                                                    getUserTemp(user, simple[i]['high']['fahrenheit']),
                                                    getUserTemp(user, simple[i]['low']['fahrenheit']))
                forecasts[i]['conditions'] = conditions
        except IndexError:
            pass

        ## Use saved units

        temp = getUserTemp(user, temp_f)
        feels_like_formatted = getUserTemp(user, feels_like_f)
        #self.log.info(temp)
        wind_formatted = getUserDist(user, wind_mph, wind_dir)
        ## Respond
        if ircutils.stripBold(location) == ', ':
            self.log.info('Wunder.py: No results for location: %s' % locquery)
            s = "Location not found."
        else:
	    if save:
	        user.location = locquery
                #self.db.commit()
            self.log.info('Wunder.py: Location found. Returning current weather')
            s = (
                  "{0}: Temp: {1}(≈{7}), Humidity: {2}, Current Conditions: {3}, Wind: "
                  "{4},{5} {6[0][title]}: {6[0][conditions]}, {6[1][title]}: "
                  "{6[1][conditions]}"
                  ).format(ircutils.bold(location), temp, ircutils.bold(humidity),
                          ircutils.bold(weather), wind_formatted, alert_text,
                          forecasts, feels_like_formatted)

        # self.log.info(ircutils.stripBold(s))
        if ircutils.isChannel(msg.args[0]):
            irc.queueMsg(ircmsgs.privmsg(msg.args[0],s))
	else:
	    irc.queueMsg(ircmsgs.privmsg(msg.nick,s))


    weather = wrap(weather,[optional('text')])

Class = Wunder

