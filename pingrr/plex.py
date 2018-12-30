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
plex = PlexServer(conf['plex']['SERVER_URL'], conf['plex']['SERVER_TOKEN'])

def in_plex(imdb):
    movies = plex.library.section('Movies')
    if movies.search(guid=imdb):
        return True
    else:
        return False