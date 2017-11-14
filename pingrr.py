import pingrr.config as config

import json
import logging
from logging.handlers import RotatingFileHandler
import sys
import requests

from time import sleep
from imdb import IMDb

i = IMDb()

################################
# Logging
################################

# Logging format
formatter = logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s %(message)s')

# root logger
logger = logging.getLogger()
# Set initial level to INFO
logger.setLevel(logging.INFO)

# Console handler, log to stdout
consoleHandler = logging.StreamHandler(sys.stdout)
consoleHandler.setFormatter(formatter)
logger.addHandler(consoleHandler)

# Other modules logging levels
logging.getLogger("requests").setLevel(logging.WARNING)

################################
# Load config
################################

# Load initial config
configuration = config.Config()

# Set configured log level
logger.setLevel(configuration.settings['loglevel'])

# Load config file
configuration.load()
conf = configuration.config

# Log file handler
fileHandler = RotatingFileHandler(configuration.settings['logfile'], maxBytes=1024 * 1024 * 2, backupCount=1)
fileHandler.setFormatter(formatter)
logger.addHandler(fileHandler)

################################
# Init
################################

import pingrr.trakt as trakt
import pingrr.sonarr as sonarr
import pingrr.allflicks as allflicks
import pingrr.justWatch as justWatch
import pingrr.radarr as radarr
from pingrr.notifications import Notifications

new = []
delay_time = conf['pingrr']['timer'] * 3600
options = {"ignoreEpisodesWithFiles": False, "ignoreEpisodesWithoutFiles": False,
           "searchForMissingEpisodes": conf['sonarr']['search_missing_episodes']}
notify = Notifications()

if conf['pushover']['enabled']:
    notify.load(service="pushover", app_token=conf['pushover']['app_token'], user_token=conf['pushover']['user_token'])

if conf['slack']['enabled']:
    notify.load(service="slack", webhook_url=conf['slack']['webhook_url'], sender_name=conf['slack']['sender_name'],
                sender_icon=conf['slack']['sender_icon'], channel=conf['slack']['channel'])


################################
# Main
################################


def create_path(genres, program):
    """Create path based on genre for sonarr/radarr"""

    # Set root folder for path creation
    root_folder = conf[program]['path_root']

    # Check if any of the genres match up
    for key in conf[program]['paths']:
        for genre in conf[program]['paths'][key]:
            if genre in genres:
                return root_folder + key + '/'
    # If no match, return default path
    return conf[program]['folder_path']


def send_to_sonarr(a, b, genres):
    """Send found tv program to sonarr"""

    path = create_path(genres, "sonarr")

    payload = {"tvdbId": a, "title": b, "qualityProfileId": conf['sonarr']['quality_profile'], "images": [],
               "seasons": [], "seasonFolder": True, "monitored": conf['sonarr']['monitored'], "rootFolderPath": path,
               "addOptions": options, }

    r = requests.post(sonarr.url + '/api/series', headers=sonarr.headers, data=json.dumps(payload), timeout=10)

    if r.status_code == 201:
        logger.debug("sent to sonarr successfully")
        return True

    else:
        logger.debug("failed to send to sonarr, code return: %r", r.status_code)
        return False


def send_to_radarr(a, b, genres, year):
    """Send found tv program to sonarr"""

    path = create_path(genres, "radarr")

    payload = {"tmdbId": a,
               "title": b,
               "qualityProfileId": conf['radarr']['quality_profile'],
               "images": [],
               "monitored": conf['radarr']['monitored'],
               "titleSlug": b,
               "rootFolderPath": path,
               "minimumAvailability": "preDB",
               "year": year
               }

    r = requests.post(radarr.url + '/api/movie', headers=radarr.headers, data=json.dumps(payload), timeout=10)

    if r.status_code == 201:
        logger.debug("sent to radarr successfully")
        return True

    else:
        logger.debug("failed to send to radarr, code return: %r", r.status_code)
        return False


