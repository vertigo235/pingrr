import logging
import config
import platform
from plexapi.server import PlexServer

################################
# Load config
################################

conf = config.Config().config

################################
# Logging
################################

logger = logging.getLogger(__name__)

################################
# Init
################################

if 'plex' in conf:
    plex = PlexServer(conf['plex']['SERVER_URL'], conf['plex']['SERVER_TOKEN'])

#plex = PlexServer('http://192.168.1.15:32400','CFx3ocCEwsjA2HqtJ85k')

def series_in_plex(tvdbid, section):
    shows = plex.library.section(section)
    logger.debug("Searching plex %s library for %s", section, tvdbid)
    searchguid = 'com.plexapp.agents.thetvdb://' + str(tvdbid) + '?lang=en'
    if shows.search(guid=searchguid):
        return True
    else:
        return False

def movie_in_plex(imdb, section):
    movies = plex.library.section(section)
    logger.debug("Searching plex %s library for %s", section, imdb)
    #searchguid = 'com.plexapp.agents.imdb://' + imdb + '?lang=en'
    if movies.search(guid=imdb):
        return True
    else:
        return False