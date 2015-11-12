import urllib.parse
import json

def get_query(handler):
    query = urllib.parse.urlparse(handler.path).query
    query = urllib.parse.unquote(query)
    query = query.split('&')
    result = {}
    for item in query:
        items = item.split('=')
        if len(items) != 2:
            continue
        key, value = items
        key = json.loads('"{}"'.format(key))
        value = json.loads('"{}"'.format(value))
        result[key] = value
    return result