def add_media(program):
    added_list = []
    n = 0

    limit = conf['pingrr']['limit'][program]

    for media in new:
        title = media['title']

        if program == "radarr":
            media_id = media['tmdb']
        elif program == "sonarr":
            media_id = media['tvdb']

        try:
            logger.debug('Sending media to {}: {}'.format(program, media['title'].encode('utf8')))

            if program == "sonarr":
                if send_to_sonarr(media_id, title, media['genres']):
                    logger.info('{} has been added to Sonarr'.format(title.encode('utf8')))
                    added_list.append(media['title'])

                    if media['aired'] >= conf['pingrr']['aired']:
                        n += 1
                    else:
                        logger.info(
                            "{} only has {} episodes, does not count towards add limit".format(media['title'].encode('utf8'),
                                                                                               media['aired']))
                    if 0 < limit == n:
                        logger.info('{} shows added limit reached'.format(str(n)))
                        break

                    elif limit > 0 and not n == limit:
                        logger.debug('limit not yet reached: {}'.format(str(n)))

                else:
                    configuration.blacklist.add(str(media["tvdb"]))
                    logger.warning('{} failed to be added to Sonarr! Adding to blacklist'.format(title.encode('utf8')))

            if program == "radarr":
                if send_to_radarr(media_id, title, media['genres'], media['year']):
                    logger.info('{} has been added to Radarr'.format(title.encode('utf8')))
                    added_list.append(media['title'])
                    n += 1

                    if 0 < limit == n:
                        logger.info('{} shows added limit reached'.format(str(n)))
                        break

                    elif limit > 0 and not n == limit:
                        logger.debug('limit not yet reached: {}'.format(str(n)))

                else:
                    configuration.blacklist.add(str(media["tmdb"]))
                    logger.warning('{} failed to be added to Radarr! Adding to blacklist'.format(title.encode('utf8')))

        except IOError:
            logger.warning('error sending media: {} id: {}'.format(title.encode('utf8'), str(media_id)))

    if conf['pushover']['enabled'] or conf['slack']['enabled'] and n != 0:
        pass
        # message = "The following {} item(s) out of {} added to {}: \n \n".format(str(n), str(len(new), program)
        #                                                                          .join(added_list))
        # notify.send(message=message)


def new_check(item_type):
    """Check for new trakt items in list"""
    if item_type == "movies":
        library = radarr.get_library()
        program = "radarr"
    else:
        library = sonarr.get_library()
        program = "sonarr"

    global new

    new = filter_list(item_type)
    logger.info('checking for new {} in lists'.format(item_type))

    if item_type == "movies":
        item_id = "imdb"
    else:
        item_id = "tvdb"

    for x in new:
        logger.debug('checking {} from list: {}'.format(item_type, x['title'].encode('utf8')))
        if x[item_id] not in library and conf['filters']['allow_ended']:
            logger.info('new media found, adding {} {} now'.format(len(new), item_type))
            add_media(program)
            break

        if item_type == "shows":
            if x[item_id] not in library and not x['status'] == 'ended':
                logger.info('new continuing show(s) found, adding shows now')
                add_media(program)
                break


def check_lists(arg, arg2):
    for filters in conf['filters'][arg]:
        for data in arg2:
            if filters == data:
                return True
    return False


