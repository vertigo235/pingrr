import logging
import config
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

def in_plex(imdb):
    movies = plex.library.section('Movies')
    logger.debug("Searching plex library for %s", imdb)
    if movies.search(guid=imdb):
        return True
    else:
        return False