from functools import wraps
from flask import Flask, request, Response, abort
from datetime import datetime
import os

import json
import pytz
import iso8601
import logging
from eventbrite import Eventbrite

app = Flask(__name__)

logger = None

def datetime_format(dt):
    return '%04d' % dt.year + dt.strftime("-%m-%dT%H:%M:%SZ")


def to_transit_datetime(dt_int):
    return "~t" + datetime_format(dt_int)

class DataAccess:
    def __init__(self):
        self._entities = {"events": [], "orders": [], "organizers": [], "bookmarks": [], "assortment": [], "owned_event_attendees": [], "owned_event_orders": []}

    def get_entities(self, since, datatype, eventbrite):
        if not datatype in self._entities:
            abort(404)
        if since is None:
            return self.get_entitiesdata(datatype, since, eventbrite)
        else:
            return [entity for entity in self.get_entitiesdata(datatype, since, eventbrite) if entity["_updated"] > since]

    def get_entitiesdata(self, datatype, since, eventbrite):
        # if datatype in self._entities:
        #     if len(self._entities[datatype]) > 0 and self._entities[datatype][0]["_updated"] > "%sZ" % (datetime.now() - timedelta(hours=12)).isoformat():
        #        return self._entities[datatype]
        now = datetime.now(pytz.UTC)
        entities = []
        end = datetime.now(pytz.UTC)  # we need to use UTC as salesforce API requires this

        data = {}
        if since:
            data['changed_since'] = iso8601.parse_date(since)
        result = eventbrite.get("/users/me/" + datatype +"/", data=data)

        datatype = datatype.split("_")[-1]
        if result[datatype]:
            for e in result[datatype]:
                e.update({"_id": e["id"]})
                e.update({"_updated": "%s" % e["changed"]})

                entities.append(e)


        return entities

data_access_layer = DataAccess()

def get_var(var):
    envvar = None
    if var.upper() in os.environ:
        envvar = os.environ[var.upper()]
    else:
        envvar = request.args.get(var)
    logger.info("Setting %s = %s" % (var, envvar))
    return envvar

def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
        'Could not verify your access level for that URL.\n'
        'You have to login with proper credentials', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth:
            return authenticate()
        return f(*args, **kwargs)

    return decorated

@app.route('/<datatype>', methods=['GET'])
@requires_auth
def get_entities(datatype):
    since = request.args.get('since')
    auth = request.authorization
    password = auth.password
    eventbrite = Eventbrite(password)
    entities = sorted(data_access_layer.get_entities(since, datatype, eventbrite), key=lambda k: k["_updated"])

    return Response(json.dumps(entities), mimetype='application/json')


if __name__ == '__main__':
    # Set up logging
    format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logger = logging.getLogger('salesforce-microservice')

    # Log to stdout
    stdout_handler = logging.StreamHandler()
    stdout_handler.setFormatter(logging.Formatter(format_string))
    logger.addHandler(stdout_handler)

    logger.setLevel(logging.DEBUG)

    app.run(debug=True, host='0.0.0.0')