def filter_check(title, item_type):

    if item_type == "shows":
        country = title['country']
        type_id = "tvdb"
        library = sonarr_library
    elif item_type == "movies":
        type_id = "tmdb"
        library = radarr_library
        country = False
    else:
        return False

    lang = title['language']

    if title[type_id] not in library:
        if str(title['imdb']) in configuration.blacklist or str(title[type_id]) in configuration.blacklist:
            logger.info("{} was rejected as it was found in the blacklist".format(title['title'].encode('utf8')))
            return False

        if conf['filters']['year'] > title['year']:
            logger.info(
                "{} was rejected as it was outside allowed year range: {}".format(title['title'].encode('utf8'),
                                                                                  str(title['year'])))
            return False

        if conf['filters']['runtime'] > title['runtime']:
            logger.info("{} was rejected as it was outside allowed runtime: {}".format(title['title'].encode('utf8'),
                                                                                       str(title['runtime'])))
            return False

        if item_type == "shows":
            if title['network'] is None or conf['filters']['network'] in title['network']:
                logger.info("{} was rejected as it was by a disallowed network: {}".format(title['title'].encode('utf8'),
                                                                                           str(title['network'])))
                return False

        if conf['filters']['votes'] > title['votes']:
            logger.info(
                "{} was rejected as it did not meet vote requirement: {}".format(title['title'].encode('utf8'),
                                                                                 str(title['votes'])))
            return False

        if conf['filters']['allow_ended'] is False and 'ended' in title['status']:
            logger.info("{} was rejected as it is an ended tv series".format(title['title'].encode('utf8')))
            return False

        if item_type == "shows":
            if conf['filters']['allow_canceled'] is False and 'canceled' in title['status']:
                logger.info("{} was rejected as it an canceled tv show".format(title['title'].encode('utf8')))
                return False

        if float(title['rating']) < float(conf['filters']['rating']):
            logger.info(
                "{} was rejected as it was outside the allowed ratings: {}".format(title['title'].encode('utf8'),
                                                                                   str(title['rating'])))
            return False

        if isinstance(conf['filters']['genre'], list):
            if check_lists('genre', title['genres']):
                logger.info("{} was rejected as it wasn't a wanted genre: {}".format(title['title'].encode('utf8'),
                                                                                     str(title['genres'])))
                return False

        elif conf['filters']['genre'] == title['genres']:
            logger.info("{} was rejected as it wasn't a wanted genre: {}".format(title['title'].encode('utf8'),
                                                                                 str(title['genres'])))
            return False

        if country and country not in conf['filters']['country']:
            logger.info("{} was rejected as it wasn't a wanted country: {}".format(title['title'].encode('utf8'),
                                                                                   str(title['country'])))
            return False

        if lang not in conf['filters']['language']:
            logger.info("{} was rejected as it wasn't a wanted language: {}".format(title['title'].encode('utf8'), lang))
            return False
        return True

    else:
        logger.info("{} was rejected as it is already in {} library".format(title['title'].encode('utf8'), item_type))


def filter_list(list_type):
    # Create the lists ready to be filtered down
    if list_type == 'shows':
        raw_list = []
        item_id = "tvdb"
        for trakt_list in conf['trakt']['tv_list']:
            if conf['trakt']['tv_list'][trakt_list]:
                raw_list = trakt.get_info('tv')
                break
        # if conf['allflicks']['enabled']['shows']:
        #     raw_list += allflicks.create_list()
        if conf['just_watch']['enabled']['shows']:
            raw_list += justWatch.create_list("shows")
    if list_type == 'movies':
        item_id = "tmdb"
        raw_list = []
        for trakt_list in conf['trakt']['movie_list']:
            if conf['trakt']['movie_list'][trakt_list]:
                raw_list = trakt.get_info('movie')
                break
        if conf['just_watch']['enabled']['movies']:
            raw_list += justWatch.create_list("movies")
        fixed_raw = []
        for raw in raw_list:
            try:
                fixed_raw.append(raw[0])
            except KeyError:
                fixed_raw.append(raw)
        raw_list = fixed_raw

    filtered = []
    for title in raw_list:
        try:
            # If not already in the list, check against filters
            if filter_check(title, list_type) and title[item_id] not in filtered:
                logger.debug('adding {} to potential add list'.format(title['title'].encode('utf8')))
                filtered.append(title)
            else:
                logger.debug('{} is a dupe, already in potential list'.format(title['title'].encode('utf8')))
                pass
        except TypeError:
            logger.debug('{} failed to check against filters'.format(title['title'].encode('utf8')))
    logger.debug("Filtered list successfully")
    return filtered


if __name__ == "__main__":
    while True:
        if conf['sonarr']['api']:
            try:
                sonarr_library = sonarr.get_library()
                new_check('shows')
            except requests.exceptions.ReadTimeout:
                logger.warning("Sonarr library timed out, skipping for now")
            except requests.exceptions.ConnectionError:
                logger.warning("Can not connect to Sonarr, check sonarr is running or host is correct")

        if conf['radarr']['api']:
            try:
                radarr_library = radarr.get_library()
                new_check('movies')
            except requests.exceptions.ReadTimeout:
                logger.warning("Radarr library timed out, skipping for now")
            except requests.exceptions.ConnectionError:
                logger.warning("Can not connect to Radarr, check Radarr is running or host is correct")

        # Save updated blacklist
        configuration.save_blacklist()

        if conf['pingrr']['timer'] == 0:
            logger.info('Scan finished, shutting down')
            sys.exit()

        if conf['pingrr']['timer'] > 1:
            hours = "s"
        else:
            hours = ""

        logger.info("check finish, sleeping for {} hour{}".format(conf['pingrr']['timer'], hours))
        sleep(float(delay_time))
        logger.debug('sleep over, checking again')
